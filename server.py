# -*- coding: utf-8 -*-
"""
公文处理工具后端服务
"""

import os
import sys
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)

# 工具脚本映射
TOOL_SCRIPTS = {
    'to_docx': 'to_docx.py',
    'to_index': 'to_index.py',
    'to_compare': 'to_compare.py',
    'to_pdf': 'to_pdf.py',
    'to_pageNum': 'to_pageNum.py',
    'to_redhead': 'to_redhead.py'
}

# 首页路由
@app.route('/')
def index():
    return app.send_static_file('index.html')

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@app.route('/list_files', methods=['POST'])
def api_list_files():
    """列出目录中的文档文件"""
    data = request.get_json()
    workdir = data.get('workdir')
    tool = data.get('tool', 'to_docx')
    session_id = data.get('session_id')  # 支持会话ID
    show_all = data.get('show_all', False)  # 是否显示所有文件（包含上传的原始文件）

    # 支持临时目录路径格式
    if workdir and workdir.startswith('/temp_workdirs/'):
        session_id = workdir.replace('/temp_workdirs/', '')
        workdir = None

    # 如果有session_id，获取会话目录
    if session_id:
        workdir = get_user_temp_dir(session_id)

    if not workdir or not os.path.isdir(workdir):
        return jsonify({'success': False, 'message': '目录不存在'})

    # 各工具支持的文件类型
    tool_extensions = {
        'to_docx': ('.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'),
        'to_index': ('.docx', '.doc'),
        'to_compare': ('.docx', '.doc'),
        'to_pdf': ('.docx', '.doc'),
        'to_pageNum': ('.docx', '.doc'),
        'to_redhead': ('.docx',)
    }

    extensions = tool_extensions.get(tool, ('.docx',))

    try:
        files = []
        for f in os.listdir(workdir):
            if f.startswith('~$'):
                continue
            file_path = os.path.join(workdir, f)
            # 只显示文件，不显示目录
            if os.path.isfile(file_path):
                # show_all=true 时显示所有文件，否则按工具类型过滤
                if show_all or f.lower().endswith(extensions):
                    files.append({
                        'name': f,
                        'is_dir': False
                    })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/list_dir', methods=['POST'])
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


@app.route('/select_folder', methods=['POST'])
def api_select_folder():
    """打开文件夹选择对话框"""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    root.attributes('-topmost', True)  # 窗口置顶
    folder = filedialog.askdirectory()
    root.destroy()

    if folder:
        return jsonify({'success': True, 'path': folder})
    else:
        return jsonify({'success': False, 'message': '取消选择'})


@app.route('/get_desktop', methods=['POST'])
def api_get_desktop():
    """获取用户桌面路径"""
    import os
    home = os.path.expanduser('~')
    desktop = os.path.join(home, 'Desktop')
    return jsonify({'success': True, 'path': desktop})


@app.route('/open_folder', methods=['POST'])
def api_open_folder():
    """打开指定目录"""
    import subprocess
    data = request.get_json()
    path = data.get('path')

    if not path:
        return jsonify({'success': False, 'message': '未指定路径'})

    if not os.path.exists(path):
        return jsonify({'success': False, 'message': '目录不存在'})

    try:
        # Windows 系统使用 explorer 打开目录
        subprocess.Popen(['explorer', path])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/get_server_config', methods=['GET'])
def api_get_server_config():
    """获取服务器默认配置"""
    import yaml
    
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.yaml')
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取配置失败: {str(e)}'})


@app.route('/get_last_workdir', methods=['GET'])
def api_get_last_workdir():
    """获取最近使用的文件夹路径（从用户独立的配置文件读取）"""
    import yaml
    
    # 用户配置文件路径：~/.config/doc_tool/config.yaml
    user_config_dir = os.path.join(os.path.expanduser('~'), '.config', 'doc_tool')
    config_path = os.path.join(user_config_dir, 'config.yaml')
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            last_workdir = config.get('last_workdir', '') if config else ''
            return jsonify({'success': True, 'path': last_workdir})
        return jsonify({'success': True, 'path': ''})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/save_last_workdir', methods=['POST'])
