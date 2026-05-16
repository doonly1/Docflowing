import os
import sys
import uuid
import time
import zipfile
import io
import shutil
import tempfile
import subprocess
import json

from flask import Blueprint, request, jsonify, send_file, Response, g
from functools import wraps

from server.auth import login_required, admin_required, _get_auth_data_dir
from fb.database import get_db, get_visible_fb_ids, get_user_role

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')

PERMISSION_LEVELS = {'view': 0, 'edit': 1, 'manage': 2}


def _check_fb_permission(filebase_id, user_id, required_level):
    """检查用户对指定文件库的权限"""
    if not user_id:
        return False
    # 检查是否为管理员
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
                return jsonify({'success': False, 'message': '权限不足'}), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


# ==================== 文件库 CRUD ====================

def _get_user_workspace(user_id):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ws = os.path.join(root_dir, 'workspaces', user_id)
    os.makedirs(ws, exist_ok=True)
    return ws


@fb_bp.route('/create-folder', methods=['POST'])
@login_required
def create_folder():
    user_id = g.user_id
    data = request.get_json()
    filebase_type = (data.get('filebase_type') or 'local').strip()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '文件夹名称不能为空'})
    if len(name) > 64:
        return jsonify({'success': False, 'message': '文件夹名称不能超过64个字符'})
    if '/' in name or '\\' in name:
        return jsonify({'success': False, 'message': '文件夹名称不能包含路径分隔符'})

    # 网络文件库需要管理员权限
    if filebase_type == 'net':
        users_path = os.path.join(_get_auth_data_dir(), 'users.json')
        users = {}
        if os.path.exists(users_path):
            try:
                with open(users_path, 'r', encoding='utf-8') as f:
                    users = json.load(f)
            except Exception:
                pass
        user_info = users.get(user_id, {})
        role = user_info.get('role', 'viewer')
        if role != 'admin':
            return jsonify({'success': False, 'message': '需要管理员权限才能创建网络文件库'}), 403

    db = get_db()
    filebase_id = str(uuid.uuid4())
    now = time.time()

    if filebase_type == 'net':
        network_path = (data.get('network_path') or '').strip()
        if not network_path:
            return jsonify({'success': False, 'message': '网络路径不能为空'})

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

    ws = _get_user_workspace(user_id)
    local_path = os.path.join(ws, name)
    counter = 1
    orig_name = name
    while os.path.exists(local_path) and counter < 100:
        name = orig_name + '_' + str(counter)
        local_path = os.path.join(ws, name)
        counter += 1
    if os.path.exists(local_path):
        return jsonify({'success': False, 'message': '无法生成唯一的文件夹名称'})

    os.makedirs(local_path, exist_ok=True)

    db.execute(
        "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at) VALUES (?, ?, ?, 'local', ?, ?)",
        (filebase_id, name, user_id, local_path, now)
    )
    db.execute(
        "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
        (filebase_id, user_id, 'manage')
    )
    db.commit()

    return jsonify({
        'success': True,
        'fb': {'id': filebase_id, 'name': name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'local',
               'local_path': local_path}
    })


@fb_bp.route('/copy-folder', methods=['POST'])
@login_required
def copy_folder():
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


@fb_bp.route('/list', methods=['GET'])
@login_required
def list_fb():
    user_id = g.user_id
    is_admin = (get_user_role(user_id) == 'admin')
    db = get_db()
    ws = _get_user_workspace(user_id)

    import json
    users = {}
    try:
        users_path = os.path.join(_get_auth_data_dir(), 'users.json')
        if os.path.exists(users_path):
            with open(users_path, 'r', encoding='utf-8') as f:
                users = json.load(f)
    except Exception:
        pass

    db_kbs = {}
    rows = db.execute("SELECT * FROM filebases").fetchall()
    for row in rows:
        db_kbs[row['local_path']] = row

    # 分别处理本地文件库和网络文件库
    local_existing_paths = set()
    for row in rows:
        if row['filebase_type'] != 'net':
            local_existing_paths.add(row['local_path'])

    fs_paths = set()

    for entry_name in sorted(os.listdir(ws)):
        if entry_name.startswith('.') or entry_name == '已删除':
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

    # 删除不存在于文件系统的本地文件库
    for path in local_existing_paths - fs_paths:
        row = db_kbs[path]
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

    kbs = []
    for row in visible_rows:
        perm_row = db.execute(
            "SELECT permission_level FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
            (row['id'], user_id)
        ).fetchone()
        permission = 'manage' if row['owner_id'] == user_id or is_admin else (
            perm_row['permission_level'] if perm_row else 'view'
        )

        owner_info = users.get(row['owner_id'], {})
        owner_username = owner_info.get('username', row['owner_id'])

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
            'local_path': local_path
        })

    return jsonify({'success': True, 'kbs': kbs})


