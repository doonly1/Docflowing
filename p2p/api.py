import os
import json
import sys
import subprocess
import uuid
import time

from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file, g

from .auth import p2p_auth_required
from .models import TrustStore, RemoteFilebaseStore
from logging_config import get_logger
from tools.tool_defs import get_tool_script_path, TOOL_EXTENSIONS

logger = get_logger(__name__)

p2p_bp = Blueprint('p2p', __name__, url_prefix='/p2p')

from fb.decorators import PERM_BITS, _check_fb_perm_bits

# Backward compatible levels for old system
FB_PERMISSION_LEVELS = {'view': 0, 'edit': 1, 'manage': 2}



def _check_permission(fb_id: str, node_id: str, required: str) -> bool:
    """Check permission using either old table or new bitmask table"""
    from fb.database import get_db
    from fb.decorators import ROLE_TEMPLATES
    db = get_db()

    # Try new perm_v2 first
    bit = PERM_BITS.get(required)
    if bit is not None:
        row = db.execute(
            "SELECT perm_mask FROM filebase_perm_v2 WHERE filebase_id = ? AND user_id = ?",
            (fb_id, node_id)
        ).fetchone()
        if row:
            return (row['perm_mask'] & bit) == bit

    # Fallback to old permission_level
    row = db.execute(
        "SELECT permission_level FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
        (fb_id, node_id)
    ).fetchone()
    if not row:
        # Check if node is owner
        owner_row = db.execute("SELECT owner_id FROM filebases WHERE id = ?", (fb_id,)).fetchone()
        if owner_row and owner_row['owner_id'] == node_id:
            if bit is not None:
                return (ROLE_TEMPLATES['manage'] & bit) == bit
            return True
        return False

    if bit is None:
        # Old style level check
        actual = FB_PERMISSION_LEVELS.get(row['permission_level'], -1)
        return actual >= FB_PERMISSION_LEVELS.get(required, 0)
    else:
        # Map old level to role template and check bit
        level = row['permission_level']
        if level == 'manage':
            return (ROLE_TEMPLATES['manage'] & bit) == bit
        elif level == 'edit':
            return (ROLE_TEMPLATES['edit'] & bit) == bit
        elif level == 'view':
            return (ROLE_TEMPLATES['view'] & bit) == bit
        return False



def _get_fb_local_path(fb_id: str) -> str | None:
    from fb.database import get_db
    db = get_db()
    row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (fb_id,)).fetchone()
    return row['local_path'] if row else None


