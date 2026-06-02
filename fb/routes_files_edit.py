"""文件库文件操作 - 文件编辑与移动"""

import os
import shutil
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db
from fb.decorators import _require_fb_permission, _ensure_local_fb_route, _get_node_identity
from fb.routes_files import _trigger_fb_sync

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


@fb_bp.route('/<fb_id>/local-files/replace', methods=['PUT'])
@login_required
@_require_fb_permission('edit')
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
@_require_fb_permission('edit')
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
@_require_fb_permission('edit')
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

    _trigger_fb_sync(filebase_id)
    return jsonify({'success': True, 'deleted': deleted, 'errors': errors})


@fb_bp.route('/<fb_id>/local-files/rename', methods=['PUT'])
@login_required
@_require_fb_permission('edit')
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
@_require_fb_permission('edit')
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