def api_save_last_workdir():
    """保存最近使用的文件夹路径到用户独立的config.yaml"""
    import yaml
    
    data = request.get_json()
    workdir = data.get('path', '')
    
    # 用户配置文件路径：~/.config/doc_tool/config.yaml
    user_config_dir = os.path.join(os.path.expanduser('~'), '.config', 'doc_tool')
    config_path = os.path.join(user_config_dir, 'config.yaml')
    
    try:
        # 读取现有配置（保留其他配置字段）
        config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        
        # 只更新 last_workdir，保留其他字段
        config['last_workdir'] = workdir
        
        # 确保目录存在
        os.makedirs(user_config_dir, exist_ok=True)
        
        # 写回配置文件
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/run_tool_with_config', methods=['POST'])
def api_run_tool_with_config():
    """执行工具（支持自定义配置）"""
    data = request.get_json()
    
    tool = data.get('tool')
    workdir = data.get('workdir')
    files = data.get('files')
    user_config = data.get('userConfig')
    
    if not tool:
        return jsonify({'success': False, 'message': '未指定工具'})
    if not workdir:
        return jsonify({'success': False, 'message': '未指定工作目录'})
    
    # 支持临时目录路径格式 /temp_workdirs/xxx
    session_id = None
    if workdir.startswith('/temp_workdirs/'):
        session_id = workdir.replace('/temp_workdirs/', '')
        workdir = get_user_temp_dir(session_id)
        # 更新会话活动时间
        update_session_activity(session_id)
    
    if not os.path.isdir(workdir):
        return jsonify({'success': False, 'message': f'目录不存在: {workdir}'})
    
    import subprocess
    import tempfile
    import yaml
    from flask import Response
    import json
    
    if tool not in TOOL_SCRIPTS:
        return jsonify({'success': False, 'message': f'未知的工具: {tool}'})
    
    script = TOOL_SCRIPTS[tool]
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    
    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'脚本不存在: {script}'})
    
    def generate():
        try:
            # 创建临时配置文件（如果用户提供了配置）
            temp_config_path = None
            env = os.environ.copy()
            
            if user_config:
                try:
                    # 创建临时目录和配置文件
                    temp_dir = tempfile.mkdtemp()
                    temp_config_path = os.path.join(temp_dir, 'config.yaml')
                    
                    with open(temp_config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(user_config, f, allow_unicode=True, default_flow_style=False)
                    
                    # 设置环境变量，让工具知道使用自定义配置
                    env['USER_CONFIG_PATH'] = temp_config_path
                    
                except Exception as e:
                    yield f'data: {json.dumps({"type": "end", "success": False, "error": f"创建临时配置文件失败: {str(e)}"})}\n\n'
                    return
            
            # 构建命令行参数
            cmd_args = [sys.executable, "-u", script_path]
            
            # 对to_compare，如果提供了文件，将文件完整路径传递给脚本
            if files and tool == 'to_compare' and len(files) >= 2:
                # 添加原稿和终稿文件的完整路径
                for f in files[:2]:  # 只取前两个文件
                    full_path = os.path.join(workdir, f)
                    cmd_args.append(full_path)
            else:
                # 其他情况只传递工作目录
                cmd_args.append(workdir)

            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=workdir,
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
            
            # 清理临时文件
            if temp_config_path and os.path.exists(os.path.dirname(temp_config_path)):
                try:
                    import shutil
                    shutil.rmtree(os.path.dirname(temp_config_path))
                except:
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


@app.route('/auto_save_config', methods=['POST'])
def api_auto_save_config():
    """自动保存配置到用户 ~/.config/ 目录"""
    import yaml
    
    data = request.get_json()
    user_config = data.get('userConfig')
    
    if not user_config:
        return jsonify({'success': False})
    
    try:
        # 保存到 ~/.config/doc_tool/
        config_dir = os.path.join(os.path.expanduser('~'), '.config', 'doc_tool')
        os.makedirs(config_dir, exist_ok=True)
        
        save_path = os.path.join(config_dir, 'config.yaml')
        
        # 读取现有配置，保留 last_workdir
        existing_config = {}
        if os.path.exists(save_path):
            with open(save_path, 'r', encoding='utf-8') as f:
                existing_config = yaml.safe_load(f) or {}
        
        # 合并配置：保留 last_workdir，只更新其他配置
        last_workdir = existing_config.get('last_workdir', '')
        user_config['last_workdir'] = last_workdir
        
        with open(save_path, 'w', encoding='utf-8') as f:
            yaml.dump(user_config, f, allow_unicode=True, default_flow_style=False)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False})


# ==================== 文件上传处理功能 ====================

# 存储用户会话的临时目录
user_sessions = {}

