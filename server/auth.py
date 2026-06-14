"""简化认证系统 — 单用户桌面版，以本机 node_id 为用户标识"""

from functools import wraps

from flask import Blueprint, request, jsonify, g

auth_bp = Blueprint('auth', __name__)

# 缓存，避免每次请求都重新加载 YAML
_node_id: str | None = None


def _get_node_id() -> str:
    global _node_id
    if _node_id:
        return _node_id

    from server import get_node_identity
    nid = get_node_identity()
    if nid:
        _node_id = nid.node_id
        return _node_id

    from p2p.node import NodeIdentity
    _node_id = NodeIdentity().load_or_create().node_id
    return _node_id


def _get_real_ip() -> str:
    """获取真实客户端 IP，优先从 X-Forwarded-For 解析（反向代理场景）"""
    xff = request.headers.get('X-Forwarded-For', '').strip()
    if xff:
        # X-Forwarded-For 格式: client_ip, proxy1_ip, proxy2_ip, ...
        return xff.split(',')[0].strip()
    return request.remote_addr or ''


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        remote_ip = _get_real_ip()
        if remote_ip in ('127.0.0.1', '::1', 'localhost'):
            g.user_id = _get_node_id()
            return f(*args, **kwargs)

        return jsonify({'success': False, 'message': '仅允许本机访问'}), 403
    return decorated


@auth_bp.route('/api/user/me', methods=['GET'])
@login_required
def api_user_me():
    nid = _get_node_id()
    return jsonify({
        'success': True,
        'username': 'admin',
        'role': 'admin',
        'user_id': nid
    })
