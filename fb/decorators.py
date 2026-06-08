"""公共装饰器和工具函数"""

import os
import logging
from functools import wraps
from flask import request, jsonify, g

from server.auth import login_required
from fb.database import get_db, get_user_role, get_db as _get_db
from p2p.models import RemoteFilebaseStore

logger = logging.getLogger(__name__)

PERMISSION_LEVELS = {'view': 0, 'edit': 1, 'manage': 2}

# ---- Granular permission bits (bitmask) ----
PERM_BITS = {
    'view':     0b00000001,
    'create':   0b00000010,
    'edit':     0b00000100,
    'rename':   0b00001000,
    'move':     0b00010000,
    'copy':     0b00100000,
    'delete':   0b01000000,
    'manage':   0b10000000,
}

# Role templates for backward compatibility
ROLE_TEMPLATES = {
    'view':  PERM_BITS['view'],
    'edit':  PERM_BITS['view'] | PERM_BITS['create'] | PERM_BITS['edit'] | PERM_BITS['rename'] | PERM_BITS['move'] | PERM_BITS['copy'] | PERM_BITS['delete'],
    'manage': PERM_BITS['view'] | PERM_BITS['create'] | PERM_BITS['edit'] | PERM_BITS['rename'] | PERM_BITS['move'] | PERM_BITS['copy'] | PERM_BITS['delete'] | PERM_BITS['manage'],
}


def _is_remote_fb(filebase_id):
    """检查文件库是否为远程文件库（共享自其他节点）"""
    store = RemoteFilebaseStore()
    info = store.get(filebase_id)
    return info is not None, info


_node_identity = None


def _get_node_identity():
    """获取节点身份"""
    global _node_identity
    if _node_identity is None:
        from p2p.node import NodeIdentity
        _node_identity = NodeIdentity()
        _node_identity.load_or_create()
    return _node_identity


def _ensure_local_fb_route(f):
    """装饰器：对路由函数包装，如果文件库是远程则自动代理"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        fb_id = kwargs.get('filebase_id') or kwargs.get('fb_id', '')
        if fb_id:
            is_remote, remote_info = _is_remote_fb(fb_id)
            if is_remote and remote_info:
                g.is_remote_fb = True
                g.remote_fb_info = remote_info
            else:
                g.is_remote_fb = False
        return f(*args, **kwargs)
    return wrapper


def _check_fb_permission(filebase_id, user_id, required_level):
    """检查用户对指定文件库的权限（旧版字符串级别）"""
    if not user_id:
        return False
    if get_user_role(user_id) == 'admin':
        return True
    db = get_db()
    row = db.execute(
        "SELECT permission_level FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
        (filebase_id, user_id)
    ).fetchone()
    if row:
        actual = PERMISSION_LEVELS.get(row['permission_level'], -1)
        return actual >= PERMISSION_LEVELS.get(required_level, 0)
    kb_row = db.execute(
        "SELECT owner_id FROM filebases WHERE id = ?", (filebase_id,)
    ).fetchone()
    if kb_row and kb_row['owner_id'] == user_id:
        return True
    return False


def _require_fb_permission(required_level):
    """FB 专属权限校验装饰器，需在 @login_required 之后使用"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            user_id = g.user_id
            if not user_id:
                return jsonify({'success': False, 'message': '未登录，请先登录'}), 401

            fb_id = kwargs.pop('fb_id', None)
            if fb_id:
                kwargs['filebase_id'] = fb_id

            filebase_id = kwargs.get('filebase_id')
            if filebase_id and not _check_fb_permission(filebase_id, user_id, required_level):
                is_remote, remote_info = _is_remote_fb(filebase_id)
                if not is_remote:
                    return jsonify({'success': False, 'message': '权限不足'}), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


# ---- New granular permission check ----

