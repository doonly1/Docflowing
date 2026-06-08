"""文件库文件锁定管理"""

import time
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db
from fb.decorators import require_fb_perm, check_file_lock, _get_node_identity

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


@fb_bp.route('/<fb_id>/locks', methods=['GET'])
@login_required
@require_fb_perm('view')
def list_locks(filebase_id):
    """获取文件库中所有活跃的锁"""
    db = get_db()
    now = time.time()
    rows = db.execute(
        "SELECT id, path, locked_by, locked_at, expires_at FROM file_locks "
        "WHERE filebase_id = ? AND (expires_at IS NULL OR expires_at > ?)",
        (filebase_id, now)
    ).fetchall()

    locks = []
    for r in rows:
        locks.append({
            'id': r['id'],
            'path': r['path'],
            'locked_by': r['locked_by'],
            'locked_by_short': r['locked_by'][:8] if r['locked_by'] else '',
            'locked_at': r['locked_at'],
            'expires_at': r['expires_at'],
        })

    return jsonify({'success': True, 'locks': locks})


@fb_bp.route('/<fb_id>/locks', methods=['POST'])
@login_required
@require_fb_perm('edit')
def acquire_lock(filebase_id):
    """锁定一个文件"""
    data = request.get_json() or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({'success': False, 'message': '请指定文件路径'})

    user_id = g.user_id
    db = get_db()

    # Check if already locked by someone else
    existing = check_file_lock(filebase_id, path)
    if existing:
        if existing['locked_by'] != user_id:
            return jsonify({
                'success': False,
                'message': '文件已被 %s 锁定' % existing['locked_by'][:8],
                'locked': True,
                'locked_by': existing['locked_by'],
                'locked_at': existing['locked_at']
            }), 423
        else:
            # Already locked by current user, update timestamp
            now = time.time()
            expires_at = data.get('expires_at')
            db.execute(
                "UPDATE file_locks SET locked_at = ?, expires_at = ? WHERE filebase_id = ? AND path = ?",
                (now, expires_at, filebase_id, path)
            )
            db.commit()
            return jsonify({'success': True, 'message': '锁定已续期', 'locked_at': now})

    # Acquire new lock
    now = time.time()
    expires_at = data.get('expires_at')  # optional
    try:
        db.execute(
            "INSERT INTO file_locks (filebase_id, path, locked_by, locked_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (filebase_id, path, user_id, now, expires_at)
        )
        db.commit()
        return jsonify({'success': True, 'message': '文件已锁定', 'locked_at': now})
    except Exception as e:
        return jsonify({'success': False, 'message': '锁定失败: ' + str(e)}), 500


@fb_bp.route('/<fb_id>/locks', methods=['DELETE'])
@login_required
@require_fb_perm('edit')
def release_lock(filebase_id):
    """释放文件锁"""
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({'success': False, 'message': '请指定文件路径'})

    user_id = g.user_id
    db = get_db()

    # Check lock ownership
    lock_info = check_file_lock(filebase_id, path)
    if lock_info and lock_info['locked_by'] != user_id:
        from fb.decorators import _check_fb_perm_bits, PERM_BITS
        if not _check_fb_perm_bits(filebase_id, user_id, PERM_BITS['manage']):
            return jsonify({
                'success': False,
                'message': '只能解锁自己锁定的文件',
                'locked_by': lock_info['locked_by']
            }), 403

    db.execute(
        "DELETE FROM file_locks WHERE filebase_id = ? AND path = ?",
        (filebase_id, path)
    )
    db.commit()
    return jsonify({'success': True, 'message': '锁定已解除'})


@fb_bp.route('/<fb_id>/locks/check', methods=['GET'])
@login_required
@require_fb_perm('view')
def check_lock_status(filebase_id):
    """检查单个文件的锁定状态"""
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({'success': False, 'message': '请指定文件路径'})

    lock_info = check_file_lock(filebase_id, path)
    if lock_info:
        return jsonify({
            'success': True,
            'locked': True,
            'locked_by': lock_info['locked_by'],
            'locked_by_short': lock_info['locked_by'][:8] if lock_info['locked_by'] else '',
            'locked_at': lock_info['locked_at'],
            'expires_at': lock_info['expires_at'],
            'is_current_user': lock_info['locked_by'] == g.user_id,
        })
    else:
        return jsonify({
            'success': True,
            'locked': False,
        })
