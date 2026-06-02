"""文件库文件操作 - 本地文件管理"""

import os
import io
import shutil
import zipfile
from flask import Blueprint, request, jsonify, send_file, g

from server.auth import login_required
from fb.database import get_db
from fb.decorators import _require_fb_permission, _ensure_local_fb_route, _get_node_identity
from tools.tool_defs import TOOL_EXTENSIONS

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


def _resolve_local_path(db, filebase_id, subdir=''):
    """解析本地路径"""
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return None, None
    local_path = kb_row['local_path']
    target = os.path.join(local_path, subdir) if subdir else local_path
    target = os.path.normpath(target)
    if not target.startswith(os.path.normpath(local_path)):
        return None, None
    return local_path, target


def _trigger_fb_sync(filebase_id):
    """文件变更后触发同步"""
    try:
        from kb.sync_worker import get_sync_worker
        from flask import g
        worker = get_sync_worker()
        worker._trigger_sync(g.user_id, filebase_id)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(f"Failed to trigger sync for {filebase_id}")


SUPPORTED_PREVIEW_EXTS = {'.docx', '.pptx', '.ppt', '.xlsx', '.xls'}


@fb_bp.route('/<fb_id>/local-files', methods=['POST'])
@login_required
@_require_fb_permission('edit')
@_ensure_local_fb_route
def upload_local_files(filebase_id):
    """上传文件"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        subdir = request.args.get('subdir', '').strip()
        uploaded = []
        for key in request.files:
            for f in request.files.getlist(key):
                if not f.filename:
                    continue
                result = p2p_proxy.remote_upload_file(
                    info['owner_addr'], node, filebase_id,
                    subdir, f.filename, f.stream, 0
                )
                if result:
                    uploaded.extend(result.get('uploaded', []))
        return jsonify({'success': True, 'uploaded': uploaded})

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
            safe_filename = f.filename
            safe_filename = safe_filename.replace('..', '')
            if safe_filename.startswith('/') or safe_filename.startswith('\\'):
                safe_filename = safe_filename[1:]
            file_path = os.path.join(target_dir, safe_filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            f.save(file_path)
            stat = os.stat(file_path)
            uploaded.append({
                'name': f.filename,
                'size': stat.st_size,
                'mtime': stat.st_mtime
            })

    if uploaded:
        _trigger_fb_sync(filebase_id)

    return jsonify({'success': True, 'uploaded': uploaded})


@fb_bp.route('/<fb_id>/local-files/dir', methods=['POST'])
@login_required
@_require_fb_permission('edit')
@_ensure_local_fb_route
def create_local_dir(filebase_id):
    """创建目录"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        data = request.get_json() or {}
        result = p2p_proxy.remote_create_dir(info['owner_addr'], node, filebase_id, data.get('name', ''), data.get('parent', ''))
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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
@_ensure_local_fb_route
def create_local_file(filebase_id):
    """创建本地文件"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        data = request.get_json() or {}
        result = p2p_proxy.remote_create_file(info['owner_addr'], node, filebase_id, data.get('name', ''), data.get('parent', ''))
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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

    base, ext = os.path.splitext(name)
    if ext:
        filename = name
        default_ext = ext
    else:
        filename = name + '.md'
        default_ext = '.md'
    file_path = os.path.join(target_dir, filename)

    counter = 1
    while os.path.exists(file_path) and counter < 100:
        filename = base + '_' + str(counter) + default_ext
        file_path = os.path.join(target_dir, filename)
        counter += 1
    if os.path.exists(file_path):
        return jsonify({'success': False, 'message': '无法生成唯一的文件名'})

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('')
    rel = os.path.relpath(file_path, local_path).replace('\\', '/')
    _trigger_fb_sync(filebase_id)
    return jsonify({'success': True, 'path': rel})


@fb_bp.route('/<fb_id>/local-files/create-office', methods=['POST'])
@login_required
@_require_fb_permission('edit')
@_ensure_local_fb_route
def create_office_file(filebase_id):
    """创建 Office 文件"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        data = request.get_json() or {}
        result = p2p_proxy.remote_create_file(info['owner_addr'], node, filebase_id, data.get('name', ''), data.get('parent', ''))
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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

    ext = os.path.splitext(name)[1].lower()
    if ext not in ('.docx', '.xlsx', '.pptx'):
        return jsonify({'success': False, 'message': f'不支持的文件类型: {ext}'})

    base = os.path.splitext(name)[0]
    file_path = os.path.join(target_dir, name)
    counter = 1
    while os.path.exists(file_path) and counter < 100:
        filename = f'{base}_{counter}{ext}'
        file_path = os.path.join(target_dir, filename)
        counter += 1
    if os.path.exists(file_path):
        return jsonify({'success': False, 'message': '无法生成唯一的文件名'})

    try:
        if ext == '.docx':
            from docx import Document
            from tools.mystyle import clear_styles, add_my_styles, set_page
            doc = Document()
            set_page(doc)
            clear_styles(doc)
            add_my_styles(doc)
            doc.save(file_path)
        elif ext == '.xlsx':
            import openpyxl
            wb = openpyxl.Workbook()
            wb.save(file_path)
        elif ext == '.pptx':
            from pptx import Presentation
            prs = Presentation()
            prs.save(file_path)
    except ImportError as e:
        return jsonify({'success': False, 'message': f'缺少创建 {ext} 文件所需的库: {str(e)}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'创建文件失败: {str(e)}'})

    rel = os.path.relpath(file_path, local_path).replace('\\', '/')
    _trigger_fb_sync(filebase_id)
    return jsonify({'success': True, 'path': rel})


@fb_bp.route('/<fb_id>/local-files', methods=['GET'])
@login_required
@_require_fb_permission('view')
@_ensure_local_fb_route
def list_local_files(filebase_id):
    """列出本地文件"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        subdir = request.args.get('subdir', '')
        result = p2p_proxy.remote_list_files(info['owner_addr'], node, filebase_id, subdir)
        return jsonify(result or {'success': False, 'message': '远程节点不可用'})

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

    extensions = TOOL_EXTENSIONS.get(tool) if tool else None

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
    """列出目录树"""
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
    """扫描单层目录"""
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
    """递归扫描目录树"""
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
