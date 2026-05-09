import os
import time
import json

from flask import Blueprint, request, jsonify
from functools import wraps

from kb.database import get_db
from kb.search import search_wiki
from kb.config import get_kb_section
from kb.llm import is_llm_available, call_llm
from kb.context_compressor import ContextCompressor
from kb.session_db import get_session_db

wiki_bp = Blueprint('wiki', __name__, url_prefix='/api/kb')

PERMISSION_LEVELS = {'view': 0, 'edit': 1, 'manage': 2}


def _get_user_id():
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    elif auth_header:
        token = auth_header

    if not token:
        data = request.get_json(silent=True) or {}
        token = data.get('token') or data.get('client_id')

    if not token:
        token = request.args.get('token') or request.args.get('client_id')

    if not token:
        token = request.form.get('token') or request.form.get('client_id')

    if not token:
        return None

    tokens_path = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'auth', 'tokens.json')
    try:
        if os.path.exists(tokens_path):
            with open(tokens_path, 'r', encoding='utf-8') as f:
                tokens = json.load(f)
            return tokens.get(token)
    except Exception:
        pass
    return None


def _get_user_role(user_id):
    try:
        users_path = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'auth', 'users.json')
        if os.path.exists(users_path):
            with open(users_path, 'r', encoding='utf-8') as f:
                users = json.load(f)
            user_info = users.get(user_id, {})
            return user_info.get('role', 'viewer')
    except Exception:
        pass
    return 'viewer'


def _is_admin(user_id):
    return _get_user_role(user_id) == 'admin'


def _check_wiki_permission(usr_id, target_usr_id, required_level):
    if not usr_id:
        return False
    if _is_admin(usr_id):
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
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            user_id = _get_user_id()
            if not user_id:
                return jsonify({'success': False, 'message': '未登录，请先登录'}), 401

            kwargs['_user_id'] = user_id
            return f(*args, **kwargs)
        return decorated
    return decorator


def _get_kb_root(usr_id):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kb_dir = os.path.join(root_dir, 'workspaces', usr_id, 'kb')
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir


def _build_skills_index(usr_id: str) -> str:
    try:
        from .skills.manager import list_skills
        skills = list_skills(usr_id, state="active")
        if not skills:
            return ""
        lines = ["## 可用技能索引", ""]
        for s in skills:
            name = s.get("name", "")
            fm = s.get("frontmatter", {})
            desc = fm.get("description", "") if isinstance(fm, dict) else ""
            cat = fm.get("category", "") if isinstance(fm, dict) else ""
            line = f"- **{name}**"
            if cat:
                line += f" [{cat}]"
            if desc:
                line += f": {desc}"
            lines.append(line)
        lines.append("")
        return "\n".join(lines)
    except Exception:
        return ""


def sanitize_path(user_path):
    clean_path = user_path.lstrip('/').replace('\\', '/')
    parts = clean_path.split('/')
    safe_parts = []
    for part in parts:
        if part == '..' or part == '.' or not part:
            continue
        safe_parts.append(part)
    return os.path.join(*safe_parts)


def validate_file_path(usr_id, file_path):
    kb_root = _get_kb_root(usr_id)
    if not file_path:
        return kb_root, kb_root
    safe = sanitize_path(file_path)
    full_path = os.path.normpath(os.path.join(kb_root, safe))
    if not full_path.startswith(os.path.normpath(kb_root)):
        return None, None
    return kb_root, full_path