@p2p_bp.route('/fb/<fb_id>/metadata', methods=['GET'])
@p2p_auth_required
def p2p_fb_metadata(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'view'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    from fb.database import get_db
    db = get_db()
    row = db.execute("SELECT name, owner_id FROM filebases WHERE id = ?", (fb_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件库不存在'}), 404

    total_files = 0
    if local_path and os.path.isdir(local_path):
        for root, dirs, files in os.walk(local_path):
            total_files += len([f for f in files if not f.startswith('~$')])

    return jsonify({
        'success': True,
        'name': row['name'],
        'owner_id': row['owner_id'],
        'total_files': total_files,
        'exists': bool(local_path and os.path.isdir(local_path))
    })


@p2p_bp.route('/fb/<fb_id>/list-files', methods=['GET'])
@p2p_auth_required
def p2p_list_files(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'view'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path or not os.path.isdir(local_path):
        return jsonify({'success': False, 'message': '文件库不存在', 'files': [], 'categories': []})

    subdir = request.args.get('subdir', '').strip()
    tool = request.args.get('tool', '').strip()
    target = os.path.join(local_path, subdir) if subdir else local_path
    target = os.path.normpath(target)

    if not target.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    if not os.path.isdir(target):
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
        for entry in os.scandir(target):
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


@p2p_bp.route('/fb/<fb_id>/file-content', methods=['GET'])
@p2p_auth_required
def p2p_file_content(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'view'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    ext = os.path.splitext(file_path)[1].lower()
    text_exts = {'.md', '.txt', '.html', '.htm', '.xml', '.json', '.csv', '.yaml', '.yml', '.py', '.js', '.css'}

    if ext in text_exts:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'success': True, 'content': content, 'file_type': ext})
        except UnicodeDecodeError:
            return jsonify({'success': False, 'message': '无法读取此文件'})

    if ext == '.docx':
        try:
            from docx import Document
            doc = Document(file_path)
            return jsonify({'success': True, 'content': '\n'.join(p.text for p in doc.paragraphs), 'file_type': ext})
        except Exception:
            return jsonify({'success': False, 'message': '无法读取docx内容'})

    return jsonify({'success': False, 'message': '不支持查看此文件类型'})


@p2p_bp.route('/fb/<fb_id>/download', methods=['GET'])
@p2p_auth_required
def p2p_download(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'view'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))


@p2p_bp.route('/fb/<fb_id>/upload', methods=['POST'])
@p2p_auth_required
def p2p_upload(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    subdir = request.args.get('subdir', '').strip()
    target_dir = os.path.join(local_path, subdir) if subdir else local_path
    target_dir = os.path.normpath(target_dir)

    if not target_dir.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    os.makedirs(target_dir, exist_ok=True)

    uploaded = []
    for key in request.files:
        for f in request.files.getlist(key):
            if not f.filename:
                continue
            safe_name = os.path.basename(f.filename)
            file_path = os.path.join(target_dir, safe_name)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            f.save(file_path)
            stat = os.stat(file_path)
            uploaded.append({'name': f.filename, 'size': stat.st_size, 'mtime': stat.st_mtime})

    return jsonify({'success': True, 'uploaded': uploaded})


@p2p_bp.route('/fb/<fb_id>/save-file', methods=['POST'])
@p2p_auth_required
def p2p_save_file(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    rel_path = (data.get('path') or '').strip()
    content = data.get('content', '')
    client_mtime = data.get('client_mtime', 0)

    if not rel_path:
        return jsonify({'success': False, 'message': '未指定路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    current_mtime = os.stat(file_path).st_mtime
    if client_mtime and current_mtime != client_mtime:
        return jsonify({
            'success': False,
            'conflict': True,
            'message': '文件已被其他人修改',
            'server_mtime': current_mtime
        }), 409

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    new_mtime = os.stat(file_path).st_mtime
    return jsonify({'success': True, 'mtime': new_mtime})


@p2p_bp.route('/fb/<fb_id>/delete-items', methods=['POST'])
@p2p_auth_required
def p2p_delete_items(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    paths = data.get('paths', [])
    if not paths:
        return jsonify({'success': False, 'message': '请选择要删除的项目'})

    deleted = 0
    errors = []
    for rel in paths:
        target = os.path.normpath(os.path.join(local_path, rel))
        if not target.startswith(os.path.normpath(local_path)):
            errors.append(f'{rel}: 路径非法')
            continue
        try:
            if os.path.isdir(target):
                import shutil
                shutil.rmtree(target)
            elif os.path.isfile(target):
                os.remove(target)
            else:
                errors.append(f'{rel}: 不存在')
                continue
            deleted += 1
        except Exception as e:
            errors.append(f'{rel}: {str(e)}')

    return jsonify({'success': True, 'deleted': deleted, 'errors': errors})


@p2p_bp.route('/fb/<fb_id>/rename-item', methods=['POST'])
@p2p_auth_required
def p2p_rename_item(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    rel_path = (data.get('path') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not rel_path or not new_name:
        return jsonify({'success': False, 'message': '参数不完整'})
    if '/' in new_name or '\\' in new_name:
        return jsonify({'success': False, 'message': '名称不能包含路径分隔符'})

    old = os.path.normpath(os.path.join(local_path, rel_path))
    if not old.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    parent_dir = os.path.dirname(old)
    new_path = os.path.join(parent_dir, new_name)
    if os.path.exists(new_path):
        return jsonify({'success': False, 'message': '同名项目已存在'})

    try:
        os.rename(old, new_path)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

    new_rel = os.path.relpath(new_path, local_path).replace('\\', '/')
    return jsonify({'success': True, 'new_path': new_rel})


@p2p_bp.route('/fb/<fb_id>/move-items', methods=['POST'])
@p2p_auth_required
def p2p_move_items(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    sources = data.get('sources', [])
    dest = (data.get('dest') or '').strip()
    if not sources or not dest:
        return jsonify({'success': False, 'message': '参数不完整'})

    dest_path = os.path.normpath(os.path.join(local_path, dest))
    if not dest_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '目标路径非法'})

    import shutil
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

    return jsonify({'success': True, 'moved': moved, 'errors': errors})


@p2p_bp.route('/fb/<fb_id>/copy-items', methods=['POST'])
@p2p_auth_required
def p2p_copy_items(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    sources = data.get('sources', [])
    dest = (data.get('dest') or '').strip()
    if not sources:
        return jsonify({'success': False, 'message': '请选择要复制的项目'})

    import shutil
    dest_dir = os.path.normpath(os.path.join(local_path, dest)) if dest else local_path
    if not dest_dir.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '目标路径非法'})
    os.makedirs(dest_dir, exist_ok=True)

    copied = 0
    errors = []
    for rel in sources:
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
            else:
                shutil.copy2(src, dst)
            copied += 1
        except Exception as e:
            errors.append(f'{rel}: {str(e)}')

    return jsonify({'success': True, 'copied': copied, 'errors': errors})


@p2p_bp.route('/fb/<fb_id>/create-file', methods=['POST'])
@p2p_auth_required
def p2p_create_file(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    parent = (data.get('parent') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '文件名不能为空'})

    target_dir = os.path.join(local_path, parent) if parent else local_path
    target_dir = os.path.normpath(target_dir)
    if not target_dir.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    base, ext = os.path.splitext(name)
    filename = name if ext else name + '.md'
    file_path = os.path.join(target_dir, filename)
    counter = 1
    while os.path.exists(file_path) and counter < 100:
        filename = base + '_' + str(counter) + (ext or '.md')
        file_path = os.path.join(target_dir, filename)
        counter += 1

    os.makedirs(target_dir, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('')

    rel = os.path.relpath(file_path, local_path).replace('\\', '/')
    return jsonify({'success': True, 'path': rel})


@p2p_bp.route('/fb/<fb_id>/create-dir', methods=['POST'])
@p2p_auth_required
def p2p_create_dir(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    parent = (data.get('parent') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '目录名不能为空'})

    target_dir = os.path.join(local_path, parent) if parent else local_path
    target_dir = os.path.normpath(target_dir)
    if not target_dir.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    new_dir = os.path.join(target_dir, name)
    counter = 1
    orig_name = name
    while os.path.exists(new_dir) and counter < 100:
        name = orig_name + '_' + str(counter)
        new_dir = os.path.join(target_dir, name)
        counter += 1

    os.makedirs(new_dir, exist_ok=True)
    rel = os.path.relpath(new_dir, local_path).replace('\\', '/')
    return jsonify({'success': True, 'path': rel})


@p2p_bp.route('/fb/<fb_id>/replace-file', methods=['POST'])
@p2p_auth_required
def p2p_replace_file(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'success': False, 'message': '未指定路径'})

    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})

    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '原文件不存在'})

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '请选择文件'})

    upload_file = request.files['file']
    try:
        upload_file.save(file_path)
        new_stat = os.stat(file_path)
        return jsonify({'success': True, 'size': new_stat.st_size, 'mtime': new_stat.st_mtime})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@p2p_bp.route('/fb/<fb_id>/run-tool', methods=['POST'])
@p2p_auth_required
def p2p_run_tool(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    data = request.get_json() or {}
    tool = data.get('tool')
    files = data.get('files')
    subdir = data.get('subdir', '').strip()

    if not tool:
        return jsonify({'success': False, 'message': '未指定工具'})

    script_path = get_tool_script_path(tool) if tool else None
    if not script_path or not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'工具脚本不存在: {tool}'})

    target_path = os.path.normpath(os.path.join(local_path, subdir)) if subdir else local_path
    if not target_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})
    if not os.path.isdir(target_path):
        return jsonify({'success': False, 'message': f'目录不存在: {subdir or "根目录"}'})

    if not files:
        extensions = TOOL_EXTENSIONS.get(tool, ('.docx',))
        files = [f for f in os.listdir(target_path)
                 if os.path.isfile(os.path.join(target_path, f)) and f.lower().endswith(extensions)]

    def generate():
        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env['USER_ID'] = g.remote_node_id

            cmd_args = [sys.executable, "-u", script_path]
            for f in files:
                full_path = os.path.join(target_path, f)
                cmd_args.append(full_path)

            process = subprocess.Popen(
                cmd_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=target_path, env=env
            )

            output_lines = []
            for line in iter(process.stdout.readline, ''):
                if line:
                    content = line.rstrip()
                    content = content.replace('\\', '/')
                    output_lines.append(content)
                    yield f'data: {json.dumps({"type": "output", "content": content})}\n\n'

            process.stdout.close()
            process.wait()
            success = process.returncode == 0
            if not success:
                yield f'data: {json.dumps({"type": "end", "success": False, "error": "\n".join(output_lines) if output_lines else "执行失败"})}\n\n'
            else:
                yield f'data: {json.dumps({"type": "end", "success": True})}\n\n'

        except Exception as e:
            yield f'data: {json.dumps({"type": "end", "success": False, "error": str(e)})}\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@p2p_bp.route('/kb/search', methods=['POST'])
