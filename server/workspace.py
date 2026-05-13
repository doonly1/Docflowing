"""Workspace 管理 + 文件操作 API"""

import os
import json
import shutil
import tempfile

from flask import Blueprint, request, jsonify, Response
from server.auth import _login_required, update_user_activity

workspace_bp = Blueprint('workspace', __name__)

# ==================== 常量 ====================

MAX_FILE_SIZE = 90 * 1024 * 1024          # 单文件最大 90MB
MAX_SESSION_SIZE = 900 * 1024 * 1024      # 单会话总大小最大 900MB
MAX_FILES_PER_UPLOAD = 900                # 单次最多上传 900 个文件

# ==================== Workspace 路径 / 活动 ====================

def _get_workspace_dir(user_id):
    ws_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'workspaces', user_id)
    return ws_dir

def _get_workspace_workdir(user_id):
    workdir = os.path.join(_get_workspace_dir(user_id), 'workdir')
    os.makedirs(workdir, exist_ok=True)
    return workdir

def _get_workspace_resources_dir(user_id):
    res_dir = os.path.join(_get_workspace_dir(user_id), 'resources', 'stamps')
    os.makedirs(res_dir, exist_ok=True)
    return res_dir

def _update_workspace_activity(user_id):
    """记录用户最后访问时间"""
    update_user_activity(user_id)

def _get_tool_extensions(tool):
    """获取工具支持的文件扩展名"""
    ext_map = {
        'to_docx': ('.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'),
        'to_index': ('.docx', '.doc', '.pdf', '.xlsx'),
        'to_compare': ('.docx', '.doc'),
        'to_pdf': ('.docx', '.doc'),
        'to_pageNum': ('.docx', '.doc'),
        'to_redhead': ('.docx',)
    }
    return ext_map.get(tool, ('.docx',))

# ==================== 文件列表 ====================

@workspace_bp.route('/list_files', methods=['POST'])
@_login_required
def api_list_files(_user_id=None):
    data = request.get_json()
    workdir = data.get('workdir')
    tool = data.get('tool', 'to_docx')
    token = data.get('token') or data.get('client_id')
    show_all = data.get('show_all', False)

    if workdir and not os.path.isabs(workdir):
        ws_root = _get_workspace_dir(_user_id)
        workdir = os.path.join(ws_root, workdir)
        workdir = os.path.normpath(workdir)

    if not workdir or not os.path.isdir(workdir):
        return jsonify({'success': False, 'message': '目录不存在'})

    extensions = _get_tool_extensions(tool)

    try:
        files = []
        for f in os.listdir(workdir):
            if f.startswith('~$'):
                continue
            file_path = os.path.join(workdir, f)
            if os.path.isfile(file_path):
                if show_all or f.lower().endswith(extensions):
                    files.append({
                        'name': f,
                        'is_dir': False
                    })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ==================== 版本兼容的目录操作 ====================

@workspace_bp.route('/list_dir', methods=['POST'])
def api_list_dir():
    """列出目录内容的API"""
    data = request.get_json()
    workdir = data.get('workdir')

    if not workdir or not os.path.isdir(workdir):
        return jsonify({'success': False, 'message': '目录不存在'})

    try:
        files = []
        for f in os.listdir(workdir):
            if not f.startswith('~$'):
                file_path = os.path.join(workdir, f)
                files.append({
                    'name': f,
                    'is_dir': os.path.isdir(file_path)
                })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ==================== 文件上传 / 结果检查 / 下载 / 清理 ====================