@fb_bp.route('/<fb_id>', methods=['PUT'])
@login_required
@_require_fb_permission('manage')
def rename_fb(filebase_id):
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

    # 网络文件库：只更新数据库记录，不操作文件系统
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


@fb_bp.route('/<fb_id>', methods=['DELETE'])
@login_required
@_require_fb_permission('manage')
def delete_fb(filebase_id):
    db = get_db()
    row = db.execute("SELECT id, name, local_path, owner_id, filebase_type FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = row['local_path']
    filebase_type = row['filebase_type'] or 'local'
    ws = _get_user_workspace(row['owner_id'])
    trash_dir = os.path.join(ws, '已删除')

    # 网络文件库：只删除数据库记录
    if filebase_type == 'net':
        db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
        db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
        db.commit()
        return jsonify({'success': True, 'message': '网络文件库已删除'})

    if local_path.startswith(trash_dir):
        if os.path.isdir(local_path):
            shutil.rmtree(local_path)
        db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
        db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
        db.commit()
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
    return jsonify({'success': True, 'message': '文件库已移至已删除目录'})


@fb_bp.route('/trash', methods=['DELETE'])
@login_required
def clear_trash():
    user_id = g.user_id
    ws = _get_user_workspace(user_id)
    trash_dir = os.path.join(ws, '已删除')
    if not os.path.isdir(trash_dir):
        return jsonify({'success': True, 'deleted': 0})

    count = 0
    for entry in os.listdir(trash_dir):
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
    user_id = g.user_id
    ws = _get_user_workspace(user_id)
    trash_dir = os.path.join(ws, '已删除')
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
    user_id = g.user_id

    data = request.get_json()
    item_name = (data.get('name') or '').strip()
    if not item_name:
        return jsonify({'success': False, 'message': '未指定项目'})

    ws = _get_user_workspace(user_id)
    trash_dir = os.path.join(ws, '已删除')
    src = os.path.join(trash_dir, item_name)
    if not os.path.isdir(src):
        return jsonify({'success': False, 'message': '项目不存在'})

    dst_name = item_name.rsplit('_', 1)[0] if '_' in item_name else item_name
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
    user_id = g.user_id

    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '未指定项目'})

    ws = _get_user_workspace(user_id)
    trash_dir = os.path.join(ws, '已删除')
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


