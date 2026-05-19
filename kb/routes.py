import os
import re
import time
import json

from flask import Blueprint, request, jsonify, g, Response, stream_with_context
from functools import wraps

from server.auth import login_required, admin_required
from kb.database import get_db
from kb.search import search_wiki
from kb.llm import is_llm_available, call_llm
from kb.context_compressor import ContextCompressor
from kb.session_db import get_session_db
from kb.tools import _extract_relevant_snippets

wiki_bp = Blueprint('wiki', __name__, url_prefix='/api/kb')

PERMISSION_LEVELS = {'view': 0, 'edit': 1, 'manage': 2}


def _check_wiki_permission(usr_id, target_usr_id, required_level):
    """检查用户对目标用户知识库的权限"""
    if not usr_id:
        return False
    # 检查是否为管理员：从 g 或数据库获取当前用户角色
    from server.auth import _load_json, _get_users_path
    users = _load_json(_get_users_path())
    user_info = users.get(usr_id, {})
    if user_info.get('role', 'viewer') == 'admin':
        return True
    if usr_id == target_usr_id:
        return True

    conn = get_db(usr_id)
    row = conn.execute(
        "SELECT permission_level FROM wiki_permissions WHERE usr_id = ? AND shared_user_id = ?",
        (target_usr_id, usr_id)
    ).fetchone()
    if row:
        actual = PERMISSION_LEVELS.get(row['permission_level'], -1)
        return actual >= PERMISSION_LEVELS.get(required_level, 0)
    return False


