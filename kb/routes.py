import os
import time
import json

from flask import Blueprint, request, jsonify
from functools import wraps

from kb.database import get_db
from kb.search import search_wiki

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

    conn = get_db()
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
    conn = get_db()
    conn.execute("DELETE FROM wiki_fts WHERE usr_id = ? AND path = ?", (usr_id, file_path))
    conn.execute(
        "INSERT INTO wiki_fts (usr_id, title, content, path) VALUES (?, ?, ?, ?)",
        (usr_id, title, content, file_path)
    )
    conn.commit()


def remove_from_index(usr_id, file_path):
    conn = get_db()
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
    conn = get_db()
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

    conn = get_db()
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
    conn = get_db()
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

    if not query:
        return jsonify({'success': True, 'context': '', 'sources': []})

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

    return jsonify({
        'success': True,
        'context': '\n\n---\n\n'.join(context_parts),
        'sources': sources
    })
