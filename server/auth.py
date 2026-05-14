"""Token 认证系统 + 用户管理 API

认证数据存储位置：workspaces/data/auth/
迁移：从旧路径 ~/.config/DocProc/auth/ 自动迁移
"""

import os
import json
import uuid
import hashlib
import secrets
import time
import shutil
from functools import wraps

from flask import Blueprint, request, jsonify, g
from logging_config import get_logger

logger = get_logger(__name__)

auth_bp = Blueprint('auth', __name__)

SECRET_KEY = os.environ.get('DOCPROC_SECRET', secrets.token_hex(32))

# ==================== 路径工具 ====================

def _get_data_dir():
    """获取全局数据存储目录：workspaces/data/"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'workspaces', 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def _get_auth_data_dir():
    """获取认证数据目录：workspaces/data/auth/"""
    auth_dir = os.path.join(_get_data_dir(), 'auth')
    os.makedirs(auth_dir, exist_ok=True)
    return auth_dir

def _migrate_old_auth_data():
    """从旧路径 ~/.config/DocProc/auth/ 迁移认证数据到新路径"""
    old_auth_dir = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'auth')
    new_auth_dir = _get_auth_data_dir()

    if not os.path.exists(old_auth_dir):
        return

    for filename in ['users.json', 'tokens.json']:
        old_path = os.path.join(old_auth_dir, filename)
        new_path = os.path.join(new_auth_dir, filename)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                shutil.copy2(old_path, new_path)
            except Exception:
                pass

def _get_users_path():
    return os.path.join(_get_auth_data_dir(), 'users.json')

def _get_tokens_path():
    return os.path.join(_get_auth_data_dir(), 'tokens.json')

def _load_json(path):
    # 首次加载时触发迁移
    if 'users.json' in path or 'tokens.json' in path:
        _migrate_old_auth_data()

    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================== 密码 / Token ====================

def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return f'{salt}${pwd_hash}'

def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, pwd_hash = stored.split('$', 1)
        computed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
        return computed == pwd_hash
    except Exception:
        return False

def _generate_token() -> str:
    return secrets.token_hex(32)

def _get_user_id_from_token(token: str) -> str | None:
    tokens = _load_json(_get_tokens_path())
    return tokens.get(token)

# ==================== 装饰器 ====================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

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
            token = request.form.get('token') or request.form.get('client_id')

        if not token:
            return jsonify({'success': False, 'message': '未登录，请先登录'}), 401

        user_id = _get_user_id_from_token(token)
        if not user_id:
            return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401

        g.user_id = user_id
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

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
            token = request.form.get('token') or request.form.get('client_id')

        if not token:
            return jsonify({'success': False, 'message': '未登录，请先登录'}), 401

        user_id = _get_user_id_from_token(token)
        if not user_id:
            return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401

        users = _load_json(_get_users_path())
        user_info = users.get(user_id, {})
        role = user_info.get('role', 'viewer')
        if role != 'admin':
            return jsonify({'success': False, 'message': '需要管理员权限'}), 403

        g.user_id = user_id
        return f(*args, **kwargs)
    return decorated

# ==================== Auth API ====================

@auth_bp.route('/api/register', methods=['POST'])
def api_register():
    from server.settings import ensure_user_config  # 延迟导入避免循环依赖

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '请求数据不能为空'})

    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'})
    if len(username) < 2 or len(username) > 32:
        return jsonify({'success': False, 'message': '用户名长度为 2-32 个字符'})
    if not password or len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少 6 个字符'})

    users = _load_json(_get_users_path())
    for uid, uinfo in users.items():
        if uinfo.get('username') == username:
            return jsonify({'success': False, 'message': '用户名已存在'})

    # 注册用户默认为普通角色
    role = 'viewer'

    user_id = str(uuid.uuid4())
    users[user_id] = {
        'username': username,
        'password': _hash_password(password),
        'role': role,
        'created_at': time.time()
    }
    _save_json(_get_users_path(), users)

    token = _generate_token()
    tokens = _load_json(_get_tokens_path())
    tokens[token] = user_id
    _save_json(_get_tokens_path(), tokens)

    ensure_user_config(user_id)

    return jsonify({
        'success': True,
        'token': token,
        'username': username,
        'role': role,
        'message': '注册成功'
    })

@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    from server.settings import ensure_user_config  # 延迟导入避免循环依赖

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '请求数据不能为空'})

    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})

    users = _load_json(_get_users_path())
    user_id = None
    user_role = 'viewer'
    for uid, uinfo in users.items():
        if uinfo.get('username') == username:
            if _verify_password(password, uinfo.get('password', '')):
                user_id = uid
                user_role = uinfo.get('role', 'viewer')
            break

    if not user_id:
        return jsonify({'success': False, 'message': '用户名或密码错误'})

    token = _generate_token()
    tokens = _load_json(_get_tokens_path())
    tokens[token] = user_id
    _save_json(_get_tokens_path(), tokens)

    ensure_user_config(user_id)

    return jsonify({
        'success': True,
        'token': token,
        'username': username,
        'role': user_role,
        'message': '登录成功'
    })

@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    elif auth_header:
        token = auth_header

    if not token:
        data = request.get_json(silent=True) or {}
        token = data.get('token') or data.get('client_id')

    if token:
        tokens = _load_json(_get_tokens_path())
        tokens.pop(token, None)
        _save_json(_get_tokens_path(), tokens)

    return jsonify({'success': True, 'message': '已退出登录'})

# ==================== 用户管理 API（Admin） ====================

@auth_bp.route('/api/users/list', methods=['GET'])
@admin_required
def api_users_list():
    users = _load_json(_get_users_path())
    user_list = []
    for uid, uinfo in users.items():
        user_list.append({
            'user_id': uid,
            'username': uinfo.get('username', ''),
            'role': uinfo.get('role', 'viewer'),
            'created_at': uinfo.get('created_at', 0),
            'last_active': uinfo.get('last_active', 0)
        })
    return jsonify({'success': True, 'users': user_list})

@auth_bp.route('/api/users/<user_id>/role', methods=['PUT'])
@admin_required
def api_set_user_role(user_id):
    data = request.get_json()
    new_role = (data.get('role') or '').strip()
    if new_role not in ('admin', 'editor', 'viewer'):
        return jsonify({'success': False, 'message': '无效的角色，可选值: admin, editor, viewer'})

    if user_id == g.user_id:
        return jsonify({'success': False, 'message': '不能修改自己的角色'})

    users = _load_json(_get_users_path())
    if user_id not in users:
        return jsonify({'success': False, 'message': '用户不存在'})

    users[user_id]['role'] = new_role
    _save_json(_get_users_path(), users)
    return jsonify({'success': True, 'message': '角色修改成功'})

@auth_bp.route('/api/user/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '请求数据不能为空'})

    old_password = (data.get('old_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()

    if not old_password:
        return jsonify({'success': False, 'message': '请输入原密码'})
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码至少 6 个字符'})

    users = _load_json(_get_users_path())
    if g.user_id not in users:
        return jsonify({'success': False, 'message': '用户不存在'})

    user_info = users[g.user_id]
    if not _verify_password(old_password, user_info.get('password', '')):
        return jsonify({'success': False, 'message': '原密码错误'})

    user_info['password'] = _hash_password(new_password)
    _save_json(_get_users_path(), users)

    return jsonify({'success': True, 'message': '密码修改成功'})

@auth_bp.route('/api/user/me', methods=['GET'])
@login_required
def api_user_me():
    users = _load_json(_get_users_path())
    if g.user_id not in users:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    user_info = users[g.user_id]
    return jsonify({
        'success': True,
        'username': user_info.get('username', ''),
        'role': user_info.get('role', 'viewer'),
        'user_id': g.user_id
    })

# ==================== Admin 用户初始化 ====================

# ==================== 用户活跃时间 ====================

def update_user_activity(user_id):
    """记录用户最后活跃时间到 users.json"""
    users = _load_json(_get_users_path())
    if user_id in users:
        users[user_id]['last_active'] = time.time()
        _save_json(_get_users_path(), users)


def ensure_admin_user():
    """全新部署时自动创建默认管理员账户"""
    from server.settings import ensure_user_config  # 延迟导入避免循环依赖

    users_path = _get_users_path()
    users = _load_json(users_path)
    if users:
        return

    default_user = 'admin'
    user_id = str(uuid.uuid4())
    default_pass = user_id[-6:]  # 取 UUID 后 6 位作为初始密码
    users[user_id] = {
        'username': default_user,
        'password': _hash_password(default_pass),
        'role': 'admin',
        'created_at': time.time()
    }
    _save_json(users_path, users)
    ensure_user_config(user_id)
    logger.info("=" * 50)
    logger.info("  全新部署：已创建默认管理员账户")
    logger.info("  用户名: %s", default_user)
    logger.info("  密码:   %s", default_pass)
    logger.info("  登录后请在系统设置中修改密码！")
    logger.info("=" * 50)
