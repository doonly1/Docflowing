"""Workspace 管理 + 文件操作 API"""

import os
import json
import shutil
import tempfile

from flask import Blueprint, request, jsonify, Response, g
from server.auth import login_required
from tools.tool_defs import get_tool_extensions

workspace_bp = Blueprint('workspace', __name__)

# ==================== 常量 ====================

MAX_FILE_SIZE = 90 * 1024 * 1024          # 单文件最大 90MB
MAX_SESSION_SIZE = 900 * 1024 * 1024      # 单会话总大小最大 900MB
MAX_FILES_PER_UPLOAD = 900                # 单次最多上传 900 个文件

# ==================== 运行时目录解析 ====================

def _get_runtime_dir():
    """返回运行时数据目录（绝对路径）。

    优先级：
    1. 环境变量 DOCFLOWING_DATA_DIR（开发者/测试手动指定）
    2. 已打包 / 桌面运行： %APPDATA%\\Docflowing 或 ~/.docflowing
    """
    env_dir = os.environ.get('DOCFLOWING_DATA_DIR') or os.environ.get('DOCFLOWING_RUNTIME_DIR')
    if env_dir:
        d = os.path.abspath(env_dir)
        os.makedirs(d, exist_ok=True)
        return d

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    marker = os.path.join(project_root, 'package.json')
    dev_marker = os.path.join(project_root, 'app_server.py')

    # 判断是否为开发模式：开发模式直接使用项目根下的 workspaces
    if os.path.exists(marker) or os.path.exists(dev_marker):
        d = os.path.join(project_root, 'workspaces')
        os.makedirs(d, exist_ok=True)
        return d

    # 否则使用用户目录
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
        d = os.path.join(appdata, 'Docflowing')
    else:
        d = os.path.join(os.path.expanduser('~'), '.docflowing')
    os.makedirs(d, exist_ok=True)
    return d


def _get_project_root():
    """返回项目源代码根目录（用于定位 UI、知识库扩展等静态资源）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_workspace_dir(user_id=None):
    """运行时数据根目录（旧名兼容，指向与 _get_runtime_dir 相同位置）。"""
    return _get_runtime_dir()

def _get_workspace_resources_dir(user_id):
    res_dir = os.path.join(_get_workspace_dir(user_id), 'resources', 'stamps')
    os.makedirs(res_dir, exist_ok=True)
    return res_dir

# 工具扩展名由 tools/tool_defs.get_tool_extensions() 统一管理
# 旧的 _get_tool_extensions 函数已移至 tools/tool_defs.py

# ==================== 文件列表 ====================

@workspace_bp.route('/list_files', methods=['POST'])
@login_required
def api_list_files():
    data = request.get_json()
    directory = data.get('directory')
    tool = data.get('tool', 'to_docx')
    show_all = data.get('show_all', False)

    if not directory or not os.path.isdir(directory):
        return jsonify({'success': False, 'message': '目录不存在或无效'})

    extensions = get_tool_extensions(tool)

    try:
        files = []
        for f in os.listdir(directory):
            if f.startswith('~$'):
                continue
            file_path = os.path.join(directory, f)
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
    directory = data.get('directory')

    if not directory or not os.path.isdir(directory):
        return jsonify({'success': False, 'message': '目录不存在或无效'})

    try:
        files = []
        for f in os.listdir(directory):
            if not f.startswith('~$'):
                file_path = os.path.join(directory, f)
                files.append({
                    'name': f,
                    'is_dir': os.path.isdir(file_path)
                })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ==================== 文件上传 / 结果检查 / 下载 / 清理 ====================

@workspace_bp.route('/upload_files', methods=['POST', 'OPTIONS'])
@login_required
def api_upload_files():
    # multipart/form-data 时 request.get_json() 为 None，需从 form 中获取
    data = request.get_json() or {}
    tool = request.form.get('tool') or data.get('tool', 'to_docx')
    extensions = get_tool_extensions(tool)

    directory = request.form.get('directory') or data.get('directory')
    if not directory:
        return jsonify({'success': False, 'message': '请指定上传目录'}), 400
    
    os.makedirs(directory, exist_ok=True)

    saved_files = []
    uploaded_files = request.files.getlist('files') if request.files else []

    if len(uploaded_files) > MAX_FILES_PER_UPLOAD:
        return jsonify({'success': False, 'message': f'单次最多上传 {MAX_FILES_PER_UPLOAD} 个文件'})

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

        filename = os.path.basename(file.filename)
        save_path = os.path.join(directory, filename)
        with open(save_path, 'wb') as f:
            f.write(file_content)
        saved_files.append(filename)

    return jsonify({
        'success': True,
        'files': saved_files,
        'file_count': len(saved_files),
        'directory': directory
    })

@workspace_bp.route('/check_results', methods=['POST'])
@login_required
def api_check_results():
    data = request.get_json()
    directory = data.get('directory')

    if not directory or not os.path.isdir(directory):
        return jsonify({'success': True, 'files': [], 'count': 0})

    try:
        result_files = []
        for f in os.listdir(directory):
            file_path = os.path.join(directory, f)
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
@login_required
def api_download_results():
    import zipfile, io
    from flask import send_file

    data = request.get_json()
    folder_name = data.get('folder_name', 'results')
    directory = data.get('directory')

    if not directory or not os.path.isdir(directory):
        return jsonify({'success': False, 'message': '目录不存在'})

    try:
        files_in_dir = [f for f in os.listdir(directory) 
                       if os.path.isfile(os.path.join(directory, f)) and not f.startswith('~$')]
        if not files_in_dir:
            return jsonify({'success': False, 'message': '目录中无文件可供下载'})

        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files_in_dir:
                file_path = os.path.join(directory, f)
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

@workspace_bp.route('/open_folder', methods=['POST'])
@login_required
def api_open_folder():
    """用系统文件管理器打开指定目录"""
    import platform
    import subprocess

    data = request.get_json() or {}
    directory = data.get('directory')

    if not directory or not os.path.isdir(directory):
        return jsonify({'success': False, 'message': '目录不存在或无效'})

    try:
        system = platform.system()
        if system == 'Windows':
            os.startfile(directory)
        elif system == 'Darwin':
            subprocess.run(['open', directory], check=True)
        else:
            subprocess.run(['xdg-open', directory], check=True)
        return jsonify({'success': True, 'message': '已打开目录'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@workspace_bp.route('/clear_workspace', methods=['POST'])
@login_required
def api_clear_workspace():
    data = request.get_json() or {}
    directory = data.get('directory')

    if not directory or not os.path.isdir(directory):
        return jsonify({'success': True, 'message': '目录不存在或无效'})

    try:
        for f in os.listdir(directory):
            fpath = os.path.join(directory, f)
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
@login_required
def api_build_index_from_metadata():
    from tools.to_index import build_index_from_metadata

    data = request.get_json()
    metadata_list = data.get('metadata', [])
    folder_name = data.get('folder_name', 'unknown')
    output_dir = data.get('directory')

    if not metadata_list:
        return jsonify({'success': False, 'message': '没有文件元信息'})

    if not output_dir:
        return jsonify({'success': False, 'message': '请指定输出目录'})

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