def _check_fb_perm_bits(filebase_id, user_id, required_bits):
    """检查用户对文件库是否拥有指定的权限位（bitmask）"""
    if not user_id:
        return False
    if get_user_role(user_id) == 'admin':
        return True

    db = _get_db()

    # 1. Try perm_v2 first (granular bitmask)
    row = db.execute(
        "SELECT perm_mask FROM filebase_perm_v2 WHERE filebase_id = ? AND user_id = ?",
        (filebase_id, user_id)
    ).fetchone()
    if row:
        return (row['perm_mask'] & required_bits) == required_bits

    # 2. Fallback to old permission_level
    row = db.execute(
        "SELECT permission_level FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
        (filebase_id, user_id)
    ).fetchone()
    if row:
        level = row['permission_level']
        if level == 'manage':
            return (ROLE_TEMPLATES['manage'] & required_bits) == required_bits
        elif level == 'edit':
            return (ROLE_TEMPLATES['edit'] & required_bits) == required_bits
        elif level == 'view':
            return (ROLE_TEMPLATES['view'] & required_bits) == required_bits
        return False

    # 3. Check if user is owner (owner gets manage bits)
    kb_row = db.execute(
        "SELECT owner_id FROM filebases WHERE id = ?", (filebase_id,)
    ).fetchone()
    if kb_row and kb_row['owner_id'] == user_id:
        return (ROLE_TEMPLATES['manage'] & required_bits) == required_bits

    return False


def require_fb_perm(*required_perm_names, single_bit=True):
    """
    粒度权限校验装饰器工厂，需在 @login_required 之后使用。

    Parameters:
        required_perm_names: 权限名列表
        single_bit: True 时只需满足其一，False 时需同时满足全部
    """
    required_bits = 0
    for name in required_perm_names:
        bit = PERM_BITS.get(name)
        if bit is None:
            raise ValueError(f"Unknown permission name: {name}")
        required_bits |= bit

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            user_id = g.user_id
            if not user_id:
                return jsonify({'success': False, 'message': '未登录，请先登录'}), 401

            fb_id = kwargs.pop('fb_id', None)
            if fb_id:
                kwargs['filebase_id'] = fb_id

            filebase_id = kwargs.get('filebase_id')
            if filebase_id:
                has_perm = _check_fb_perm_bits(filebase_id, user_id, required_bits)
                if not has_perm:
                    is_remote, _ = _is_remote_fb(filebase_id)
                    if not is_remote:
                        return jsonify({'success': False, 'message': '权限不足'}), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


# ---- File Lock Functions ----

def check_file_lock(filebase_id, path):
    """检查指定文件是否被锁定。返回锁定信息字典或 None"""
    db = _get_db()
    row = db.execute(
        "SELECT id, locked_by, locked_at, expires_at FROM file_locks WHERE filebase_id = ? AND path = ?",
        (filebase_id, path)
    ).fetchone()
    if not row:
        return None

    # Check expiry
    if row['expires_at']:
        import time
        if time.time() > row['expires_at']:
            db.execute("DELETE FROM file_locks WHERE id = ?", (row['id'],))
            db.commit()
            return None

    return {
        'locked_by': row['locked_by'],
        'locked_at': row['locked_at'],
        'expires_at': row['expires_at'],
    }


def require_not_locked(f):
    """装饰器：检查请求中的文件路径是否被他人锁定"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        filebase_id = kwargs.get('filebase_id')
        if not filebase_id:
            return f(*args, **kwargs)

        path = ''
        if request.method == 'GET':
            path = request.args.get('path', '')
        else:
            data = request.get_json(silent=True) or {}
            for key in ('path', 'paths', 'sources'):
                val = data.get(key)
                if val:
                    if isinstance(val, list):
                        path = val[0] if val else ''
                    else:
                        path = val
                    break

        if path and filebase_id:
            lock_info = check_file_lock(filebase_id, path)
            if lock_info:
                return jsonify({
                    'success': False,
                    'message': f'文件已被 {lock_info["locked_by"][:8]} 锁定，无法操作',
                    'locked': True,
                    'locked_by': lock_info['locked_by'],
                    'locked_at': lock_info['locked_at']
                }), 423

        return f(*args, **kwargs)
    return decorated


def _is_admin(user_id):
    """检查用户是否为管理员"""
    return get_user_role(user_id) == 'admin'