@fb_bp.route('/<fb_id>/transfer', methods=['POST'])
@login_required
@_require_fb_permission('manage')
def transfer_fb(filebase_id):
    data = request.get_json()
    new_owner_id = (data.get('new_owner_id') or '').strip()
    keep_role = (data.get('keep_role') or 'editor').strip()

    if not new_owner_id:
        return jsonify({'success': False, 'message': '请指定新所有者'})
    if keep_role not in ('view', 'edit', 'manage'):
        keep_role = 'editor'

    db = get_db()
    kb_row = db.execute("SELECT owner_id FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    db.execute("UPDATE filebases SET owner_id = ? WHERE id = ?", (new_owner_id, filebase_id))

    db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?", (filebase_id, new_owner_id))
    db.execute("INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
               (filebase_id, new_owner_id, 'manage'))

    db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?", (filebase_id, g.user_id))
    db.execute("INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
               (filebase_id, g.user_id, keep_role))

    db.commit()
    return jsonify({'success': True, 'message': '所有权移交成功'})


# ==================== 成员权限管理 ====================

@fb_bp.route('/<fb_id>/members', methods=['GET'])
@login_required
@_require_fb_permission('view')
def list_members(filebase_id):
    import json
    users_path = os.path.join(_get_auth_data_dir(), 'users.json')
    users = {}
    if os.path.exists(users_path):
        with open(users_path, 'r', encoding='utf-8') as f:
            users = json.load(f)

    db = get_db()
    kb_row = db.execute("SELECT owner_id FROM filebases WHERE id = ?", (filebase_id,)).fetchone()

    members = []
    owner_id = kb_row['owner_id'] if kb_row else None
    if owner_id:
        owner_info = users.get(owner_id, {})
        members.append({
            'user_id': owner_id,
            'username': owner_info.get('username', ''),
            'permission': 'manage',
            'is_owner': True
        })

    perm_rows = db.execute(
        "SELECT user_id, permission_level FROM filebase_permissions WHERE filebase_id = ? AND user_id != ?",
        (filebase_id, owner_id or '')
    ).fetchall()

    for row in perm_rows:
        user_info = users.get(row['user_id'], {})
        members.append({
            'user_id': row['user_id'],
            'username': user_info.get('username', ''),
            'permission': row['permission_level'],
            'is_owner': False
        })

    return jsonify({'success': True, 'members': members})


@fb_bp.route('/<fb_id>/members', methods=['POST'])
@login_required
@_require_fb_permission('manage')
def add_member(filebase_id):
    import json
    users_path = os.path.join(_get_auth_data_dir(), 'users.json')
    users = {}
    if os.path.exists(users_path):
        with open(users_path, 'r', encoding='utf-8') as f:
            users = json.load(f)

    data = request.get_json()
    target_username = (data.get('username') or '').strip()
    permission = (data.get('permission') or 'view').strip()

    if permission not in ('view', 'edit', 'manage'):
        return jsonify({'success': False, 'message': '无效的权限级别'})

    target_user_id = None
    for uid, uinfo in users.items():
        if uinfo.get('username') == target_username:
            target_user_id = uid
            break

    if not target_user_id:
        return jsonify({'success': False, 'message': '用户不存在'})

    db = get_db()
    existing = db.execute(
        "SELECT * FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
        (filebase_id, target_user_id)
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE filebase_permissions SET permission_level = ? WHERE filebase_id = ? AND user_id = ?",
            (permission, filebase_id, target_user_id)
        )
    else:
        db.execute(
            "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
            (filebase_id, target_user_id, permission)
        )
    db.commit()

    return jsonify({'success': True, 'message': '成员已添加/更新'})


@fb_bp.route('/<fb_id>/members/<member_id>', methods=['PUT'])
@login_required
@_require_fb_permission('manage')
def update_member(filebase_id, member_id):
    data = request.get_json()
    permission = (data.get('permission') or 'view').strip()
    if permission not in ('view', 'edit', 'manage'):
        return jsonify({'success': False, 'message': '无效的权限级别'})

    db = get_db()
    db.execute(
        "UPDATE filebase_permissions SET permission_level = ? WHERE filebase_id = ? AND user_id = ?",
        (permission, filebase_id, member_id)
    )
    db.commit()
    return jsonify({'success': True, 'message': '权限已更新'})


@fb_bp.route('/<fb_id>/members/<member_id>', methods=['DELETE'])
@login_required
@_require_fb_permission('manage')
def remove_member(filebase_id, member_id):
    db = get_db()
    db.execute(
        "DELETE FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
        (filebase_id, member_id)
    )
    db.commit()
    return jsonify({'success': True, 'message': '成员已移除'})


def _is_admin(user_id):
    """检查用户是否为管理员"""
    return get_user_role(user_id) == 'admin'


# ==================== 全文搜索 ====================

@fb_bp.route('/search', methods=['GET'])
@login_required
def search_documents():
    user_id = g.user_id
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'success': True, 'results': []})

    is_admin = _is_admin(user_id)
    visible_ids = get_visible_fb_ids(user_id, is_admin)
    if not visible_ids:
        return jsonify({'success': True, 'results': []})

    db = get_db()
    results = []
    keywords = q.lower().split()

    for filebase_id in visible_ids:
        kb_row = db.execute("SELECT name, filebase_type, local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
        if not kb_row:
            continue
        fb_name = kb_row['name'] or ''
        local_path = (kb_row['local_path'] if 'local_path' in kb_row.keys() else '') or ''

        if local_path and os.path.isdir(local_path):
            results.extend(_search_local_dir(local_path, filebase_id, fb_name, keywords))

    return jsonify({'success': True, 'results': results, 'query': q})


def _search_local_dir(base_path, filebase_id, fb_name, keywords):
    results = []
    try:
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith('~$')]
            for fname in files:
                if fname.startswith('~$'):
                    continue
                matched = False
                match_type = ''
                fname_lower = fname.lower()

                for kw in keywords:
                    if kw in fname_lower:
                        matched = True
                        match_type = 'filename'
                        break

                if not matched:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in ('.md', '.txt', '.html', '.htm', '.xml', '.json', '.csv'):
                        file_path = os.path.join(root, fname)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read().lower()
                            for kw in keywords:
                                if kw in content:
                                    matched = True
                                    match_type = 'content'
                                    break
                        except Exception:
                            pass

                if matched:
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, base_path).replace('\\', '/')
                    stat = os.stat(full_path)
                    results.append({
                        'document_id': rel_path,
                        'fb_id': filebase_id,
                        'fb_name': fb_name,
                        'filename': fname,
                        'file_type': os.path.splitext(fname)[1],
                        'file_size': stat.st_size,
                        'updated_at': stat.st_mtime,
                        'match_type': match_type,
                        'rel_path': rel_path
                    })
    except PermissionError:
        pass
    return results


