"""公共装饰器和工具函数"""

import os
import logging
from functools import wraps
from flask import request, jsonify, g

from server.auth import login_required
from fb.database import get_db, get_user_role
from p2p.models import RemoteFilebaseStore

logger = logging.getLogger(__name__)

PERMISSION_LEVELS = {'view': 0, 'edit': 1, 'manage': 2}


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
    """检查用户对指定文件库的权限"""
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


def _is_admin(user_id):
    """检查用户是否为管理员"""
    return get_user_role(user_id) == 'admin'