def get_user_temp_dir(session_id):
    """获取用户的临时工作目录"""
    temp_base = os.path.join(os.path.dirname(__file__), 'temp_workdirs')
    user_dir = os.path.join(temp_base, session_id)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def cleanup_old_sessions():
    """清理超过4小时未活动的临时目录"""
    temp_base = os.path.join(os.path.dirname(__file__), 'temp_workdirs')
    if not os.path.exists(temp_base):
        return
    
    current_time = time.time()
    for session_id in os.listdir(temp_base):
        session_dir = os.path.join(temp_base, session_id)
        if os.path.isdir(session_dir):
            try:
                # 检查会话是否活跃
                session_info = user_sessions.get(session_id, {})
                last_active = session_info.get('last_active', 0)
                
                # 如果没有会话记录，使用目录修改时间
                if last_active == 0:
                    last_active = os.path.getmtime(session_dir)
                
                # 4小时无活动则清理
                if current_time - last_active > 14400:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    user_sessions.pop(session_id, None)
            except:
                pass

def update_session_activity(session_id):
    """更新会话活动时间"""
    if session_id in user_sessions:
        user_sessions[session_id]['last_active'] = time.time()

@app.route('/clear_session', methods=['POST'])
def api_clear_session():
    """清理会话目录中的所有文件"""
    import shutil
    data = request.get_json() if request.is_json else {}
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'success': False, 'message': '会话ID不存在'})
    
    user_dir = get_user_temp_dir(session_id)
    if not os.path.exists(user_dir):
        return jsonify({'success': True, 'message': '目录不存在'})
    
    try:
        # 删除目录中的所有文件
        for f in os.listdir(user_dir):
            fpath = os.path.join(user_dir, f)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                elif os.path.isdir(fpath):
                    shutil.rmtree(fpath)
            except:
                pass
        
        return jsonify({'success': True, 'message': '清理完成'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/upload_files', methods=['POST'])
def api_upload_files():
    """接收用户上传的文件，保存到临时目录"""
    import uuid
    
    # 清理旧会话
    cleanup_old_sessions()
    
    # 获取或创建会话ID
    session_id = request.form.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # 获取用户原始路径（用于显示）
    original_path = request.form.get('original_path', '未知路径')
    
    # 获取该工具支持的文件扩展名
    tool = request.form.get('tool', 'to_docx')
    tool_extensions = {
        'to_docx': ('.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'),
        'to_index': ('.docx', '.doc'),
        'to_compare': ('.docx', '.doc'),
        'to_pdf': ('.docx', '.doc'),
        'to_pageNum': ('.docx', '.doc'),
        'to_redhead': ('.docx',)
    }
    extensions = tool_extensions.get(tool, ('.docx',))
    
    # 创建用户临时目录
    user_dir = get_user_temp_dir(session_id)
    
    # 保存上传的文件（保留原有文件）
    saved_files = []
    uploaded_files = request.files.getlist('files')
    
    for file in uploaded_files:
        if file.filename:
            # 安全检查：只保存允许的文件类型
            if file.filename.lower().endswith(extensions):
                filename = os.path.basename(file.filename)  # 防止路径遍历
                save_path = os.path.join(user_dir, filename)
                file.save(save_path)
                saved_files.append(filename)
    
    # 保存会话信息，记录上传完成时间
    user_sessions[session_id] = {
        'original_path': original_path,
        'created_at': time.time(),
        'last_active': time.time(),
        'upload_finished': time.time(),  # 记录上传完成时间，用于过滤原始文件
        'files': saved_files,
        'ip': request.remote_addr  # 记录用户IP
    }
    
    return jsonify({
        'success': True,
        'session_id': session_id,
        'server_path': user_dir,
        'files': saved_files,
        'original_path': original_path
    })


@app.route('/download_results', methods=['POST'])
def api_download_results():
    """将处理结果打包返回给用户"""
    import zipfile
    import io
    
    data = request.get_json()
    session_id = data.get('session_id')
    original_path = data.get('original_path', 'results')
    
    if not session_id:
        return jsonify({'success': False, 'message': '会话ID不存在'})
    
    # 更新会话活动时间
    update_session_activity(session_id)
    
    user_dir = get_user_temp_dir(session_id)
    if not os.path.exists(user_dir):
        return jsonify({'success': False, 'message': '工作目录不存在'})
    
    try:
        # 获取上传完成时间，用于过滤原始文件
        session_info = user_sessions.get(session_id, {})
        upload_time = session_info.get('upload_finished', 0)
        metadata_only = session_info.get('metadata_only', False)
        
        # 创建内存中的ZIP文件
        memory_file = io.BytesIO()
        
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(user_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # 元信息模式：打包所有文件；普通模式：只打包处理结果
                    if metadata_only or os.path.getmtime(file_path) > upload_time:
                        arcname = os.path.relpath(file_path, user_dir)
                        zf.write(file_path, arcname)
        
        memory_file.seek(0)
        
        # 生成下载文件名
        folder_name = os.path.basename(original_path) if original_path else 'results'
        download_name = f"{folder_name}_处理结果.zip"
        
        from flask import send_file
        response = send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=download_name
        )
        
        # 下载完成后清理会话目录
        @response.call_on_close
        def cleanup_after_download():
            if session_id and session_id in user_sessions:
                del user_sessions[session_id]
            if os.path.exists(user_dir):
                shutil.rmtree(user_dir, ignore_errors=True)
        
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'打包失败: {str(e)}'})


