"""文件库 KB 同步管理"""

import os
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db
from fb.decorators import _require_fb_permission, require_fb_perm
from fb.routes_base import _count_files_on_disk

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


def _toggle_fb_sync_visibility(filebase_id, visible):
    """切换同步数据在 KB 中的可见性（当前请求上下文）"""
    from flask import g
    _update_kb_path_prefix(g.user_id, filebase_id, visible)


def _update_kb_path_prefix(user_id, filebase_id, visible):
    """重命名 KB 路径前缀：imported/ ↔ _disabled/（指定用户），
    两条 UPDATE 在同一事务中，失败整体回滚，避免出现"半更新"状态"""
    try:
        from kb.database import get_db as get_kb_db
        conn = get_kb_db(user_id)
        if visible:
            old_prefix = f'_disabled/{filebase_id}/'
            new_prefix = f'imported/{filebase_id}/'
        else:
            old_prefix = f'imported/{filebase_id}/'
            new_prefix = f'_disabled/{filebase_id}/'

        try:
            # sqlite3 在遇到 DML 时自动开启事务；这里确保两条 UPDATE 在同一事务中整体提交/回滚
            conn.execute(
                "UPDATE wiki_files SET path = REPLACE(path, ?, ?) WHERE usr_id = ? AND path LIKE ?",
                (old_prefix, new_prefix, user_id, old_prefix + '%')
            )
            conn.execute(
                "UPDATE wiki_fts SET path = REPLACE(path, ?, ?) WHERE usr_id = ? AND path LIKE ?",
                (old_prefix, new_prefix, user_id, old_prefix + '%')
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    except Exception:
        import logging
        logging.getLogger(__name__).exception(f"Failed to toggle visibility for {filebase_id}")


def _trigger_fb_sync(filebase_id):
    """触发文件库同步"""
    try:
        from kb.sync_worker import get_sync_worker
        from flask import g
        worker = get_sync_worker()
        worker._trigger_sync(g.user_id, filebase_id)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(f"Failed to trigger sync for {filebase_id}")


@fb_bp.route('/<fb_id>/sync', methods=['POST'])
@login_required
@require_fb_perm('manage')
def toggle_sync(filebase_id):
    """切换文件库同步状态"""
    data = request.get_json() or {}
    enabled = bool(data.get('enabled', False))

    db = get_db()
    kb_row = db.execute("SELECT owner_id FROM filebases WHERE id = ?", (filebase_id,)).fetchone()

    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'}), 404

    if kb_row['owner_id'] != g.user_id:
        return jsonify({'success': False, 'message': '只有文件库所有者可以管理同步'}), 403

    db.execute("UPDATE filebases SET is_synced_to_kb = ? WHERE id = ?", (1 if enabled else 0, filebase_id))
    db.commit()

    _toggle_fb_sync_visibility(filebase_id, enabled)

    if enabled:
        _trigger_fb_sync(filebase_id)

    return jsonify({'success': True, 'enabled': enabled})


@fb_bp.route('/<fb_id>/sync-now', methods=['POST'])
@login_required
@require_fb_perm('manage')
def sync_now(filebase_id):
    """手动触发立即同步"""
    db = get_db()
    kb_row = db.execute("SELECT owner_id, is_synced_to_kb FROM filebases WHERE id = ?", (filebase_id,)).fetchone()

    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'}), 404

    if kb_row['owner_id'] != g.user_id:
        return jsonify({'success': False, 'message': '只有文件库所有者可以触发同步'}), 403

    if not kb_row['is_synced_to_kb']:
        return jsonify({'success': False, 'message': '请先启用同步功能'}), 400

    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()
        worker.trigger_sync_now(g.user_id, filebase_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to trigger sync: {e}")

    return jsonify({'success': True, 'message': '同步已触发'})


@fb_bp.route('/<fb_id>/sync-status', methods=['GET'])
@login_required
@require_fb_perm('view')
def get_sync_status(filebase_id):
    """获取同步状态"""
    db = get_db()
    kb_row = db.execute("SELECT owner_id, is_synced_to_kb, local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()

    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'}), 404

    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()

        from kb.sync_state import get_sync_state_manager
        state_manager = get_sync_state_manager()
        state = state_manager.load_state(kb_row['owner_id'], filebase_id)

        stats = worker.get_filebase_stats(filebase_id)
        if stats:
            total_files = stats['total_files']
            syncable_count = stats['syncable_files']
        elif state.total_files > 0:
            total_files = state.total_files
            syncable_count = state.syncable_files
        else:
            # 兜底：直接扫描磁盘
            total_files = _count_files_on_disk(filebase_id, kb_row['owner_id'])
            syncable_count = total_files

        is_syncing = filebase_id in worker._processing_filebases
        try:
            failed_count = len(state.failed_files or [])
        except Exception:
            failed_count = 0

        return jsonify({
            'success': True,
            'enabled': bool(kb_row['is_synced_to_kb']),
            'is_owner': kb_row['owner_id'] == g.user_id,
            'is_syncing': is_syncing,
            'status': {
                'total_files': total_files,
                'syncable_files': syncable_count,
                'synced_files': state.synced_files,
                'failed_count': failed_count,
                'last_sync': state.last_sync
            }
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to get sync status: {e}")
        return jsonify({
            'success': True,
            'enabled': bool(kb_row['is_synced_to_kb']),
            'is_owner': kb_row['owner_id'] == g.user_id,
            'is_syncing': False,
            'status': {
                'total_files': 0,
                'syncable_files': 0,
                'synced_files': 0,
                'failed_count': 0,
                'last_sync': None
            }
        })
