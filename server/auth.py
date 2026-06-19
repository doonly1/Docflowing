"""简化认证系统 — 单用户桌面版，以本机 node_id 为用户标识"""

import ipaddress
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
    """获取真实客户端 IP。

    桌面单用户场景下，所有请求都直接来自本机浏览器。为避免 X-Forwarded-For 请求头
    被滥用伪造 IP 来绕过认证，我们只信任 `request.remote_addr`（TCP 连接的真实远端 IP）。

    未来如果放在反向代理后部署，应改为：从可信代理链末尾提取 IP，并验证代理白名单。
    """
    return request.remote_addr or ""


def _is_loopback(ip_str: str) -> bool:
    """判断 IP 地址是否为回环地址（支持 IPv4、IPv6、IPv4-mapped IPv6）。"""
    if not ip_str:
        return False
    if ip_str == 'localhost':
        return True
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_loopback
    except ValueError:
        return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        remote_ip = _get_real_ip()
        if _is_loopback(remote_ip):
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