@app.route('/check_results', methods=['POST'])
def api_check_results():
    """检查处理结果文件"""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'success': False, 'message': '会话ID不存在'})
    
    # 更新会话活动时间
    update_session_activity(session_id)
    
    user_dir = get_user_temp_dir(session_id)
    if not os.path.exists(user_dir):
        return jsonify({'success': False, 'message': '工作目录不存在'})
    
    try:
        # 获取上传完成时间，用于过滤处理结果文件
        session_info = user_sessions.get(session_id, {})
        upload_time = session_info.get('upload_finished', 0)
        metadata_only = session_info.get('metadata_only', False)
        
        # 获取所有生成的文件
        result_files = []
        for f in os.listdir(user_dir):
            file_path = os.path.join(user_dir, f)
            if os.path.isfile(file_path):
                # 跳过临时文件
                if f.startswith('~$'):
                    continue
                # 元信息模式：没有上传原始文件，返回所有文件
                # 普通模式：只返回上传完成后修改的文件（处理结果）
                if metadata_only or os.path.getmtime(file_path) > upload_time:
                    result_files.append({
                        'name': f,
                        'size': os.path.getsize(file_path)
                    })
        
        return jsonify({
            'success': True,
            'files': result_files,
            'count': len(result_files),
            'server_path': user_dir
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/build_index_from_metadata', methods=['POST'])
def api_build_index_from_metadata():
    """从前端上传的文件元信息直接构建索引（无需上传文件内容）"""
    import uuid
    from to_index import build_index_from_metadata

    data = request.get_json()
    metadata_list = data.get('metadata', [])
    folder_name = data.get('folder_name', 'unknown')
    session_id = data.get('session_id')

    if not metadata_list:
        return jsonify({'success': False, 'message': '没有文件元信息'})

    # 创建或复用临时目录
    if not session_id:
        session_id = str(uuid.uuid4())
    output_dir = get_user_temp_dir(session_id)

    try:
        output_path = build_index_from_metadata(metadata_list, folder_name, output_dir)
        if not output_path:
            return jsonify({'success': False, 'message': '生成索引失败：无有效文件'})

        # 记录会话信息
        user_sessions[session_id] = {
            'original_path': folder_name,
            'created_at': time.time(),
            'last_active': time.time(),
            'upload_finished': time.time(),
            'files': ['file_index.xlsx'],
            'ip': request.remote_addr,
            'metadata_only': True  # 标记为纯元信息模式
        }

        file_count = len(metadata_list)
        return jsonify({
            'success': True,
            'session_id': session_id,
            'file_count': file_count,
            'message': f'已索引 {file_count} 个文件'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/load_config_from_path', methods=['GET'])
def api_load_config_from_path():
    """从 ~/.config/ 目录加载配置"""
    try:
        config_path = os.path.join(os.path.expanduser('~'), '.config', 'doc_tool', 'config.yaml')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                import yaml
                config = yaml.safe_load(f)
            return jsonify({'success': True, 'config': config, 'path': config_path})
        
        return jsonify({'success': False})
    except Exception as e:
        return jsonify({'success': False})


if __name__ == '__main__':
    print("=" * 50)
    print("文档处理服务")
    print("访问地址: http://localhost:5000")
    print("=" * 50)

    # 打开浏览器（只在主进程中执行，避免debug模式下重复打开）
    import webbrowser
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        webbrowser.open('http://localhost:5000')

    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)