# ==================== 本地目录浏览 ====================

def _resolve_local_path(db, filebase_id, subdir=''):
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return None, None
    local_path = kb_row['local_path']
    target = os.path.join(local_path, subdir) if subdir else local_path
    target = os.path.normpath(target)
    if not target.startswith(os.path.normpath(local_path)):
        return None, None
    return local_path, target


@fb_bp.route('/<fb_id>/local-files', methods=['POST'])
@login_required
@_require_fb_permission('edit')
def upload_local_files(filebase_id):
    db = get_db()
    subdir = request.args.get('subdir', '').strip()
    local_path, target_dir = _resolve_local_path(db, filebase_id, subdir)
    if local_path is None:
        return jsonify({'success': False, 'message': '文件库不存在或路径非法'})

    if not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    uploaded = []
    for key in request.files:
        for f in request.files.getlist(key):
            if not f.filename:
                continue
            file_path = os.path.join(target_dir, f.filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            f.save(file_path)
            stat = os.stat(file_path)
            uploaded.append({
                'name': f.filename,
                'size': stat.st_size,
                'mtime': stat.st_mtime
            })

    return jsonify({'success': True, 'uploaded': uploaded})


@fb_bp.route('/<fb_id>/local-files/dir', methods=['POST'])
@login_required
@_require_fb_permission('edit')
def create_local_dir(filebase_id):
    db = get_db()
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    parent = (data.get('parent') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '目录名不能为空'})
    if '/' in name or '\\' in name:
        return jsonify({'success': False, 'message': '目录名不能包含路径分隔符'})

    local_path, target_dir = _resolve_local_path(db, filebase_id, parent)
    if local_path is None:
        return jsonify({'success': False, 'message': '文件库不存在或路径非法'})

    new_dir = os.path.join(target_dir, name)
    counter = 1
    orig_name = name
    while os.path.exists(new_dir) and counter < 100:
        name = orig_name + '_' + str(counter)
        new_dir = os.path.join(target_dir, name)
        counter += 1
    if os.path.exists(new_dir):
        return jsonify({'success': False, 'message': '无法生成唯一的目录名称'})

    os.makedirs(new_dir, exist_ok=True)
    rel = os.path.relpath(new_dir, local_path).replace('\\', '/')
    return jsonify({'success': True, 'path': rel})


@fb_bp.route('/<fb_id>/local-files/create', methods=['POST'])
@login_required
@_require_fb_permission('edit')
def create_local_file(filebase_id):
    db = get_db()
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    parent = (data.get('parent') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '文件名不能为空'})
    if '/' in name or '\\' in name:
        return jsonify({'success': False, 'message': '文件名不能包含路径分隔符'})

    local_path, target_dir = _resolve_local_path(db, filebase_id, parent)
    if local_path is None:
        return jsonify({'success': False, 'message': '文件库不存在或路径非法'})

    filename = name if name.lower().endswith('.md') else name + '.md'
    file_path = os.path.join(target_dir, filename)

    counter = 1
    orig_name = name if not name.lower().endswith('.md') else name[:-3]
    while os.path.exists(file_path) and counter < 100:
        filename = orig_name + '_' + str(counter) + '.md'
        file_path = os.path.join(target_dir, filename)
        counter += 1
    if os.path.exists(file_path):
        return jsonify({'success': False, 'message': '无法生成唯一的文件名'})

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('')
    rel = os.path.relpath(file_path, local_path).replace('\\', '/')
    return jsonify({'success': True, 'path': rel})


@fb_bp.route('/<fb_id>/local-files/content', methods=['PUT'])
@login_required
@_require_fb_permission('edit')
def save_local_file_content(filebase_id):
    db = get_db()
    data = request.get_json() or {}
    path = (data.get('path') or '').strip()
    content = data.get('content', '')

    if not path:
        return jsonify({'success': False, 'message': '未指定文件路径'})

    local_path, target = _resolve_local_path(db, filebase_id, path)
    if local_path is None:
        return jsonify({'success': False, 'message': '文件库不存在或路径非法'})

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)
    stat = os.stat(target)
    return jsonify({'success': True, 'mtime': stat.st_mtime})