def update_search_index(usr_id, file_path, title, content):
    conn = get_db(usr_id)
    conn.execute("DELETE FROM wiki_fts WHERE usr_id = ? AND path = ?", (usr_id, file_path))
    conn.execute(
        "INSERT INTO wiki_fts (usr_id, title, content, path) VALUES (?, ?, ?, ?)",
        (usr_id, title, content, file_path)
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
@_require_wiki_permission('view')
def get_wiki_info(_user_id=None):
    usr_id = _user_id
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
@_require_wiki_permission('manage')
def update_wiki_settings(_user_id=None):
    usr_id = _user_id
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
@_require_wiki_permission('view')
def list_files(_user_id=None):
    usr_id = _user_id
    kb_root = _get_kb_root(usr_id)
    subdir = request.args.get('subdir', '').strip()

    if subdir:
        target_dir = os.path.normpath(os.path.join(kb_root, subdir))
        if not target_dir.startswith(os.path.normpath(kb_root)):
            return jsonify({'success': False, 'message': '路径非法'})
    else:
        target_dir = kb_root

    if not os.path.isdir(target_dir):
        return jsonify({'success': True, 'files': [], 'folders': [], 'current_path': subdir})

    files = []
    folders = []
    try:
        for entry in os.scandir(target_dir):
            if entry.name.startswith('.'):
                continue
            if entry.is_file():
                files.append({
                    'name': entry.name,
                    'path': os.path.relpath(entry.path, kb_root).replace('\\', '/'),
                    'size': entry.stat().st_size,
                    'mtime': entry.stat().st_mtime,
                    'ext': os.path.splitext(entry.name)[1].lower()
                })
            elif entry.is_dir():
                folders.append({
                    'name': entry.name,
                    'path': os.path.relpath(entry.path, kb_root).replace('\\', '/')
                })
    except PermissionError:
        return jsonify({'success': False, 'message': '没有权限访问此目录'})

    folders.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())

    return jsonify({
        'success': True,
        'files': files,
        'folders': folders,
        'current_path': subdir
    })


@wiki_bp.route('/files/<path:file_path>', methods=['GET'])
@_require_wiki_permission('view')
def get_file_content(file_path, _user_id=None):
    usr_id = _user_id
    kb_root, full_path = validate_file_path(usr_id, file_path)
    if full_path is None:
        return jsonify({'success': False, 'message': '路径非法'}), 400

    if not os.path.isfile(full_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    ext = os.path.splitext(full_path)[1].lower()
    if ext not in ('.md', '.txt', '.html', '.htm', '.xml', '.json', '.csv', '.yaml', '.yml', '.py', '.js', '.css'):
        return jsonify({'success': False, 'message': '不支持的文件类型'}), 400

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content, 'file_type': ext})
    except UnicodeDecodeError:
        return jsonify({'success': False, 'message': '无法以文本方式读取此文件'}), 400


@wiki_bp.route('/files/<path:file_path>', methods=['POST'])
@_require_wiki_permission('edit')
def create_or_update_file(file_path, _user_id=None):
    usr_id = _user_id
    data = request.get_json()
    content = data.get('content', '')

    kb_root, full_path = validate_file_path(usr_id, file_path)
    if full_path is None:
        return jsonify({'success': False, 'message': '路径非法'}), 400

    if not full_path.lower().endswith('.md'):
        full_path = full_path + '.md'

    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    old_title = ''
    if os.path.isfile(full_path):
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                old_title = _extract_title_from_md(f.read())
        except Exception:
            pass

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

    title = _extract_title_from_md(content) or os.path.splitext(os.path.basename(full_path))[0]
    rel_path = os.path.relpath(full_path, kb_root).replace('\\', '/')
    update_search_index(usr_id, rel_path, title, content)

    now = time.time()
    conn = get_db(usr_id)
    conn.execute(
        "UPDATE wiki_info SET updated_at = ? WHERE usr_id = ?",
        (now, usr_id)
    )
    conn.commit()

    return jsonify({'success': True, 'message': '文件已保存'})


