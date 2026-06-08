"""文件库文件操作 - 文件编辑与移动"""

import os
import shutil
import time
import json
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db
from fb.decorators import _require_fb_permission, require_fb_perm, _ensure_local_fb_route, _get_node_identity, require_not_locked
from fb.routes_files import _trigger_fb_sync
from fb.routes_base import _get_trash_dir

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


@fb_bp.route('/<fb_id>/local-files/replace', methods=['PUT'])
@login_required
@require_fb_perm('edit')
@require_not_locked
@_ensure_local_fb_route
def replace_local_file(filebase_id):
    """替换文件"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        path = request.args.get('path', '').strip()
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '请选择文件'})
        upload_file = request.files['file']
        result = p2p_proxy.remote_replace_file(info['owner_addr'], node, filebase_id, path, upload_file.filename, upload_file.stream)
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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
        _trigger_fb_sync(filebase_id)
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
@require_fb_perm('edit')
@require_not_locked
@_ensure_local_fb_route
def move_local_items(filebase_id):
    """移动文件或目录"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        data = request.get_json() or {}
        result = p2p_proxy.remote_move_items(info['owner_addr'], node, filebase_id, data.get('sources', []), data.get('dest', ''))
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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

    _trigger_fb_sync(filebase_id)
    return jsonify({
        'success': True,
        'moved': moved,
        'errors': errors
    })


@fb_bp.route('/<fb_id>/local-files', methods=['DELETE'])
@login_required
@require_fb_perm('edit')
@require_not_locked
@_ensure_local_fb_route
def delete_local_items(filebase_id):
    """删除文件或目录"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        result = p2p_proxy.remote_delete_items(info['owner_addr'], node, filebase_id, (request.get_json() or {}).get('paths', []))
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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
    trash_dir = os.path.join(_get_trash_dir(), '_files_', filebase_id)
    for rel in paths:
        if not rel:
            continue
        target = os.path.normpath(os.path.join(local_path, rel))
        if not target.startswith(os.path.normpath(local_path)):
            errors.append(f'{rel}: 路径非法')
            continue
        try:
            if not os.path.exists(target):
                errors.append(f'{rel}: 文件不存在')
                continue
            os.makedirs(trash_dir, exist_ok=True)
            ts = str(int(time.time() * 1000000))
            basename = os.path.basename(rel)
            trash_name = basename + '_' + ts
            trash_target = os.path.join(trash_dir, trash_name)
            shutil.move(target, trash_target)
            meta = {'original_path': rel, 'is_dir': os.path.isdir(trash_target), 'timestamp': ts}
            with open(trash_target + '.meta.json', 'w', encoding='utf-8') as f:
                json.dump(meta, f)
            deleted += 1
        except Exception as e:
            errors.append(f'{rel}: {str(e)}')

    _trigger_fb_sync(filebase_id)
    return jsonify({'success': True, 'deleted': deleted, 'errors': errors})


@fb_bp.route('/<fb_id>/local-files/rename', methods=['PUT'])
@login_required
@require_fb_perm('edit')
@require_not_locked
@_ensure_local_fb_route
def rename_local_item(filebase_id):
    """重命名文件或目录"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        data = request.get_json() or {}
        result = p2p_proxy.remote_rename_item(info['owner_addr'], node, filebase_id, data.get('path', ''), data.get('new_name', ''))
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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
    _trigger_fb_sync(filebase_id)
    return jsonify({'success': True, 'new_path': new_rel})