@fb_bp.route('/<fb_id>/local-files', methods=['GET'])
@login_required
@_require_fb_permission('view')
def list_local_files(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    if not os.path.isdir(local_path):
        return jsonify({'success': False, 'message': '本地目录不存在', 'files': [], 'categories': []})

    subdir = request.args.get('subdir', '').strip()
    tool = request.args.get('tool', '').strip()
    target_path = os.path.join(local_path, subdir) if subdir else local_path
    target_path = os.path.normpath(target_path)

    if not target_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '不允许访问上级目录'})

    if not os.path.isdir(target_path):
        return jsonify({'success': False, 'message': '目录不存在'})

    tool_extensions = {
        'to_docx': ('.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'),
        'to_index': ('.docx', '.doc', '.pdf', '.xlsx'),
        'to_compare': ('.docx', '.doc'),
        'to_pdf': ('.docx', '.doc'),
        'to_pageNum': ('.docx', '.doc'),
        'to_redhead': ('.docx',)
    }
    extensions = tool_extensions.get(tool) if tool else None

    files = []
    categories = []
    try:
        for entry in os.scandir(target_path):
            if entry.name.startswith('~$'):
                continue
            stat = entry.stat()
            if entry.is_dir():
                categories.append({
                    'name': entry.name,
                    'path': os.path.relpath(entry.path, local_path).replace('\\', '/')
                })
            elif entry.is_file():
                _, ext = os.path.splitext(entry.name)
                if extensions and ext.lower() not in extensions:
                    continue
                files.append({
                    'name': entry.name,
                    'path': os.path.relpath(entry.path, local_path).replace('\\', '/'),
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'ext': ext.lower()
                })
    except PermissionError:
        return jsonify({'success': False, 'message': '没有权限访问此目录'})

    categories.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())

    return jsonify({
        'success': True,
        'files': files,
        'categories': categories,
        'current_path': subdir.replace('\\', '/') if subdir else ''
    })


@fb_bp.route('/<fb_id>/local-categories', methods=['GET'])
@login_required
@_require_fb_permission('view')
def list_local_categories(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    if not os.path.isdir(local_path):
        return jsonify({'success': False, 'categories': []})

    recursive = request.args.get('recursive', '0') == '1'

    if recursive:
        categories = _scan_categories_recursive(local_path, local_path)
        return jsonify({'success': True, 'categories': categories})

    subdir = request.args.get('subdir', '').strip()
    target_path = os.path.join(local_path, subdir) if subdir else local_path
    target_path = os.path.normpath(target_path)

    if not target_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'categories': []})

    categories = _scan_categories(target_path, local_path)
    return jsonify({'success': True, 'categories': categories})


def _scan_categories(target_path, base_path):
    categories = []
    try:
        for entry in os.scandir(target_path):
            if entry.name.startswith('~$') or not entry.is_dir():
                continue
            rel_path = os.path.relpath(entry.path, base_path).replace('\\', '/')
            child_categories = []
            try:
                for child in os.scandir(entry.path):
                    if not child.name.startswith('~$') and child.is_dir():
                        child_categories.append({
                            'name': child.name,
                            'path': os.path.relpath(child.path, base_path).replace('\\', '/')
                        })
            except PermissionError:
                pass
            child_categories.sort(key=lambda x: x['name'].lower())
            categories.append({
                'name': entry.name,
                'path': rel_path,
                'children': child_categories
            })
    except PermissionError:
        pass
    categories.sort(key=lambda x: x['name'].lower())
    return categories


def _scan_categories_recursive(target_path, base_path):
    categories = []
    try:
        for entry in os.scandir(target_path):
            if entry.name.startswith('~$') or not entry.is_dir():
                continue
            rel_path = os.path.relpath(entry.path, base_path).replace('\\', '/')
            children = _scan_categories_recursive(entry.path, base_path)
            categories.append({
                'name': entry.name,
                'path': rel_path,
                'children': children
            })
    except PermissionError:
        pass
    categories.sort(key=lambda x: x['name'].lower())
    return categories


@fb_bp.route('/<fb_id>/local-files/download', methods=['GET'])
@login_required
@_require_fb_permission('view')
def download_local_file(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定文件路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '不允许访问上级目录'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))


# ==================== KB 同步管理 ====================