@p2p_auth_required
def p2p_kb_search(fb_id=None):
    data = request.get_json() or {}
    fb_ids = data.get('fb_ids', [])
    query = (data.get('q') or '').strip()

    if not fb_ids or not query:
        return jsonify({'success': False, 'message': '参数不完整'})

    allowed_fb_ids = [fid for fid in fb_ids if _check_permission(fid, g.remote_node_id, 'view')]
    if not allowed_fb_ids:
        return jsonify({'success': True, 'results': []})

    from kb.database import get_db as get_kb_db
    results = []
    for fb_id in allowed_fb_ids:
        owner_id = None
        from fb.database import get_db
        fb_db = get_db()
        row = fb_db.execute("SELECT owner_id FROM filebases WHERE id = ?", (fb_id,)).fetchone()
        if row:
            owner_id = row['owner_id']

        if not owner_id:
            continue

        conn = get_kb_db(owner_id)
        prefix = f'imported/{fb_id}/%'
        try:
            rows = conn.execute(
                "SELECT path, title, content FROM wiki_fts WHERE usr_id = ? AND path LIKE ? AND content MATCH ?",
                (owner_id, prefix, query)
            ).fetchall()
            for r in rows:
                results.append({
                    'fb_id': fb_id,
                    'path': r['path'],
                    'title': r['title'],
                    'content': r['content'][:500] if r['content'] else ''
                })
        except Exception:
            pass

    return jsonify({'success': True, 'results': results})