def _require_wiki_permission(required_level):
    """KB 专属权限校验装饰器，需在 @login_required 之后使用"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            user_id = g.user_id
            if not user_id:
                return jsonify({'success': False, 'message': '未登录，请先登录'}), 401

            # 此处可扩展：检查 user_id 对当前资源的具体权限
            # 目前仅保证已登录，具体权限由调用方通过 _check_wiki_permission 判断

            return f(*args, **kwargs)
        return decorated
    return decorator


def _get_system_skills_dir() -> str:
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root_dir, 'kb', 'skills', 'system')


def _list_system_skills() -> list:
    system_dir = _get_system_skills_dir()
    if not os.path.exists(system_dir):
        return []
    skills = []
    for name in os.listdir(system_dir):
        skill_dir = os.path.join(system_dir, name)
        if os.path.isdir(skill_dir):
            skill_md = os.path.join(skill_dir, 'SKILL.md')
            if os.path.exists(skill_md):
                try:
                    content = open(skill_md, 'r', encoding='utf-8').read()
                    fm = _parse_frontmatter(content)
                    skills.append({
                        "name": name,
                        "frontmatter": fm,
                        "exists": True,
                        "source": "system",
                    })
                except Exception:
                    pass
    return skills


def _parse_frontmatter(content: str) -> dict:
    import re
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return {}
    fm_text = match.group(1)
    fm = {}
    for line in fm_text.split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip()
    return fm


def _build_skills_index(usr_id: str) -> str:
    try:
        from .skills.manager import list_skills as list_user_skills
        user_skills = list_user_skills(usr_id, state="active")
        system_skills = _list_system_skills()
        all_skills = system_skills + user_skills
        if not all_skills:
            return ""
        lines = ["## 可用技能索引", ""]
        current_category = None
        for s in sorted(all_skills, key=lambda x: (x.get('source', 'user'), x.get('name', ''))):
            name = s.get("name", "")
            fm = s.get("frontmatter", {})
            desc = fm.get("description", "") if isinstance(fm, dict) else ""
            cat = fm.get("category", "") if isinstance(fm, dict) else ""
            source = s.get("source", "user")
            marker = "🔒" if source == "system" else ""
            if cat and cat != current_category:
                lines.append(f"### {cat}")
                current_category = cat
            line = f"- **{name}**{marker}"
            if desc:
                line += f": {desc}"
            lines.append(line)
        lines.append("")
        return "\n".join(lines)
    except Exception:
        return ""


def update_search_index(usr_id, file_path, title, content):
    conn = get_db(usr_id)
    conn.execute("DELETE FROM wiki_fts WHERE usr_id = ? AND path = ?", (usr_id, file_path))
    conn.execute(
        "INSERT INTO wiki_fts (usr_id, title, content, path) VALUES (?, ?, ?, ?)",
        (usr_id, title, content, file_path)
    )

    now = time.time()
    existing = conn.execute(
        "SELECT path FROM wiki_files WHERE usr_id = ? AND path = ?",
        (usr_id, file_path)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE wiki_files SET title = ?, updated_at = ? WHERE usr_id = ? AND path = ?",
            (title, now, usr_id, file_path)
        )
    else:
        conn.execute(
            "INSERT INTO wiki_files (usr_id, path, title, created_at, updated_at, file_size) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (usr_id, file_path, title, now, now, len(content))
        )

    conn.commit()


def remove_from_index(usr_id, file_path):
    conn = get_db(usr_id)
    conn.execute("DELETE FROM wiki_fts WHERE usr_id = ? AND path = ?", (usr_id, file_path))
    conn.commit()


def _extract_title_from_md(content):
    for line in content.split('\n')[:10]:
        stripped = line.strip()
        if stripped.startswith('# '):
            return stripped[2:].strip()
    return ''


# ==================== 知识库管理 ====================

@wiki_bp.route('/info', methods=['GET'])
@login_required
@_require_wiki_permission('view')
def get_wiki_info():
    usr_id = g.user_id
    conn = get_db(usr_id)
    row = conn.execute("SELECT * FROM wiki_info WHERE usr_id = ?", (usr_id,)).fetchone()

    if not row:
        now = time.time()
        conn.execute(
            "INSERT INTO wiki_info (usr_id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (usr_id, '我的知识库', '', now, now)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM wiki_info WHERE usr_id = ?", (usr_id,)).fetchone()

    return jsonify({
        'success': True,
        'info': {
            'usr_id': row['usr_id'],
            'name': row['name'],
            'description': row['description'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }
    })


@wiki_bp.route('/settings', methods=['POST'])
@login_required
@_require_wiki_permission('manage')
def update_wiki_settings():
    usr_id = g.user_id
    data = request.get_json()
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()

    conn = get_db(usr_id)
    row = conn.execute("SELECT * FROM wiki_info WHERE usr_id = ?", (usr_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '知识库未初始化'})

    now = time.time()
    conn.execute(
        "UPDATE wiki_info SET name = ?, description = ?, updated_at = ? WHERE usr_id = ?",
        (name or '我的知识库', description, now, usr_id)
    )
    conn.commit()
    return jsonify({'success': True, 'message': '设置已更新'})


# ==================== 文件操作 ====================

@wiki_bp.route('/files', methods=['GET'])
@login_required
@_require_wiki_permission('view')
def list_files():
    usr_id = g.user_id
    subdir = request.args.get('subdir', '').strip()

    if subdir.startswith('imported/'):
        return _list_imported_files(usr_id, subdir)

    if not subdir:
        return jsonify({
            'success': True,
            'files': [],
            'folders': [{'name': 'imported', 'path': 'imported'}],
            'current_path': ''
        })

    return jsonify({'success': True, 'files': [], 'folders': [], 'current_path': subdir})


def _list_imported_files(usr_id, subdir):
    """从 wiki_files 表查 imported 下的文件"""
    conn = get_db(usr_id)
    prefix = subdir.rstrip('/') + '/'

    rows = conn.execute(
        "SELECT path, title, created_at, updated_at "
        "FROM wiki_files WHERE usr_id = ? AND path LIKE ?",
        (usr_id, prefix + '%')
    ).fetchall()

    files = []
    folder_names = set()
    for row in rows:
        rel = row['path'][len(prefix):]
        parts = rel.split('/')
        if len(parts) == 1:
            files.append({
                'name': parts[0],
                'path': row['path'],
                'mtime': row['updated_at'],
                'ext': '.md'
            })
        else:
            folder_names.add(parts[0])

    folders = [{'name': f, 'path': prefix + f} for f in sorted(folder_names)]

    return jsonify({
        'success': True,
        'files': files,
        'folders': folders,
        'current_path': subdir
    })


@wiki_bp.route('/files/<path:file_path>', methods=['GET'])
@login_required
@_require_wiki_permission('view')
def get_file_content(file_path):
    usr_id = g.user_id

    if not file_path.startswith('imported/'):
        return jsonify({'success': False, 'message': '不支持的路径'}), 400

    conn = get_db(usr_id)
    row = conn.execute(
        "SELECT content FROM wiki_fts WHERE usr_id = ? AND path = ?",
        (usr_id, file_path)
    ).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    return jsonify({
        'success': True,
        'content': row['content'],
        'file_type': '.md'
    })


# ==================== 搜索 ====================

@wiki_bp.route('/search', methods=['GET'])
@login_required
@_require_wiki_permission('view')
def search_files():
    usr_id = g.user_id
    q = request.args.get('q', '').strip()

    if not q:
        return jsonify({'success': True, 'results': []})

    results = search_wiki(usr_id, q)
    return jsonify({'success': True, 'results': results, 'query': q})


@wiki_bp.route('/agent/context', methods=['POST'])
@login_required
@_require_wiki_permission('view')
def agent_context():
    try:
        usr_id = g.user_id
        data = request.get_json() or {}
        query = (data.get('query') or '').strip()
        max_chars = data.get('max_chars', 10000)
        session_id = data.get('session_id')
        stream = data.get('stream', False)

        if not query:
            return jsonify({'success': True, 'context': '', 'sources': [], 'session_id': session_id, 'llm_used': False})

        results = search_wiki(usr_id, query)

        context_parts = []
        sources = []
        total_chars = 0

        # 先收集所有匹配文档的来源（不受字符预算限制）
        for r in results:
            src = {'path': r['path'], 'title': r['title']}
            if r['path'].startswith('imported/'):
                parts = r['path'].split('/')
                if len(parts) >= 3:
                    src['fb_id'] = parts[1]
                    fb_path = '/'.join(parts[2:])
                    # 同步时非 .md 文件被追加了 .md 后缀，需还原
                    base, ext = os.path.splitext(fb_path)
                    if ext.lower() == '.md' and os.path.splitext(base)[1]:
                        fb_path = base
                    src['fb_path'] = fb_path
            sources.append(src)

        keywords = query.lower().split()
        num_results = len(results)

        conn = get_db(usr_id)

        for i, r in enumerate(results):
            row = conn.execute(
                "SELECT content FROM wiki_fts WHERE usr_id = ? AND path = ?",
                (usr_id, r['path'])
            ).fetchone()
            if not row or not row['content'].strip():
                continue

            # 公平配额：剩余预算 / 剩余待处理文档数
            remaining_results = num_results - i
            doc_budget = (max_chars - total_chars) // remaining_results
            if doc_budget <= 0:
                continue

            doc_content = _extract_relevant_snippets(row['content'], keywords, doc_budget)
            context_parts.append(f"## {r['title']}\n\n{doc_content}")
            total_chars += len(doc_content)

        kb_context = '\n\n---\n\n'.join(context_parts)

        # 对非LLM返回的匹配内容做关键词高亮标记
        kb_context_marked = kb_context or ''
        if kb_context and keywords:
            for kw in keywords:
                if len(kw) < 1:
                    continue
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                kb_context_marked = pattern.sub(lambda m: f'<mark>{m.group()}</mark>', kb_context)

        from .memory import get_memory_store
        from .context_fence import build_memory_context_block
        memory_store = get_memory_store(usr_id)
        memory_block = memory_store.format_for_system_prompt()
        memory_context = build_memory_context_block(memory_block) if memory_block else ""

        llm_error = None
        if is_llm_available(usr_id):
            skills_index = _build_skills_index(usr_id)

            kb_context = f"获取信息时优选wiki_search工具，以下是首次search结果：\n{kb_context}" if kb_context else "没有结果，可能需要尝试更多关键词。\n"
            system_prompt = f"""你是全力满足用户需求的助手（需求不明时可提问）。