@fb_bp.route('/<fb_id>/sync', methods=['POST'])
@login_required
@_require_fb_permission('manage')
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

    if enabled:
        try:
            from kb.sync_worker import get_sync_worker
            worker = get_sync_worker()
            worker.trigger_sync_now(g.user_id, filebase_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to trigger sync: {e}")

    return jsonify({'success': True, 'enabled': enabled})


@fb_bp.route('/<fb_id>/sync-now', methods=['POST'])
@login_required
@_require_fb_permission('manage')
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
@_require_fb_permission('view')
def get_sync_status(filebase_id):
    """获取同步状态"""
    db = get_db()
    kb_row = db.execute("SELECT owner_id, is_synced_to_kb, local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()

    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'}), 404

    try:
        from kb.sync_state import get_sync_state_manager
        state_manager = get_sync_state_manager()
        state = state_manager.load_state(kb_row['owner_id'], filebase_id)

        total_files = 0
        if os.path.exists(kb_row['local_path']):
            for root, dirs, files in os.walk(kb_row['local_path']):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                files = [f for f in files if not f.startswith('.') and not f.startswith('~')]
                total_files += len(files)

        from kb.sync_converters import can_convert
        syncable_count = 0
        if os.path.exists(kb_row['local_path']):
            for root, dirs, files in os.walk(kb_row['local_path']):
                for f in files:
                    if can_convert(os.path.join(root, f)):
                        syncable_count += 1

        return jsonify({
            'success': True,
            'enabled': bool(kb_row['is_synced_to_kb']),
            'is_owner': kb_row['owner_id'] == g.user_id,
            'status': {
                'total_files': total_files,
                'syncable_files': syncable_count,
                'synced_files': state.synced_files,
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
            'status': {
                'total_files': 0,
                'syncable_files': 0,
                'synced_files': 0,
                'last_sync': None
            }
        })


TOOL_SCRIPTS = {
    'to_docx': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'to_docx.py'),
    'to_index': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'to_index.py'),
    'to_compare': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'to_compare.py'),
    'to_pdf': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'to_pdf.py'),
    'to_pageNum': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'to_pageNum.py'),
    'to_redhead': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'to_redhead.py')
}

TOOL_EXTENSIONS = {
    'to_docx': ('.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'),
    'to_index': ('.docx', '.doc', '.pdf', '.xlsx'),
    'to_compare': ('.docx', '.doc'),
    'to_pdf': ('.docx', '.doc'),
    'to_pageNum': ('.docx', '.doc'),
    'to_redhead': ('.docx',)
}


@fb_bp.route('/<fb_id>/run-tool', methods=['POST'])
@login_required
@_require_fb_permission('edit')
def run_tool_on_fb(filebase_id):
    data = request.get_json()
    tool = data.get('tool')
    subdir = data.get('subdir', '').strip()
    files = data.get('files')
    user_config = data.get('userConfig')

    if not tool:
        return jsonify({'success': False, 'message': '未指定工具'})

    if tool not in TOOL_SCRIPTS:
        return jsonify({'success': False, 'message': f'未知的工具: {tool}'})

    script_path = TOOL_SCRIPTS[tool]
    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'脚本不存在: {tool}'})

    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    target_path = os.path.normpath(os.path.join(local_path, subdir)) if subdir else local_path

    if not target_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '不允许访问的路径'})

    if not os.path.isdir(target_path):
        return jsonify({'success': False, 'message': f'目录不存在: {subdir or "根目录"}'})

    if not files:
        extensions = TOOL_EXTENSIONS.get(tool, ('.docx',))
        files = []
        for f in os.listdir(target_path):
            full = os.path.join(target_path, f)
            if os.path.isfile(full) and f.lower().endswith(extensions):
                files.append(f)

    def generate():
        temp_config_path = None
        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = os.path.dirname(os.path.abspath(__file__))

            if user_config:
                try:
                    temp_dir = tempfile.mkdtemp()
                    temp_config_path = os.path.join(temp_dir, 'config.yaml')
                    with open(temp_config_path, 'w', encoding='utf-8') as f:
                        import yaml
                        yaml.dump(user_config, f, allow_unicode=True, default_flow_style=False)
                    env['USER_CONFIG_PATH'] = temp_config_path
                except Exception as e:
                    yield f'data: {json.dumps({"type": "end", "success": False, "error": f"创建临时配置文件失败: {str(e)}"})}\n\n'
                    return

            cmd_args = [sys.executable, "-u", script_path]
            for f in files:
                full_path = os.path.join(target_path, f)
                cmd_args.append(full_path)

            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=target_path,
                env=env
            )

            output_lines = []
            for line in iter(process.stdout.readline, ''):
                if line:
                    content = line.rstrip()
                    output_lines.append(content)
                    yield f'data: {json.dumps({"type": "output", "content": content})}\n\n'

            process.stdout.close()
            process.wait()

            if temp_config_path and os.path.exists(os.path.dirname(temp_config_path)):
                try:
                    shutil.rmtree(os.path.dirname(temp_config_path))
                except Exception:
                    pass

            success = process.returncode == 0
            if not success:
                error_msg = '\n'.join(output_lines) if output_lines else "执行失败"
                yield f'data: {json.dumps({"type": "end", "success": False, "error": error_msg})}\n\n'
            else:
                yield f'data: {json.dumps({"type": "end", "success": True})}\n\n'

        except Exception as e:
            yield f'data: {json.dumps({"type": "end", "success": False, "error": str(e)})}\n\n'

    return Response(generate(), mimetype='text/event-stream')