@wiki_bp.route('/files/<path:file_path>', methods=['DELETE'])
@_require_wiki_permission('edit')
def delete_file(file_path, _user_id=None):
    usr_id = _user_id
    kb_root, full_path = validate_file_path(usr_id, file_path)
    if full_path is None:
        return jsonify({'success': False, 'message': '路径非法'}), 400

    if not os.path.isfile(full_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    try:
        os.remove(full_path)
        rel_path = os.path.relpath(full_path, kb_root).replace('\\', '/')
        remove_from_index(usr_id, rel_path)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': True, 'message': '文件已删除'})


# ==================== 文件夹操作 ====================

@wiki_bp.route('/folders', methods=['POST'])
@_require_wiki_permission('edit')
def create_folder(_user_id=None):
    usr_id = _user_id
    data = request.get_json()
    name = (data.get('name') or '').strip()
    parent = (data.get('parent') or '').strip()

    if not name:
        return jsonify({'success': False, 'message': '文件夹名称不能为空'})
    if '/' in name or '\\' in name:
        return jsonify({'success': False, 'message': '文件夹名称不能包含路径分隔符'})

    kb_root, parent_path = validate_file_path(usr_id, parent)
    if parent_path is None:
        return jsonify({'success': False, 'message': '路径非法'}), 400

    new_dir = os.path.join(parent_path, name)
    if os.path.exists(new_dir):
        return jsonify({'success': False, 'message': '同名文件夹已存在'})

    os.makedirs(new_dir, exist_ok=True)
    rel_path = os.path.relpath(new_dir, kb_root).replace('\\', '/')

    return jsonify({'success': True, 'path': rel_path})


@wiki_bp.route('/folders/<path:folder_path>', methods=['DELETE'])
@_require_wiki_permission('edit')
def delete_folder(folder_path, _user_id=None):
    usr_id = _user_id
    kb_root, full_path = validate_file_path(usr_id, folder_path)
    if full_path is None:
        return jsonify({'success': False, 'message': '路径非法'}), 400

    if not os.path.isdir(full_path):
        return jsonify({'success': False, 'message': '文件夹不存在'}), 404

    try:
        import shutil
        shutil.rmtree(full_path)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': True, 'message': '文件夹已删除'})


# ==================== 搜索 ====================

@wiki_bp.route('/search', methods=['GET'])
@_require_wiki_permission('view')
def search_files(_user_id=None):
    usr_id = _user_id
    q = request.args.get('q', '').strip()

    if not q:
        return jsonify({'success': True, 'results': []})

    results = search_wiki(usr_id, q)
    return jsonify({'success': True, 'results': results, 'query': q})


# ==================== Agent 上下文（预留） ====================

@wiki_bp.route('/agent/context', methods=['POST'])
@_require_wiki_permission('view')
def agent_context(_user_id=None):
    usr_id = _user_id
    data = request.get_json() or {}
    query = (data.get('query') or '').strip()
    max_chars = data.get('max_chars', 4000)
    session_id = data.get('session_id')

    if not query:
        return jsonify({'success': True, 'context': '', 'sources': [], 'session_id': session_id, 'llm_used': False})

    results = search_wiki(usr_id, query)

    context_parts = []
    sources = []
    total_chars = 0

    for r in results:
        if total_chars >= max_chars:
            break

        kb_root = _get_kb_root(usr_id)
        full_path = os.path.normpath(os.path.join(kb_root, r['path']))
        if not os.path.isfile(full_path):
            continue

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        remaining = max_chars - total_chars
        if len(content) > remaining:
            content = content[:remaining]

        context_parts.append(f"## {r['title']}\n\n{content}")
        sources.append({'path': r['path'], 'title': r['title']})
        total_chars += len(content)

    kb_context = '\n\n---\n\n'.join(context_parts)

    from .memory import get_memory_store
    from .context_fence import build_memory_context_block
    memory_store = get_memory_store(usr_id)
    memory_block = memory_store.format_for_system_prompt()
    memory_context = build_memory_context_block(memory_block) if memory_block else ""

    if is_llm_available() and kb_context:
        kb_section = get_kb_section()
        wiki_name = kb_section.get('default_name', '知识库')

        skills_index = _build_skills_index(usr_id)

        system_prompt = f"""你是一个专业的知识库助手，基于以下知识库内容回答用户问题。

## 知识库名称
{wiki_name}

## 知识库内容
{kb_context}

{memory_context}
{skills_index}

请根据上述知识库内容回答用户问题。如果知识库中没有相关信息，请明确告知用户。回答要简洁准确，基于提供的内容，不要编造信息。

你拥有持久化记忆和技能管理能力。当用户要求你记住某些信息，或者你发现值得跨会话保留的知识时，请主动使用工具保存。"""

        from .tools import ALL_TOOL_SCHEMAS, execute_tool_call
        from .llm import call_llm_with_tools

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

        llm_result = call_llm_with_tools(
            system_prompt=system_prompt,
            user_query=query,
            messages_history=messages_history,
            tools=ALL_TOOL_SCHEMAS,
            max_tool_rounds=5,
            tool_executor=_tool_exec,
        )

        answer = llm_result.get("content", "")
        if answer:
            from .context_fence import sanitize_context
            answer = sanitize_context(answer)

            if llm_result.get("tool_calls_made"):
                from .auto_extract import auto_extract_async
                auto_extract_async(usr_id, query, answer)

            return jsonify({
                'success': True,
                'context': answer,
                'sources': sources,
                'session_id': session_id,
                'llm_used': True,
                'tool_calls': len(llm_result.get("tool_calls_made", [])),
            })

    return jsonify({
        'success': True,
        'context': kb_context,
        'sources': sources,
        'session_id': session_id,
        'llm_used': False,
    })


# --- LLM 配置接口 ---

LLM_PROVIDERS = [
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]},
    {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "models": ["deepseek-chat", "deepseek-reasoner"]},
    {"name": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "models": ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Pro/Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3"]},
    {"name": "阿里百炼", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"]},
    {"name": "Moonshot", "base_url": "https://api.moonshot.cn/v1", "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]},
    {"name": "Groq", "base_url": "https://api.groq.com/openai/v1", "models": ["llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]},
    {"name": "智谱", "base_url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-4-plus", "glm-4-air", "glm-4-flash"]},
    {"name": "自定义", "base_url": "", "models": []},
]


@wiki_bp.route('/llm-config', methods=['GET'])
@_require_wiki_permission('view')
def get_llm_config_route(_user_id=None):
    from .config import get_llm_config, _mask_api_key
    cfg = get_llm_config()
    masked = dict(cfg)
    if masked.get('api_key'):
        masked['api_key'] = _mask_api_key(masked['api_key'])
    return jsonify({'success': True, 'config': masked})


@wiki_bp.route('/llm-config', methods=['PUT'])
@_require_wiki_permission('manage')
def update_llm_config_route(_user_id=None):
    from .config import save_llm_config, get_llm_config
    data = request.get_json() or {}
    llm_cfg = data.get('llm', {})

    # 如果 api_key 为空或为脱敏值，保留现有加密值
    api_key = llm_cfg.get('api_key', '')
    if not api_key or '****' in api_key:
        current = get_llm_config()
        existing = current.get('api_key', '')
        # 重新加密保存（从内存中的明文重新加密）
        llm_cfg['api_key'] = existing

    ok = save_llm_config(llm_cfg)
    if ok:
        return jsonify({'success': True, 'message': 'LLM 配置已保存'})
    return jsonify({'success': False, 'message': '保存配置失败'}), 500


@wiki_bp.route('/llm-providers', methods=['GET'])
def get_llm_providers(_user_id=None):
    return jsonify({'success': True, 'providers': LLM_PROVIDERS})


@wiki_bp.route('/llm-test', methods=['POST'])
@_require_wiki_permission('manage')
def test_llm_connection(_user_id=None):
    """测试 LLM 连接：发送一条简单消息验证配置是否可用"""
    from .llm import call_llm
    data = request.get_json() or {}
    test_cfg = data.get('llm', {})

    # 临时配置覆盖
    from .config import get_llm_config
    current = dict(get_llm_config())
    for k in ('api_key', 'base_url', 'model'):
        if k in test_cfg and test_cfg[k]:
            if '****' not in test_cfg[k]:
                current[k] = test_cfg[k]

    if not current.get('api_key') or not current.get('base_url') or not current.get('model'):
        return jsonify({'success': False, 'message': '请先填写 API Key、API 地址和模型名称'})

    import logging
    logger = logging.getLogger(__name__)

    try:
        import requests
        url = current['base_url'].rstrip('/') + '/chat/completions'
        headers = {
            'Authorization': f"Bearer {current['api_key']}",
            'Content-Type': 'application/json',
        }
        payload = {
            'model': current['model'],
            'messages': [{'role': 'user', 'content': 'hi'}],
            'max_tokens': 10,
            'temperature': 0.1,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            return jsonify({'success': True, 'message': '连接成功！模型响应正常。'})
        else:
            detail = resp.text[:200]
            return jsonify({'success': False, 'message': f'连接失败 (HTTP {resp.status_code}): {detail}'})
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': '连接超时，请检查 API 地址是否正确'})
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': '无法连接，请检查 API 地址和网络设置'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'连接异常: {str(e)}'})


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