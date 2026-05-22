import hashlib

from functools import wraps
from flask import request, jsonify, g

from .node import verify_signature
from .models import TrustStore
from logging_config import get_logger

logger = get_logger(__name__)


def p2p_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        node_id = request.headers.get('X-Node-ID', '')
        sig_b64 = request.headers.get('X-Node-Sig', '')

        if not node_id or not sig_b64:
            return jsonify({'success': False, 'message': '缺少节点认证信息'}), 401

        trust_store = TrustStore()
        pub_key = trust_store.get_public_key(node_id)
        if not pub_key:
            return jsonify({'success': False, 'message': '未信任的节点'}), 403

        # 签名覆盖 method:path:body_hash，防止请求体被篡改
        body = request.get_data()
        body_hash = hashlib.sha256(body).hexdigest() if body else ''
        sign_data = f'{request.method}:{request.path}:{body_hash}'.encode()

        if not verify_signature(pub_key, sign_data, sig_b64):
            # 向后兼容：旧版签名不包含 body_hash
            old_sign_data = f'{request.method}:{request.path}'.encode()
            if not verify_signature(pub_key, old_sign_data, sig_b64):
                return jsonify({'success': False, 'message': '签名验证失败'}), 403

        g.remote_node_id = node_id
        return f(*args, **kwargs)
    return decorated