@fb_bp.route('/<fb_id>/local-files/content', methods=['GET'])
@login_required
@_require_fb_permission('view')
def get_local_file_content(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定文件路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '不允许访问上级目录'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    ext = os.path.splitext(file_path)[1].lower()

    if ext in ('.md', '.txt', '.html', '.htm', '.xml', '.json', '.csv', '.yaml', '.yml', '.py', '.js', '.css'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'success': True, 'content': content, 'file_type': ext})
        except UnicodeDecodeError:
            return jsonify({'success': False, 'message': '无法以文本方式读取此文件'})

    if ext == '.docx':
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs]
            return jsonify({'success': True, 'content': '\n'.join(paragraphs), 'file_type': ext})
        except Exception:
            return jsonify({'success': False, 'message': '无法读取 docx 内容'})

    if ext in ('.xlsx', '.xls'):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=True)
            lines = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                lines.append(f'# {sheet_name}')
                for row in ws.iter_rows(values_only=True):
                    lines.append('\t'.join(str(c) if c is not None else '' for c in row))
            return jsonify({'success': True, 'content': '\n'.join(lines), 'file_type': ext})
        except Exception:
            return jsonify({'success': False, 'message': '无法读取 xlsx 内容'})

    return jsonify({'success': False, 'message': '不支持在线查看此文件类型的内容'})


SUPPORTED_PREVIEW_EXTS = {'.docx', '.pptx', '.ppt', '.xlsx', '.xls'}


