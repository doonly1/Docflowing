"""文件库基础 CRUD 功能"""

import os
import uuid
import time
import shutil
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db, get_visible_fb_ids
from fb.decorators import _require_fb_permission, _is_admin

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


def _get_user_workspace(user_id=None):
    """获取用户工作空间目录"""
    try:
        import platform
        system = platform.system()
        desktop = None

        if system == 'Windows':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
            desktop, _ = winreg.QueryValueEx(key, 'Desktop')
            winreg.CloseKey(key)
            desktop = os.path.expandvars(desktop)
        else:
            desktop = os.environ.get('XDG_DESKTOP_DIR')
            if not desktop:
                user_dirs = os.path.join(os.path.expanduser('~'), '.config', 'user-dirs.dirs')
                if os.path.exists(user_dirs):
                    with open(user_dirs, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip().startswith('XDG_DESKTOP_DIR'):
                                desktop = line.split('=', 1)[1].strip().strip('"')
                                desktop = os.path.expandvars(desktop)
                                break
                if not desktop:
                    home = os.path.expanduser('~')
                    for name in ('Desktop', '桌面'):
                        candidate = os.path.join(home, name)
                        if os.path.isdir(candidate):
                            desktop = candidate
                            break

        if desktop and os.path.isdir(desktop):
            return desktop
    except Exception:
        pass

    return os.path.expanduser('~')


@fb_bp.route('/create-folder', methods=['POST'])
@login_required
def create_folder():
    """创建文件库"""
    user_id = g.user_id
    data = request.get_json()
    filebase_type = (data.get('filebase_type') or 'local').strip()
    name = (data.get('name') or '').strip()
    local_path = (data.get('local_path') or '').strip()

    if filebase_type == 'net':
        network_path = (data.get('network_path') or data.get('local_path') or '').strip()
        if not network_path:
            return jsonify({'success': False, 'message': '网络路径不能为空'})

        if not name:
            return jsonify({'success': False, 'message': '网络文件库名称不能为空'})

        db = get_db()
        filebase_id = str(uuid.uuid4())
        now = time.time()
        db.execute(
            "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at) VALUES (?, ?, ?, 'net', ?, ?)",
            (filebase_id, name, user_id, network_path, now)
        )
        db.execute(
            "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
            (filebase_id, user_id, 'manage')
        )
        db.commit()

        return jsonify({
            'success': True,
            'fb': {'id': filebase_id, 'name': name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'net',
                   'local_path': network_path}
        })

    if not local_path:
        if not name:
            return jsonify({'success': False, 'message': '请输入文件库名称'})
        ws = _get_user_workspace(user_id)
        local_path = os.path.join(ws, name)
        os.makedirs(local_path, exist_ok=True)
        folder_name = name
    else:
        if not os.path.isdir(local_path):
            return jsonify({'success': False, 'message': '目录不存在或无效'})
        folder_name = os.path.basename(local_path.rstrip('/\\'))
        if not folder_name:
            return jsonify({'success': False, 'message': '无效的目录路径'})

    db = get_db()
    filebase_id = str(uuid.uuid4())
    now = time.time()

    existing = db.execute(
        "SELECT id FROM filebases WHERE owner_id = ? AND local_path = ?",
        (user_id, local_path)
    ).fetchone()
    if existing:
        return jsonify({'success': False, 'message': '该目录已在文件库中'})

    db.execute(
        "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at) VALUES (?, ?, ?, 'local', ?, ?)",
        (filebase_id, folder_name, user_id, local_path, now)
    )
    db.execute(
        "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
        (filebase_id, user_id, 'manage')
    )
    db.commit()

    return jsonify({
        'success': True,
        'fb': {'id': filebase_id, 'name': folder_name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'local',
               'local_path': local_path}
    })


@fb_bp.route('/copy-folder', methods=['POST'])
@login_required
def copy_folder():
    """复制文件库"""
    user_id = g.user_id
    data = request.get_json()
    filebase_id = (data.get('fb_id') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not filebase_id or not new_name:
        return jsonify({'success': False, 'message': '参数不完整'})

    db = get_db()
    kb_row = db.execute("SELECT * FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '源文件库不存在'})

    src_path = kb_row['local_path']
    if not os.path.isdir(src_path):
        return jsonify({'success': False, 'message': '源目录不存在'})

    ws = _get_user_workspace(user_id)
    dst_path = os.path.join(ws, new_name)

    counter = 1
    orig_name = new_name
    while os.path.exists(dst_path) and counter < 100:
        new_name = orig_name + '_' + str(counter)
        dst_path = os.path.join(ws, new_name)
        counter += 1
    if os.path.exists(dst_path):
        return jsonify({'success': False, 'message': '无法生成唯一的名称'})

    try:
        shutil.copytree(src_path, dst_path)
    except Exception as e:
        return jsonify({'success': False, 'message': '复制目录失败: ' + str(e)})

    new_filebase_id = str(uuid.uuid4())
    now = time.time()
    db.execute(
        "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at) VALUES (?, ?, ?, 'local', ?, ?)",
        (new_filebase_id, new_name, user_id, dst_path, now)
    )
    db.execute(
        "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
        (new_filebase_id, user_id, 'manage')
    )
    db.commit()

    return jsonify({
        'success': True,
        'fb': {'id': new_filebase_id, 'name': new_name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'local', 'local_path': dst_path}
    })


_list_fb_cache = {}
_list_fb_cache_time = 0
_LIST_FB_CACHE_TTL = 5


@fb_bp.route('/list', methods=['GET'])
@login_required
def list_fb():
    """获取文件库列表"""
    global _list_fb_cache_time
    user_id = g.user_id

    cache_key = f"list_fb:{user_id}"
    now = time.time()
    if cache_key in _list_fb_cache and now - _list_fb_cache_time < _LIST_FB_CACHE_TTL:
        return jsonify(_list_fb_cache[cache_key])

    is_admin = _is_admin(user_id)
    db = get_db()
    ws = _get_user_workspace(user_id)

    db_kbs = {}
    rows = db.execute("SELECT * FROM filebases").fetchall()
    for row in rows:
        db_kbs[row['local_path']] = row

    local_existing_paths = set()
    for row in rows:
        if row['filebase_type'] != 'net':
            local_existing_paths.add(row['local_path'])

    fs_paths = set()

    try:
        ws_entries = sorted(os.listdir(ws))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning('无法扫描工作空间 %s: %s', ws, e)
        ws_entries = []

    for entry_name in ws_entries:
        if entry_name.startswith('.') or entry_name == 'trash':
            continue
        entry_path = os.path.join(ws, entry_name)
        if os.path.isdir(entry_path):
            fs_paths.add(entry_path)
            if entry_path not in db_kbs:
                filebase_id = str(uuid.uuid4())
                now = time.time()
                db.execute(
                    "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at) VALUES (?, ?, ?, 'local', ?, ?)",
                    (filebase_id, entry_name, user_id, entry_path, now)
                )
                db.execute(
                    "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
                    (filebase_id, user_id, 'manage')
                )
            else:
                row = db_kbs[entry_path]
                if row['filebase_type'] != 'net' and row['name'] != entry_name:
                    db.execute("UPDATE filebases SET name = ? WHERE id = ?", (entry_name, row['id']))

    for path in local_existing_paths - fs_paths:
        row = db_kbs[path]
        if path.startswith(ws + os.sep) or path == ws:
            db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (row['id'],))
            db.execute("DELETE FROM filebases WHERE id = ?", (row['id'],))
    db.commit()

    if is_admin:
        visible_rows = db.execute("SELECT * FROM filebases").fetchall()
    else:
        visible_ids = get_visible_fb_ids(user_id, False)
        visible_rows = []
        for filebase_id in visible_ids:
            r = db.execute("SELECT * FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
            if r:
                visible_rows.append(r)

    # 批量查询所有本地文件库的文件数（避免 N+1 SQL + 全量 JSON 解析）
    fb_file_counts = {}
    local_fb_ids = [(row['id'], row['owner_id']) for row in visible_rows if row['filebase_type'] not in ('net', 'remote')]
    if local_fb_ids:
        try:
            conditions = []
            params = []
            for fb_id, owner_id in local_fb_ids:
                conditions.append('(filebase_id = ? AND user_id = ?)')
                params.extend([fb_id, owner_id])
            batch_sql = f"""SELECT filebase_id, json_extract(state_json, '$.total_files') AS total_files
                FROM filebase_sync_states
                WHERE {' OR '.join(conditions)}"""
            for r in db.execute(batch_sql, params).fetchall():
                fb_file_counts[r['filebase_id']] = r['total_files'] or 0
        except Exception:
            import logging
            logging.getLogger(__name__).warning('批量查询文件数失败，使用逐个回退')

    kbs = []
    for row in visible_rows:
        perm_row = db.execute(
            "SELECT permission_level FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
            (row['id'], user_id)
        ).fetchone()
        permission = 'manage' if row['owner_id'] == user_id or is_admin else (
            perm_row['permission_level'] if perm_row else 'view'
        )

        owner_username = row['owner_id'][:8]

        local_path = row['local_path']
        display_path = local_path
        if local_path:
            norm = os.path.normpath(local_path)
            parts = norm.split(os.sep)
            try:
                ws_idx = [p.lower() for p in parts].index('workspaces')
                if ws_idx + 2 < len(parts):
                    parts[ws_idx + 1] = owner_username
                path_parts = parts[ws_idx + 1:]
                display_path = '/'.join(path_parts)
            except ValueError:
                pass

        kbs.append({
            'id': row['id'],
            'name': row['name'],
            'owner_id': row['owner_id'],
            'owner_username': owner_username,
            'display_path': display_path,
            'created_at': row['created_at'],
            'permission': permission,
            'filebase_type': row['filebase_type'] or 'local',
            'local_path': local_path,
            'total_files': fb_file_counts.get(row['id'], _get_fb_file_count(row['id'], row['owner_id']))
        })

    from p2p.models import RemoteFilebaseStore, TrustStore
    remote_store = RemoteFilebaseStore()
    trust_store = TrustStore()
    for fb_id, fb_info in remote_store.get_all().items():
        owner_node = trust_store.get_node_info(fb_info['owner_node_id'])
        owner_name = owner_node['display_name'] if owner_node else fb_info['owner_node_id'][:8]
        kbs.append({
            'id': fb_id,
            'name': f'[远程] {owner_name}/{fb_info["name"]}',
            'owner_id': fb_info['owner_node_id'],
            'owner_username': owner_name,
            'display_path': f'远程节点: {fb_info["owner_addr"]}',
            'created_at': fb_info.get('created_at', 0),
            'permission': fb_info['permission'],
            'filebase_type': 'remote',
            'local_path': ''
        })

    result = {'success': True, 'kbs': kbs}
    _list_fb_cache[cache_key] = result
    _list_fb_cache_time = now
    return jsonify(result)


def _get_fb_file_count(filebase_id: str, owner_id: str) -> int:
    """获取文件库的文件总数，优先使用同步缓存，回退到数据库持久化状态"""
    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()
        stats = worker.get_filebase_stats(filebase_id)
        if stats:
            return stats['total_files']
    except Exception:
        pass
    try:
        from kb.sync_state import get_sync_state_manager
        state_manager = get_sync_state_manager()
        state = state_manager.load_state(owner_id, filebase_id)
        return state.total_files or 0
    except Exception:
        return 0


@fb_bp.route('/<fb_id>', methods=['PUT'])
@login_required
@_require_fb_permission('manage')
def rename_fb(filebase_id):
    """重命名文件库"""
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '名称不能为空'})

    db = get_db()
    kb_row = db.execute("SELECT local_path, filebase_type FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    filebase_type = kb_row['filebase_type'] or 'local'
    old_path = kb_row['local_path']

    if filebase_type == 'net':
        db.execute("UPDATE filebases SET name = ? WHERE id = ?", (name, filebase_id))
        db.commit()
        return jsonify({'success': True, 'message': '重命名成功'})

    parent_dir = os.path.dirname(old_path)
    new_path = os.path.join(parent_dir, name)

    if os.path.exists(new_path):
        return jsonify({'success': False, 'message': '同名目录已存在'})

    try:
        os.rename(old_path, new_path)
    except Exception as e:
        return jsonify({'success': False, 'message': '重命名目录失败: ' + str(e)})

    db.execute("UPDATE filebases SET name = ?, local_path = ? WHERE id = ?", (name, new_path, filebase_id))
    db.commit()
    return jsonify({'success': True, 'message': '重命名成功'})


def _cleanup_synced_data(user_id, filebase_id):
    """删除文件库时清理 KB 中的同步数据"""
    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()
        worker.cleanup_filebase(user_id, filebase_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to cleanup synced data: {e}")


@fb_bp.route('/<fb_id>', methods=['DELETE'])
@login_required
@_require_fb_permission('manage')
def delete_fb(filebase_id):
    """删除文件库"""
    db = get_db()
    row = db.execute("SELECT id, name, local_path, owner_id, filebase_type FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = row['local_path']
    filebase_type = row['filebase_type'] or 'local'
    trash_dir = _get_trash_dir()

    if filebase_type == 'net':
        db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
        db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
        db.commit()
        _cleanup_synced_data(row['owner_id'], filebase_id)
        return jsonify({'success': True, 'message': '网络文件库已移至回收站'})

    if local_path.startswith(trash_dir):
        if os.path.isdir(local_path):
            shutil.rmtree(local_path)
        db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
        db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
        db.commit()
        _cleanup_synced_data(row['owner_id'], filebase_id)
        return jsonify({'success': True, 'message': '文件库已彻底删除'})

    fb_name = row['name']
    timestamp = str(int(time.time()))
    target = os.path.join(trash_dir, fb_name + '_' + timestamp)
    os.makedirs(trash_dir, exist_ok=True)

    if os.path.isdir(local_path):
        shutil.move(local_path, target)

    db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
    db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
    db.commit()
    _cleanup_synced_data(row['owner_id'], filebase_id)
    return jsonify({'success': True, 'message': '文件库已移至trash目录'})


def _get_trash_dir():
    """获取回收站目录"""
    trash_dir = os.path.join(os.path.expanduser('~'), '.trash')
    os.makedirs(trash_dir, exist_ok=True)
    return trash_dir
