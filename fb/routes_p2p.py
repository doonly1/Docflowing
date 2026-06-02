"""文件库 P2P 共享和节点管理"""

import time
import logging
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db
from fb.decorators import _require_fb_permission, _get_node_identity
from server import get_p2p_discovery

logger = logging.getLogger(__name__)

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


@fb_bp.route('/<fb_id>/share', methods=['POST'])
@login_required
@_require_fb_permission('manage')
def share_filebase(filebase_id):
    """将文件库共享给其他 P2P 节点"""
    data = request.get_json() or {}
    target_nodes = data.get('nodes', [])
    permission = (data.get('permission') or 'view').strip()

    if not target_nodes:
        return jsonify({'success': False, 'message': '请选择目标节点'})
    if permission not in ('view', 'edit', 'manage'):
        return jsonify({'success': False, 'message': '无效的权限级别'})

    db = get_db()
    row = db.execute("SELECT name, owner_id FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    fb_name = row['name']
    identity = _get_node_identity()
    if not identity:
        return jsonify({'success': False, 'message': '节点身份未初始化'})

    owner_addr = f'{identity.node_id}:{identity.port}'

    now = time.time()
    success_count = 0
    for node in target_nodes:
        node_id = node.get('node_id', '')
        node_name = node.get('display_name', '')
        node_addr = node.get('addr', '')

        if not node_id or not node_addr:
            continue

        host = node_addr.split(':')[0] if ':' in node_addr else node_addr
        owner_full_addr = f'{host}:{identity.port}'

        try:
            import requests
            notify_url = f'http://{node_addr}/p2p/share/notify'
            resp = requests.post(notify_url, json={
                'fb_id': filebase_id,
                'fb_name': fb_name,
                'owner_addr': owner_full_addr,
                'permission': permission,
                'node_id': identity.node_id,
                'node_name': identity.display_name,
                'node_public_key': identity.get_public_key_b64()
            }, timeout=10)
            if resp.ok:
                success_count += 1
        except Exception as e:
            logger.warning("Failed to notify node %s: %s", node_addr, e)

        db.execute(
            "INSERT OR REPLACE INTO shared_nodes (filebase_id, node_id, node_name, node_addr, permission_level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (filebase_id, node_id, node_name, node_addr, permission, now)
        )

    db.commit()

    return jsonify({
        'success': True,
        'message': f'已共享给 {success_count}/{len(target_nodes)} 个节点',
        'shared_count': success_count,
        'total': len(target_nodes)
    })


@fb_bp.route('/<fb_id>/shared-nodes', methods=['GET'])
@login_required
@_require_fb_permission('manage')
def list_shared_nodes(filebase_id):
    """获取文件库已共享的节点列表"""
    db = get_db()
    rows = db.execute(
        "SELECT node_id, node_name, node_addr, permission_level, created_at FROM shared_nodes WHERE filebase_id = ? ORDER BY created_at DESC",
        (filebase_id,)
    ).fetchall()

    nodes = []
    for r in rows:
        nodes.append({
            'node_id': r['node_id'],
            'node_name': r['node_name'],
            'node_addr': r['node_addr'],
            'permission': r['permission_level'],
            'created_at': r['created_at']
        })

    return jsonify({'success': True, 'nodes': nodes})


@fb_bp.route('/<fb_id>/shared-nodes/<node_id>', methods=['DELETE'])
@login_required
@_require_fb_permission('manage')
def revoke_share(filebase_id, node_id):
    """撤销对某个节点的共享"""
    db = get_db()
    db.execute("DELETE FROM shared_nodes WHERE filebase_id = ? AND node_id = ?", (filebase_id, node_id))
    db.commit()

    row = db.execute("SELECT node_addr FROM shared_nodes WHERE filebase_id = ? AND node_id = ?",
                     (filebase_id, node_id)).fetchone()
    if row:
        node_addr = row['node_addr']
        try:
            import requests
            identity = _get_node_identity()
            from p2p.proxy import _sign_request
            if identity:
                headers = _sign_request(identity, 'DELETE', f'/p2p/fb/{filebase_id}/revoke')
                requests.delete(f'http://{node_addr}/p2p/fb/{filebase_id}/revoke',
                                headers=headers, timeout=10)
        except Exception:
            pass

    return jsonify({'success': True, 'message': '共享已撤销'})


@fb_bp.route('/share-batch', methods=['POST'])
@login_required
def batch_share():
    """一键共享给所有在线节点"""
    data = request.get_json() or {}
    fb_id = data.get('fb_id', '')
    permission = (data.get('permission') or 'view').strip()
    all_nodes = data.get('all_nodes', [])

    if not fb_id or not all_nodes:
        return jsonify({'success': False, 'message': '参数不完整'})

    db = get_db()
    row = db.execute("SELECT owner_id FROM filebases WHERE id = ?", (fb_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    identity = _get_node_identity()
    if not identity:
        return jsonify({'success': False, 'message': '节点身份未初始化'})

    fb_row = db.execute("SELECT name FROM filebases WHERE id = ?", (fb_id,)).fetchone()
    fb_name = fb_row['name'] if fb_row else ''
    owner_addr = f'{identity.node_id}:{identity.port}'
    now = time.time()

    success_count = 0
    for node in all_nodes:
        node_id = node.get('node_id', '')
        node_name = node.get('display_name', '')
        node_addr = node.get('addr', '')
        if not node_id or not node_addr:
            continue
        try:
            import requests
            host = node_addr.split(':')[0] if ':' in node_addr else node_addr
            notify_url = f'http://{node_addr}/p2p/share/notify'
            resp = requests.post(notify_url, json={
                'fb_id': fb_id,
                'fb_name': fb_name,
                'owner_addr': f'{host}:{identity.port}',
                'permission': permission,
                'node_id': identity.node_id,
                'node_name': identity.display_name,
                'node_public_key': identity.get_public_key_b64()
            }, timeout=10)
            if resp.ok:
                success_count += 1
        except Exception as e:
            logger.warning("batch share failed for %s: %s", node_addr, e)

        db.execute(
            "INSERT OR REPLACE INTO shared_nodes (filebase_id, node_id, node_name, node_addr, permission_level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fb_id, node_id, node_name, node_addr, permission, now)
        )
    db.commit()

    return jsonify({
        'success': True,
        'message': f'已共享给 {success_count}/{len(all_nodes)} 个在线节点',
        'shared_count': success_count,
        'total': len(all_nodes)
    })


@fb_bp.route('/p2p/node', methods=['GET'])
@login_required
def get_p2p_node_info():
    """获取本机 P2P 节点身份信息"""
    identity = _get_node_identity()
    if not identity:
        return jsonify({'success': False, 'message': '节点身份未初始化'})

    return jsonify({
        'success': True,
        'node_id': identity.node_id,
        'display_name': identity.display_name,
        'port': identity.port,
    })


@fb_bp.route('/p2p/node', methods=['PUT'])
@login_required
def update_p2p_node_info():
    """更新本机 P2P 节点身份配置"""
    data = request.get_json() or {}
    display_name = (data.get('display_name') or '').strip()
    port = data.get('port')

    identity = _get_node_identity()
    if not identity:
        return jsonify({'success': False, 'message': '节点身份未初始化'})

    changed = False
    if display_name and display_name != identity.display_name:
        identity.display_name = display_name
        changed = True
    if port is not None:
        try:
            new_port = int(port)
            if new_port < 1024 or new_port > 65535:
                return jsonify({'success': False, 'message': '端口号范围 1024-65535'})
            if new_port != identity.port:
                identity.port = new_port
                changed = True
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': '端口号无效'})

    if changed:
        if not identity.save_config():
            return jsonify({'success': False, 'message': '配置保存失败'})
        try:
            discovery = get_p2p_discovery()
            if discovery:
                discovery.stop()
                discovery.display_name = identity.display_name
                discovery.port = identity.port
                discovery.start()
        except Exception as e:
            logger.warning("Failed to restart P2P discovery: %s", e)

    return jsonify({'success': True, 'message': '配置已更新'})


@fb_bp.route('/p2p/discovered-nodes', methods=['GET'])
@login_required
def get_discovered_nodes():
    """获取局域网发现的其他 P2P 节点"""
    discovery = get_p2p_discovery()
    if not discovery:
        return jsonify({'success': True, 'nodes': []})

    nodes = discovery.get_discovered_nodes()
    return jsonify({'success': True, 'nodes': nodes})