{kb_context}
你的记忆：{memory_context}
你的技能：{skills_index}"""

            from .tools import ALL_TOOL_SCHEMAS, execute_tool_call
            from .llm import call_llm_with_tools, call_llm_with_tools_stream

            messages_history = None
            if session_id:
                try:
                    db = get_session_db(usr_id)
                    raw_messages = db.get_messages(session_id)
                    if raw_messages:
                        messages_history = []
                        for m in raw_messages:
                            role = m.get("role", "")
                            content = m.get("content", "")
                            if role in ("user", "assistant") and content:
                                messages_history.append({"role": role, "content": content})

                        compressor = ContextCompressor()
                        if compressor.should_compress(messages_history):
                            previous_summary = db.get_meta(f"summary:{session_id}")
                            messages_history = compressor.compress(
                                messages_history, user_id=usr_id, previous_summary=previous_summary
                            )
                            for m in messages_history:
                                if m.get("role") == "system" and "[上下文摘要" in m.get("content", ""):
                                    db.set_meta(f"summary:{session_id}", m["content"])
                                    break
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).debug("Session history load failed: %s", e)
                    messages_history = None

            def _tool_exec(name, args):
                return execute_tool_call(name, args, usr_id)

            from .interrupt import InterruptRegistry, InterruptedError
            interrupt_reg = InterruptRegistry.get_instance()
            session_key = session_id or f"anon_{usr_id}_{id(query)}"
            interrupt_event = interrupt_reg.register(session_key)

            # === 流式分支 ===
            if stream:
                def generate():
                    try:
                        full_content = ""
                        for event in call_llm_with_tools_stream(
                            system_prompt=system_prompt,
                            user_query=query,
                            messages_history=messages_history,
                            tools=ALL_TOOL_SCHEMAS,
                            max_tool_rounds=5,
                            tool_executor=_tool_exec,
                            user_id=usr_id,
                            interrupt_event=interrupt_event,
                            sources=sources,
                        ):
                            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                            if event.get("type") in ("interrupted", "error"):
                                break

                            # 收集完整内容用于后续处理
                            if event.get("type") == "done":
                                full_content = event.get("content", "")
                                tool_count = event.get("tool_calls", 0)
                                from .context_fence import sanitize_context
                                safe_content = sanitize_context(full_content)
                                if tool_count > 0:
                                    from .auto_extract import auto_extract_async
                                    auto_extract_async(usr_id, query, safe_content)
                                # 记录 assistant 消息到会话
                                if session_id and safe_content:
                                    try:
                                        sdb = get_session_db(usr_id)
                                        sdb.add_message(session_id, "assistant", safe_content)
                                    except Exception:
                                        pass
                    finally:
                        interrupt_reg.unregister(session_key)

                return Response(stream_with_context(generate()), mimetype='text/event-stream')

            # === 非流式分支（原逻辑） ===
            try:
                llm_result = call_llm_with_tools(
                    system_prompt=system_prompt,
                    user_query=query,
                    messages_history=messages_history,
                    tools=ALL_TOOL_SCHEMAS,
                    max_tool_rounds=5,
                    tool_executor=_tool_exec,
                    user_id=usr_id,
                    interrupt_event=interrupt_event,
                )
            finally:
                interrupt_reg.unregister(session_key)

            llm_error = llm_result.get("error")
            interrupted = llm_result.get("interrupted", False)
            answer = llm_result.get("content", "")
            if answer or interrupted:
                from .context_fence import sanitize_context
                answer = sanitize_context(answer)

                if llm_result.get("tool_calls_made") and not interrupted:
                    from .auto_extract import auto_extract_async
                    auto_extract_async(usr_id, query, answer)

                return jsonify({
                    'success': True,
                    'context': answer,
                    'sources': sources,
                    'session_id': session_id,
                    'llm_used': True,
                    'tool_calls': len(llm_result.get("tool_calls_made", [])),
                    'interrupted': interrupted,
                })

        message = None
        if is_llm_available(usr_id):
            if llm_error:
                message = f'AI 助手响应失败: {llm_error}'
            else:
                message = 'AI 助手暂时不可用，请稍后重试。'
        else:
            message = '没有匹配内容，请配置 AI 模型。'

        return jsonify({
            'success': True,
            'context': kb_context_marked,
            'message': message,
            'sources': sources,
            'session_id': session_id,
            'llm_used': False,
        })
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[ERROR] agent_context failed: {e}\n{error_detail}")
        return jsonify({'success': False, 'message': f'服务器内部错误: {str(e)}', 'error_detail': error_detail}), 200


@wiki_bp.route('/agent/stop', methods=['POST'])
@login_required
@_require_wiki_permission('view')
def agent_stop():
    try:
        usr_id = g.user_id
        data = request.get_json() or {}
        session_id = data.get('session_id')

        from .interrupt import InterruptRegistry
        interrupt_reg = InterruptRegistry.get_instance()

        if session_id:
            stopped = interrupt_reg.signal(session_id)
        else:
            stopped = False

        return jsonify({'success': True, 'stopped': stopped})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 200


# --- LLM 配置接口 ---

LLM_PROVIDERS = [
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "models": []},
    {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "models": []},
    {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "models": []},
    {"name": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "models": []},
    {"name": "阿里百炼", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "models": []},
    {"name": "Moonshot", "base_url": "https://api.moonshot.cn/v1", "models": []},
    {"name": "Groq", "base_url": "https://api.groq.com/openai/v1", "models": []},
    {"name": "智谱", "base_url": "https://open.bigmodel.cn/api/paas/v4", "models": []},
    {"name": "自定义", "base_url": "", "models": []},
]


def _parse_llm_error(resp):
    """解析 LLM 提供商返回的错误响应，提取可读的错误信息"""
    import logging
    logger = logging.getLogger(__name__)

    status_code = resp.status_code
    raw_text = resp.text[:500]

    logger.info('LLM provider error response: HTTP %s, body: %s', status_code, raw_text[:300])

    error_msg = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            if 'error' in body:
                err = body['error']
                if isinstance(err, dict):
                    error_msg = err.get('message') or err.get('msg') or err.get('error', '')
                    err_code = err.get('code') or err.get('type', '')
                    if err_code and str(err_code) not in str(error_msg):
                        error_msg = f'{error_msg} (code: {err_code})' if error_msg else str(err_code)
                elif isinstance(err, str):
                    error_msg = err
            if not error_msg:
                for key in ('message', 'msg', 'detail', 'error_message', 'reason'):
                    if key in body and body[key]:
                        error_msg = str(body[key])
                        break
    except Exception:
        pass

    if not error_msg:
        if status_code == 401:
            error_msg = 'API Key 无效或已过期'
        elif status_code == 403:
            error_msg = '无权访问'
        elif status_code == 404:
            error_msg = '接口不存在'
        elif status_code == 429:
            error_msg = '请求过于频繁'
        elif status_code == 500:
            error_msg = '服务器内部错误'
        elif status_code == 502:
            error_msg = '网关错误'
        elif status_code == 503:
            error_msg = '服务暂不可用'
        else:
            error_msg = f'HTTP {status_code}'

    if raw_text.strip():
        cleaned = raw_text.strip()
        if error_msg and error_msg not in cleaned and cleaned not in error_msg:
            error_msg = f'{error_msg}: {cleaned}'
        elif not error_msg:
            error_msg = cleaned

    hints = {
        401: '请检查 API Key 是否正确',
        403: '请检查 API Key 是否有该模型的访问权限',
        404: '请检查 API 地址和模型名称是否正确',
        429: '请稍后重试或更换 API Key',
        500: '请确认模型名称是否正确，或提供商服务是否正常',
        502: '提供商网关错误，请稍后重试',
        503: '提供商服务暂不可用，请稍后重试',
    }
    hint = hints.get(status_code, '')

    if hint:
        return f'{error_msg}（{hint}）'
    return error_msg


def _build_models_url(base_url):
    """根据 base_url 构建 /models 端点 URL"""
    base_url = base_url.rstrip('/')
    if base_url.endswith('/models'):
        return base_url
    if base_url.endswith('/v1') or base_url.endswith('/v4'):
        return base_url + '/models'
    if '/v1' in base_url or '/v4' in base_url:
        return base_url + '/models'
    return base_url + '/v1/models'


def _build_chat_url(base_url):
    """根据 base_url 构建 /chat/completions 端点 URL"""
    base_url = base_url.rstrip('/')
    if base_url.endswith('/chat/completions'):
        return base_url
    if base_url.endswith('/v1') or base_url.endswith('/v4'):
        return base_url + '/chat/completions'
    if '/v1' in base_url or '/v4' in base_url:
        return base_url + '/chat/completions'
    return base_url + '/v1/chat/completions'


@wiki_bp.route('/llm-config', methods=['GET'])
@login_required
@_require_wiki_permission('view')
def get_llm_config_route():
    from .config import get_llm_config, _mask_api_key
    cfg = get_llm_config(g.user_id)
    masked = dict(cfg)
    if masked.get('api_key'):
        masked['api_key'] = _mask_api_key(masked['api_key'])
    return jsonify({'success': True, 'config': masked})


@wiki_bp.route('/llm-config', methods=['PUT'])
@login_required
@_require_wiki_permission('manage')
def update_llm_config_route():
    from .config import save_llm_config, get_llm_config
    data = request.get_json() or {}
    llm_cfg = data.get('llm', {})

    api_key = llm_cfg.get('api_key', '')
    if not api_key or '****' in api_key:
        current = get_llm_config(g.user_id)
        existing = current.get('api_key', '')
        llm_cfg['api_key'] = existing

    ok = save_llm_config(llm_cfg, g.user_id)
    if ok:
        return jsonify({'success': True, 'message': 'LLM 配置已保存'}), 200
    return jsonify({'success': False, 'message': '保存配置失败'}), 200


@wiki_bp.route('/llm-providers', methods=['GET'])
def get_llm_providers():
    return jsonify({'success': True, 'providers': LLM_PROVIDERS})


@wiki_bp.route('/llm-models', methods=['POST'])
def get_llm_models():
    """从提供商API动态获取可用模型列表"""
    data = request.get_json() or {}
    base_url = data.get('base_url', '').strip()
    api_key = data.get('api_key', '').strip()

    if not base_url:
        return jsonify({'success': False, 'message': '缺少 base_url'}), 200

    try:
        import requests

        models_url = _build_models_url(base_url)
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        resp = requests.get(models_url, headers=headers, timeout=10)

        if resp.status_code != 200:
            error_msg = _parse_llm_error(resp)
            return jsonify({
                'success': False,
                'message': f'获取模型列表失败: {error_msg}'
            }), 200

        result = resp.json()

        models = []
        if 'data' in result:
            for item in result['data']:
                if isinstance(item, dict) and 'id' in item:
                    models.append(item['id'])
        elif isinstance(result, list):
            models = [item.get('id', item) if isinstance(item, dict) else str(item) for item in result]
        else:
            for key in ['models', 'model_ids', 'available_models']:
                if key in result and isinstance(result[key], list):
                    models = [item.get('id', item) if isinstance(item, dict) else str(item) for item in result[key]]
                    break

        if not models:
            return jsonify({
                'success': False,
                'message': '无法解析模型列表，请手动输入模型名称'
            }), 200

        return jsonify({
            'success': True,
            'models': sorted(models)
        })

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': '请求超时，请检查 API 地址是否正确'}), 200
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': '连接失败，请检查 API 地址和网络连接'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取模型列表失败: {str(e)}'}), 200


@wiki_bp.route('/llm-test', methods=['POST'])
@login_required
@_require_wiki_permission('view')
def test_llm_connection():
    """测试 LLM 连接：验证网络 → 验证 API Key → 验证模型名称 → 发送测试消息"""
    data = request.get_json() or {}
    test_cfg = data.get('llm', {})

    from .config import get_llm_config
    current = dict(get_llm_config(g.user_id))
    for k in ('api_key', 'base_url', 'model'):
        if k in test_cfg and test_cfg[k]:
            if '****' not in test_cfg[k]:
                current[k] = test_cfg[k]

    if not current.get('api_key') or not current.get('base_url') or not current.get('model'):
        return jsonify({'success': False, 'message': '请先填写 API Key、API 地址和模型名称'}), 200

    import logging
    logger = logging.getLogger(__name__)

    try:
        import requests

        base_url = current['base_url'].rstrip('/')
        api_key = current['api_key']
        model = current['model']

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        models_url = _build_models_url(base_url)
        logger.info('LLM test step 1: fetching models from %s', models_url)

        models_resp = None
        available_models = []
        try:
            models_resp = requests.get(models_url, headers=headers, timeout=8)
            logger.info('LLM test step 1: models endpoint returned HTTP %s', models_resp.status_code)

            if models_resp.status_code == 401 or models_resp.status_code == 403:
                error_msg = _parse_llm_error(models_resp)
                return jsonify({'success': False, 'message': f'API Key 验证失败: {error_msg}'}), 200

            if models_resp.status_code == 200:
                try:
                    result = models_resp.json()
                    if isinstance(result, dict) and 'data' in result:
                        available_models = [item['id'] for item in result['data'] if isinstance(item, dict) and 'id' in item]
                    elif isinstance(result, list):
                        available_models = [item.get('id', item) if isinstance(item, dict) else str(item) for item in result]
                except Exception:
                    pass

                if available_models and model not in available_models:
                    close_matches = [m for m in available_models if model.lower() in m.lower()]
                    suggestion = ''
                    if close_matches:
                        suggestion = f'，您是否要使用: {", ".join(close_matches[:5])}'
                    return jsonify({
                        'success': False,
                        'message': f'模型 "{model}" 不存在，该提供商可用模型: {", ".join(available_models[:10])}{"..." if len(available_models) > 10 else ""}{suggestion}'
                    }), 200
        except requests.exceptions.ConnectionError:
            return jsonify({'success': False, 'message': f'无法连接到 {base_url}，请检查 API 地址和网络'}), 200
        except requests.exceptions.Timeout:
            return jsonify({'success': False, 'message': '连接超时，请检查 API 地址是否正确'}), 200
        except Exception as e:
            logger.debug('Models endpoint check failed: %s', e)

        chat_url = _build_chat_url(base_url)
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': 'hi'}],
            'max_tokens': 5,
            'temperature': 0.1,
        }
        logger.info('LLM test step 2: sending chat request to %s, model=%s', chat_url, model)

        resp = requests.post(chat_url, headers=headers, json=payload, timeout=20)
        logger.info('LLM test step 2: chat endpoint returned HTTP %s', resp.status_code)

        if resp.status_code == 200:
            return jsonify({'success': True, 'message': '连接成功！模型响应正常。'}), 200
        else:
            error_msg = _parse_llm_error(resp)
            if available_models:
                return jsonify({
                    'success': False,
                    'message': f'{error_msg}'
                }), 200
            return jsonify({'success': False, 'message': error_msg}), 200
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': '请求超时，请检查 API 地址是否正确或网络是否畅通'}), 200
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': f'无法连接到 {current.get("base_url", "")}，请检查 API 地址和网络'}), 200
    except Exception as e:
        logger.error('LLM 测试异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': f'测试异常: {str(e)}'}), 200


# --- Memory system endpoints ---
from .routes_memory import register_memory_routes
register_memory_routes(wiki_bp)

# --- Session memory endpoints ---
from .routes_session import register_session_routes
register_session_routes(wiki_bp)

# --- Skills system endpoints ---
from .routes_skills import register_skills_routes
register_skills_routes(wiki_bp)

# --- Insights endpoints ---
from .routes_insights import register_insights_routes
register_insights_routes(wiki_bp)