@workspace_bp.route('/upload_files', methods=['POST', 'OPTIONS'])
@_login_required
def api_upload_files(_user_id=None):
    _update_workspace_activity(_user_id)
    workdir = _get_workspace_workdir(_user_id)

    tool = request.form.get('tool', 'to_docx')
    extensions = _get_tool_extensions(tool)

    saved_files = []
    uploaded_files = request.files.getlist('files')

    if len(uploaded_files) > MAX_FILES_PER_UPLOAD:
        return jsonify({'success': False, 'message': f'单次最多上传 {MAX_FILES_PER_UPLOAD} 个文件'})

    workspace_used = 0
    if os.path.exists(workdir):
        for f in os.listdir(workdir):
            fpath = os.path.join(workdir, f)
            if os.path.isfile(fpath):
                workspace_used += os.path.getsize(fpath)

    # 提取文件夹名称（从第一个文件的相对路径中获取）
    folder_name = None
    for file in uploaded_files:
        if file.filename and '/' in file.filename:
            folder_name = file.filename.split('/')[0]
            break

    save_root = os.path.join(workdir, folder_name) if folder_name else workdir
    os.makedirs(save_root, exist_ok=True)

    for file in uploaded_files:
        if not file.filename:
            continue
        fname_lower = file.filename.lower()
        if extensions and not fname_lower.endswith(extensions):
            continue

        file_content = file.read()
        file_size = len(file_content)
        file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({'success': False, 'message':
                f'文件 {file.filename} 超过 {MAX_FILE_SIZE // 1024 // 1024}MB 限制'})

        if workspace_used + file_size > MAX_SESSION_SIZE:
            return jsonify({'success': False, 'message':
                f'工作区总空间超过 {MAX_SESSION_SIZE // 1024 // 1024}MB 限制'})

        filename = os.path.basename(file.filename)
        save_path = os.path.join(save_root, filename)
        with open(save_path, 'wb') as f:
            f.write(file_content)
        workspace_used += file_size
        saved_files.append(filename)

    return jsonify({
        'success': True,
        'files': saved_files,
        'file_count': len(saved_files)
    })

@workspace_bp.route('/check_results', methods=['POST'])
@_login_required
def api_check_results(_user_id=None):
    data = request.get_json()
    _update_workspace_activity(_user_id)
    workdir = _get_workspace_workdir(_user_id)

    if not os.path.exists(workdir):
        return jsonify({'success': True, 'files': [], 'count': 0})

    try:
        result_files = []
        for f in os.listdir(workdir):
            file_path = os.path.join(workdir, f)
            if os.path.isfile(file_path) and not f.startswith('~$'):
                result_files.append({
                    'name': f,
                    'size': os.path.getsize(file_path)
                })
        return jsonify({
            'success': True,
            'files': result_files,
            'count': len(result_files)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@workspace_bp.route('/download_results', methods=['POST'])
@_login_required
def api_download_results(_user_id=None):
    import zipfile, io
    from flask import send_file

    data = request.get_json()
    folder_name = data.get('folder_name', 'results')
    workdir_param = data.get('workdir')

    if workdir_param and not os.path.isabs(workdir_param):
        ws_root = _get_workspace_dir(_user_id)
        workdir = os.path.normpath(os.path.join(ws_root, workdir_param))
    else:
        _update_workspace_activity(_user_id)
        workdir = _get_workspace_workdir(_user_id)

    if not os.path.exists(workdir) or not os.listdir(workdir):
        return jsonify({'success': False, 'message': '无文件可供下载'})

    try:
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(workdir):
                file_path = os.path.join(workdir, f)
                if os.path.isfile(file_path) and not f.startswith('~$'):
                    zf.write(file_path, f)

        memory_file.seek(0)
        download_name = f"{folder_name}_处理结果.zip"

        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'打包失败: {str(e)}'})

@workspace_bp.route('/clear_workspace', methods=['POST'])
@_login_required
def api_clear_workspace(_user_id=None):
    data = request.get_json() or {}
    workdir_param = data.get('workdir')

    if workdir_param and not os.path.isabs(workdir_param):
        ws_root = _get_workspace_dir(_user_id)
        workdir = os.path.normpath(os.path.join(ws_root, workdir_param))
    else:
        workdir = _get_workspace_workdir(_user_id)

    if not os.path.exists(workdir):
        return jsonify({'success': True, 'message': '目录为空'})

    try:
        for f in os.listdir(workdir):
            fpath = os.path.join(workdir, f)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                elif os.path.isdir(fpath):
                    shutil.rmtree(fpath)
            except Exception:
                pass
        return jsonify({'success': True, 'message': '清理完成'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@workspace_bp.route('/build_index_from_metadata', methods=['POST'])
@_login_required
def api_build_index_from_metadata(_user_id=None):
    from tools.to_index import build_index_from_metadata

    data = request.get_json()
    metadata_list = data.get('metadata', [])
    folder_name = data.get('folder_name', 'unknown')

    if not metadata_list:
        return jsonify({'success': False, 'message': '没有文件元信息'})

    _update_workspace_activity(_user_id)
    output_dir = _get_workspace_workdir(_user_id)

    try:
        output_path = build_index_from_metadata(metadata_list, folder_name, output_dir)
        if not output_path:
            return jsonify({'success': False, 'message': '生成索引失败：无有效文件'})

        file_count = len(metadata_list)
        return jsonify({
            'success': True,
            'file_count': file_count,
            'message': f'已索引 {file_count} 个文件'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