@p2p_bp.route('/fb/<fb_id>/preview', methods=['GET'])
@p2p_auth_required
def p2p_preview(fb_id):
    if not _check_permission(fb_id, g.remote_node_id, 'view'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    local_path = _get_fb_local_path(fb_id)
    if not local_path:
        return jsonify({'success': False, 'message': '文件库不存在'})

    rel_path = request.args.get('path', '').strip()
    file_path = os.path.normpath(os.path.join(local_path, rel_path))
    if not file_path.startswith(os.path.normpath(local_path)):
        return jsonify({'success': False, 'message': '路径非法'})
    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': '文件不存在'})

    supported = {'.docx', '.pptx', '.ppt', '.xlsx', '.xls'}
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in supported:
        return jsonify({'success': False, 'message': f'不支持的预览格式: {ext}'})

    try:
        from kb.sync_converters import MarkItDownConverter
        converter = MarkItDownConverter()
        markdown = converter.convert(file_path)
        if markdown is None:
            return jsonify({'success': False, 'message': '转换失败'})
        return jsonify({'success': True, 'markdown': markdown, 'file_type': ext})
    except Exception as e:
        return jsonify({'success': False, 'message': f'预览失败: {str(e)}'})


@p2p_bp.route('/handshake', methods=['POST'])
@p2p_auth_required
def p2p_handshake():
    data = request.get_json() or {}
    node_id = g.remote_node_id
    display_name = data.get('display_name', '')
    addr = request.remote_addr or ''
    port = data.get('port', 5000)
    public_key = data.get('public_key', '')

    full_addr = f'{addr}:{port}'
    trust_store = TrustStore()
    trust_store.add_node(node_id, display_name, full_addr, public_key)

    logger.info("Handshake from %s (%s) at %s", display_name, node_id[:8], full_addr)
    return jsonify({'success': True})


@p2p_bp.route('/share/notify', methods=['POST'])
def p2p_share_notify():
    data = request.get_json() or {}
    fb_id = data.get('fb_id', '')
    fb_name = data.get('fb_name', '')
    owner_addr = data.get('owner_addr', '')
    permission = data.get('permission', 'view')
    node_id = data.get('node_id', '')
    node_name = data.get('node_name', '')
    node_public_key = data.get('node_public_key', '')

    if not fb_id or not fb_name or not node_id:
        return jsonify({'success': False, 'message': '参数不完整'})

    trust_store = TrustStore()
    trust_store.add_node(node_id, node_name, owner_addr, node_public_key)

    perm_mask = data.get('perm_mask')
    remote_store = RemoteFilebaseStore()
    remote_store.add(fb_id, node_id, owner_addr, fb_name, permission, perm_mask)

    logger.info("Received shared filebase: %s (%s) from %s", fb_name, fb_id[:8], node_id[:8])
    return jsonify({'success': True, 'message': '文件库已添加到本地列表'})


@p2p_bp.route('/share/list', methods=['POST'])
@p2p_auth_required
def p2p_share_list():
    from fb.database import get_db
    db = get_db()
    # Get from old permissions table
    rows = db.execute(
        "SELECT f.id, f.name, f.filebase_type FROM filebases f "
        "JOIN filebase_permissions p ON f.id = p.filebase_id "
        "WHERE p.user_id = ? AND p.permission_level IN ('view', 'edit', 'manage') "
        "AND COALESCE(f.status, 'active') != 'trashed'",
        (g.remote_node_id,)
    ).fetchall()

    filebases = [{'id': r['id'], 'name': r['name'], 'type': r['filebase_type']} for r in rows]

    # Also include from perm_v2 table
    v2_rows = db.execute(
        "SELECT f.id, f.name, f.filebase_type FROM filebases f "
        "JOIN filebase_perm_v2 p ON f.id = p.filebase_id "
        "WHERE p.user_id = ? AND p.perm_mask > 0 "
        "AND COALESCE(f.status, 'active') != 'trashed'",
        (g.remote_node_id,)
    ).fetchall()
    existing_ids = {r['id'] for r in rows}
    for r in v2_rows:
        if r['id'] not in existing_ids:
            filebases.append({'id': r['id'], 'name': r['name'], 'type': r['filebase_type']})

    return jsonify({'success': True, 'filebases': filebases})


@p2p_bp.route('/fb/<fb_id>/revoke', methods=['DELETE'])
def p2p_revoke_share(fb_id):
    """接收远端所有者的撤销共享通知，从本地移除远程文件库"""
    remote_store = RemoteFilebaseStore()
    info = remote_store.get(fb_id)
    if not info:
        return jsonify({'success': False, 'message': '文件库不在共享列表中'}), 404

    remote_store.remove(fb_id)
    logger.info("Revoked shared filebase: %s from %s", fb_id[:8], info.get('owner_node_id', '')[:8])
    return jsonify({'success': True, 'message': '共享已撤销'})