@fb_bp.route('/<fb_id>/local-files/preview', methods=['GET'])
@login_required
@_require_fb_permission('view')
def file_preview(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定文件路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '不允许访问上级目录'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_PREVIEW_EXTS:
        return jsonify({'success': False, 'message': f'不支持的预览格式: {ext}'})

    try:
        from kb.sync_converters import MarkItDownConverter
        converter = MarkItDownConverter()
        markdown = converter.convert(file_path)
        if markdown is None:
            return jsonify({'success': False, 'message': '文件转换失败'})
        return jsonify({'success': True, 'markdown': markdown, 'file_type': ext})
    except Exception as e:
        return jsonify({'success': False, 'message': f'预览失败: {str(e)}'})


@fb_bp.route('/<fb_id>/local-files/batch-download', methods=['POST'])
@login_required
@_require_fb_permission('view')
def batch_download_local(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    data = request.get_json() or {}
    paths = data.get('paths', [])

    if not paths:
        return jsonify({'success': False, 'message': '请选择文件'})

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel_path in paths:
            abs_path = os.path.normpath(os.path.join(local_path, rel_path))
            if not abs_path.startswith(os.path.normpath(local_path)):
                continue
            if os.path.isfile(abs_path):
                zf.write(abs_path, os.path.basename(abs_path))
            elif os.path.isdir(abs_path):
                for root, dirs, files in os.walk(abs_path):
                    for f in files:
                        fp = os.path.join(root, f)
                        arc = os.path.relpath(fp, os.path.dirname(abs_path)).replace('\\', '/')
                        zf.write(fp, arc)

    memory_file.seek(0)
    return send_file(memory_file, mimetype='application/zip',
                     as_attachment=True, download_name='files.zip')


@fb_bp.route('/<fb_id>/local-files/replace', methods=['PUT'])
@login_required
@_require_fb_permission('edit')
def replace_local_file(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定文件路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '不允许访问上级目录'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '原文件不存在'})

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '请选择文件'})

    upload_file = request.files['file']
    if not upload_file.filename:
        return jsonify({'success': False, 'message': '文件名不能为空'})

    try:
        upload_file.save(file_path)
        new_stat = os.stat(file_path)
        return jsonify({
            'success': True,
            'message': '文件已替换',
            'size': new_stat.st_size,
            'mtime': new_stat.st_mtime
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@fb_bp.route('/<fb_id>/local-files/move', methods=['PUT'])
@login_required
@_require_fb_permission('edit')
def move_local_items(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    data = request.get_json() or {}
    sources = data.get('sources', [])
    dest = (data.get('dest') or '').strip()

    if not sources:
        return jsonify({'success': False, 'message': '请选择要移动的项目'})
    if not dest:
        return jsonify({'success': False, 'message': '请指定目标目录'})

    dest_path = os.path.normpath(os.path.join(local_path, dest))
    if not dest_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '目标目录非法'})

    if not os.path.isdir(dest_path):
        os.makedirs(dest_path, exist_ok=True)

    moved = 0
    errors = []
    for src in sources:
        src_path = os.path.normpath(os.path.join(local_path, src))
        if not src_path.startswith(os.path.normpath(local_path)):
            errors.append(f'{src}: 路径非法')
            continue
        if not os.path.exists(src_path):
            errors.append(f'{src}: 不存在')
            continue
        target = os.path.join(dest_path, os.path.basename(src_path))
        if os.path.exists(target):
            errors.append(f'{src}: 目标位置已存在同名项目')
            continue
        try:
            shutil.move(src_path, target)
            moved += 1
        except Exception as e:
            errors.append(f'{src}: {str(e)}')

    return jsonify({
        'success': True,
        'moved': moved,
        'errors': errors
    })


@fb_bp.route('/<fb_id>/local-files', methods=['DELETE'])
@login_required
@_require_fb_permission('edit')
def delete_local_items(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    data = request.get_json() or {}
    paths = data.get('paths', [])
    if not paths:
        return jsonify({'success': False, 'message': '请选择要删除的项目'})

    deleted = 0
    errors = []
    for rel in paths:
        if not rel:
            continue
        target = os.path.normpath(os.path.join(local_path, rel))
        if not target.startswith(os.path.normpath(local_path)):
            errors.append(f'{rel}: 路径非法')
            continue
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            elif os.path.isfile(target):
                os.remove(target)
            else:
                errors.append(f'{rel}: 文件不存在')
                continue
            deleted += 1
        except Exception as e:
            errors.append(f'{rel}: {str(e)}')

    return jsonify({'success': True, 'deleted': deleted, 'errors': errors})


@fb_bp.route('/<fb_id>/local-files/rename', methods=['PUT'])
@login_required
@_require_fb_permission('edit')
def rename_local_item(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    data = request.get_json() or {}
    rel_path = (data.get('path') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not rel_path:
        return jsonify({'success': False, 'message': '未指定文件路径'})
    if not new_name:
        return jsonify({'success': False, 'message': '新名称不能为空'})
    if '/' in new_name or '\\' in new_name:
        return jsonify({'success': False, 'message': '新名称不能包含路径分隔符'})

    old = os.path.normpath(os.path.join(local_path, rel_path))
    if not old.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    if not os.path.exists(old):
        return jsonify({'success': False, 'message': '文件或目录不存在'})

    parent_dir = os.path.dirname(old)
    new_path = os.path.join(parent_dir, new_name)
    if os.path.exists(new_path):
        return jsonify({'success': False, 'message': '同名文件或目录已存在'})

    try:
        os.rename(old, new_path)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

    new_rel = os.path.relpath(new_path, local_path).replace('\\', '/')
    return jsonify({'success': True, 'new_path': new_rel})


@fb_bp.route('/<fb_id>/local-files/copy', methods=['POST'])
@login_required
@_require_fb_permission('edit')
def copy_local_items(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    data = request.get_json() or {}
    sources = data.get('sources', [])
    dest = (data.get('dest') or '').strip()

    if not sources:
        return jsonify({'success': False, 'message': '请选择要复制的项目'})

    dest_dir = os.path.normpath(os.path.join(local_path, dest)) if dest else local_path
    if not dest_dir.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '目标路径非法'})

    os.makedirs(dest_dir, exist_ok=True)

    copied = 0
    errors = []
    for rel in sources:
        if not rel:
            continue
        src = os.path.normpath(os.path.join(local_path, rel))
        if not src.startswith(os.path.normpath(local_path)):
            errors.append(f'{rel}: 路径非法')
            continue
        try:
            basename = os.path.basename(src)
            dst = os.path.join(dest_dir, basename)

            counter = 1
            orig_dst = dst
            while os.path.exists(dst):
                name, ext = os.path.splitext(basename)
                dst = os.path.join(dest_dir, f'{name}_{counter}{ext}')
                counter += 1

            if os.path.isdir(src):
                shutil.copytree(src, dst)
            elif os.path.isfile(src):
                shutil.copy2(src, dst)
            else:
                errors.append(f'{rel}: 文件不存在')
                continue
            copied += 1
        except Exception as e:
            errors.append(f'{rel}: {str(e)}')

    return jsonify({'success': True, 'copied': copied, 'errors': errors})


@fb_bp.route('/<fb_id>/local-files/open', methods=['GET'])
@login_required
@_require_fb_permission('view')
def open_local_file(filebase_id):
    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定文件路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '不允许访问上级目录'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    # PDF、图片等浏览器可直接渲染的类型用 inline 预览，其他类型才强制下载
    ext = os.path.splitext(file_path)[1].lower()
    previewable_exts = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.txt', '.csv'}
    as_attachment = ext not in previewable_exts

    return send_file(file_path, as_attachment=as_attachment, download_name=os.path.basename(file_path))
