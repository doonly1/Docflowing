"""文件库回收站管理"""

import os
import uuid
import time
import shutil
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db
from fb.routes_base import _get_user_workspace, _get_trash_dir

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


@fb_bp.route('/trash', methods=['DELETE'])
@login_required
def clear_trash():
    """清空回收站"""
    user_id = g.user_id
    trash_dir = _get_trash_dir()
    if not os.path.isdir(trash_dir):
        return jsonify({'success': True, 'deleted': 0})

    db = get_db()
    trash_entries = list(os.listdir(trash_dir))
    for entry in trash_entries:
        entry_path = os.path.join(trash_dir, entry)
        try:
            db.execute(
                "DELETE FROM filebase_permissions WHERE filebase_id IN "
                "(SELECT id FROM filebases WHERE local_path = ?)",
                (entry_path,)
            )
            db.execute("DELETE FROM filebases WHERE local_path = ?", (entry_path,))
        except Exception:
            pass
    db.commit()

    count = 0
    for entry in trash_entries:
        entry_path = os.path.join(trash_dir, entry)
        try:
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
                count += 1
            elif os.path.isfile(entry_path):
                os.remove(entry_path)
                count += 1
        except Exception:
            pass

    return jsonify({'success': True, 'deleted': count, 'message': f'已清空 {count} 个项目'})


@fb_bp.route('/trash-list', methods=['GET'])
@login_required
def list_trash():
    """获取回收站列表"""
    user_id = g.user_id
    trash_dir = _get_trash_dir()
    if not os.path.isdir(trash_dir):
        return jsonify({'success': True, 'items': []})

    items = []
    for entry in os.listdir(trash_dir):
        entry_path = os.path.join(trash_dir, entry)
        if os.path.isdir(entry_path):
            stat = os.stat(entry_path)
            size = 0
            try:
                size = sum(os.path.getsize(os.path.join(r, f)) for r, ds, fs in os.walk(entry_path) for f in fs)
            except Exception:
                pass
            items.append({'name': entry, 'path': entry_path, 'mtime': stat.st_mtime, 'size': size})
    items.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify({'success': True, 'items': items})


@fb_bp.route('/trash-restore', methods=['POST'])
@login_required
def restore_from_trash():
    """从回收站恢复文件库"""
    user_id = g.user_id

    data = request.get_json()
    item_name = (data.get('name') or '').strip()
    if not item_name:
        return jsonify({'success': False, 'message': '未指定项目'})

    trash_dir = _get_trash_dir()
    src = os.path.join(trash_dir, item_name)
    if not os.path.isdir(src):
        return jsonify({'success': False, 'message': '项目不存在'})

    dst_name = item_name.rsplit('_', 1)[0] if '_' in item_name else item_name
    ws = _get_user_workspace(user_id)
    dst = os.path.join(ws, dst_name)
    orig_dst = dst
    counter = 1
    while os.path.exists(dst) and counter < 100:
        dst = orig_dst + '_' + str(counter)
        counter += 1
    if os.path.exists(dst):
        return jsonify({'success': False, 'message': '目标路径已存在'})

    shutil.move(src, dst)

    db = get_db()
    filebase_id = str(uuid.uuid4())
    now = time.time()
    name = os.path.basename(dst)
    db.execute(
        "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at) VALUES (?, ?, ?, 'local', ?, ?)",
        (filebase_id, name, user_id, dst, now)
    )
    db.execute(
        "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
        (filebase_id, user_id, 'manage')
    )
    db.commit()

    return jsonify({'success': True, 'fb': {'id': filebase_id, 'name': name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'local', 'local_path': dst}})


@fb_bp.route('/trash-item', methods=['DELETE'])
@login_required
def delete_trash_item():
    """永久删除回收站中的项目"""
    user_id = g.user_id

    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '未指定项目'})

    trash_dir = _get_trash_dir()
    target = os.path.join(trash_dir, name)
    if not os.path.exists(target):
        return jsonify({'success': False, 'message': '项目不存在'})

    if not target.startswith(os.path.normpath(trash_dir)):
        return jsonify({'success': False, 'message': '路径非法'})

    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': True})