@fb_bp.route('/<fb_id>/local-files/copy', methods=['POST'])
@login_required
@require_fb_perm('edit')
@require_not_locked
@_ensure_local_fb_route
def copy_local_items(filebase_id):
    """复制文件或目录"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        data = request.get_json() or {}
        result = p2p_proxy.remote_copy_items(info['owner_addr'], node, filebase_id, data.get('sources', []), data.get('dest', ''))
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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

    _trigger_fb_sync(filebase_id)
    return jsonify({'success': True, 'copied': copied, 'errors': errors})


@fb_bp.route('/<fb_id>/local-files/trash-items', methods=['GET'])
@login_required
@require_fb_perm('edit')
@_ensure_local_fb_route
def list_file_trash(filebase_id):
    """列出文件库内的回收站项目"""
    if getattr(g, 'is_remote_fb', False):
        return jsonify({'success': False, 'message': '远程文件库不支持回收站'})

    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    trash_dir = os.path.join(_get_trash_dir(), '_files_', filebase_id)
    if not os.path.isdir(trash_dir):
        return jsonify({'success': True, 'items': []})

    items = []
    for entry in os.listdir(trash_dir):
        if entry.endswith('.meta.json'):
            continue
        meta_path = os.path.join(trash_dir, entry + '.meta.json')
        meta = {}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception:
                pass
        entry_path = os.path.join(trash_dir, entry)
        stat = os.stat(entry_path)
        size = 0
        if os.path.isfile(entry_path):
            size = stat.st_size
        elif os.path.isdir(entry_path):
            try:
                size = sum(os.path.getsize(os.path.join(r, f)) for r, ds, fs in os.walk(entry_path) for f in fs)
            except Exception:
                pass
        items.append({
            'name': entry,
            'original_path': meta.get('original_path', ''),
            'is_dir': meta.get('is_dir', os.path.isdir(entry_path)),
            'mtime': stat.st_mtime,
            'size': size
        })
    items.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify({'success': True, 'items': items})


@fb_bp.route('/<fb_id>/local-files/trash-restore', methods=['POST'])
@login_required
@require_fb_perm('edit')
@_ensure_local_fb_route
def restore_file_trash(filebase_id):
    """从回收站恢复文件"""
    if getattr(g, 'is_remote_fb', False):
        return jsonify({'success': False, 'message': '远程文件库不支持回收站'})

    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    data = request.get_json() or {}
    trash_name = (data.get('name') or '').strip()
    if not trash_name:
        return jsonify({'success': False, 'message': '未指定项目'})

    trash_dir = os.path.join(_get_trash_dir(), '_files_', filebase_id)
    src = os.path.join(trash_dir, trash_name)
    if not os.path.exists(src):
        return jsonify({'success': False, 'message': '项目不存在'})

    meta_path = src + '.meta.json'
    original_path = trash_name.split('_', 1)[0] if '_' in trash_name else trash_name
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            if meta.get('original_path'):
                original_path = meta['original_path']
        except Exception:
            pass

    dst = os.path.normpath(os.path.join(local_path, original_path))
    if not dst.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    dst_parent = os.path.dirname(dst)
    os.makedirs(dst_parent, exist_ok=True)

    if os.path.exists(dst):
        base, ext = os.path.splitext(os.path.basename(original_path))
        counter = 1
        while True:
            new_name = f'{base}_{counter}{ext}'
            new_dst = os.path.join(dst_parent, new_name)
            if not os.path.exists(new_dst):
                dst = new_dst
                break
            counter += 1

    try:
        shutil.move(src, dst)
        if os.path.isfile(meta_path):
            os.remove(meta_path)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

    _trigger_fb_sync(filebase_id)
    return jsonify({'success': True})


@fb_bp.route('/<fb_id>/local-files/trash-item', methods=['DELETE'])
@login_required
@require_fb_perm('edit')
@_ensure_local_fb_route
def delete_file_trash_item(filebase_id):
    """永久删除回收站中的项目"""
    if getattr(g, 'is_remote_fb', False):
        return jsonify({'success': False, 'message': '远程文件库不支持回收站'})

    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '未指定项目'})

    trash_dir = os.path.join(_get_trash_dir(), '_files_', filebase_id)
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
        meta_path = target + '.meta.json'
        if os.path.isfile(meta_path):
            os.remove(meta_path)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': True})
