# -*- coding: utf-8 -*-
"""
公文处理工具后端服务
"""

import os
import sys
import time
import json
import uuid
import yaml
import shutil
import hashlib
import secrets
import tempfile
import subprocess
from functools import wraps
from flask import Flask, request, jsonify, g, Response
from flask_cors import CORS

from logging_config import setup_logging, set_request_id, get_logger

setup_logging()
logger = get_logger(__name__)

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)


@app.before_request
def _capture_request_id():
    req_id = request.headers.get('X-Request-Id') or str(uuid.uuid4())
    set_request_id(req_id)
    g.request_id = req_id


@app.after_request
def _inject_request_id(response):
    response.headers['X-Request-Id'] = g.get('request_id', '')
    return response

# 上传限制
MAX_FILE_SIZE = 50 * 1024 * 1024       # 单文件最大 50MB
MAX_SESSION_SIZE = 200 * 1024 * 1024    # 单会话总大小最大 200MB
MAX_FILES_PER_UPLOAD = 99              # 单次最多上传 99 个文件
WORKSPACE_EXPIRE_DAYS = 7              # workspace 无人访问自动清理天数

app.config['MAX_CONTENT_LENGTH'] = MAX_SESSION_SIZE  # Flask 请求体大小限制

# 工具脚本映射
TOOL_SCRIPTS = {
    'to_docx': 'to_docx.py',
    'to_index': 'to_index.py',
    'to_compare': 'to_compare.py',
    'to_pdf': 'to_pdf.py',
    'to_pageNum': 'to_pageNum.py',
    'to_redhead': 'to_redhead.py'
}

# ==================== Token 认证系统 ====================

SECRET_KEY = os.environ.get('DOCPROC_SECRET', secrets.token_hex(32))

def _get_auth_data_dir():
    auth_dir = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'auth')
    os.makedirs(auth_dir, exist_ok=True)
    return auth_dir

def _get_users_path():
    return os.path.join(_get_auth_data_dir(), 'users.json')

def _get_tokens_path():
    return os.path.join(_get_auth_data_dir(), 'tokens.json')

def _load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return f'{salt}${pwd_hash}'

def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, pwd_hash = stored.split('$', 1)
        computed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
        return computed == pwd_hash
    except Exception:
        return False

def _generate_token() -> str:
    return secrets.token_hex(32)

def _get_user_id_from_token(token: str) -> str | None:
    tokens = _load_json(_get_tokens_path())
    return tokens.get(token)

def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')
        token = None
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        elif auth_header:
            token = auth_header

        if not token:
            data = request.get_json(silent=True) or {}
            token = data.get('token') or data.get('client_id')

        if not token:
            token = request.form.get('token') or request.form.get('client_id')

        if not token:
            return jsonify({'success': False, 'message': '未登录，请先登录'}), 401

        user_id = _get_user_id_from_token(token)
        if not user_id:
            return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401

        kwargs['_user_id'] = user_id
        return f(*args, **kwargs)
    return decorated

# ==================== 用户配置持久化（按用户隔离） ====================

def _get_config_base_dir():
    config_dir = os.path.join(os.path.expanduser('~'), '.config', 'DocProc')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def _get_user_config_dir():
    users_dir = os.path.join(_get_config_base_dir(), 'users')
    os.makedirs(users_dir, exist_ok=True)
    return users_dir

def _get_user_config_path(user_id):
    return os.path.join(_get_user_config_dir(), f'{user_id}.yaml')

def _ensure_user_config(user_id):
    config_path = _get_user_config_path(user_id)
    if not os.path.exists(config_path):
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'config', 'config.yaml')
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            if 'last_workdir' in config:
                del config['last_workdir']
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        except Exception:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump({}, f, allow_unicode=True, default_flow_style=False)
    return config_path

# ==================== Workspace 管理（按用户隔离） ====================

def _get_workspace_dir(user_id):
    ws_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
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
    ws_dir = _get_workspace_dir(user_id)
    touch_file = os.path.join(ws_dir, '.last_active')
    try:
        os.makedirs(ws_dir, exist_ok=True)
        with open(touch_file, 'w') as f:
            f.write(str(time.time()))
    except Exception:
        pass


def _cleanup_expired_workspaces():
    """清理过期 workspace（超过 WORKSPACE_EXPIRE_DAYS 天未访问）"""
    ws_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspaces')
    if not os.path.exists(ws_root):
        return
    now = time.time()
    expire_sec = WORKSPACE_EXPIRE_DAYS * 86400
    for cid in os.listdir(ws_root):
        ws_dir = os.path.join(ws_root, cid)
        if not os.path.isdir(ws_dir):
            continue
        touch_file = os.path.join(ws_dir, '.last_active')
        try:
            if os.path.exists(touch_file):
                with open(touch_file, 'r') as f:
                    last_active = float(f.read().strip())
            else:
                last_active = os.path.getmtime(ws_dir)
            if now - last_active > expire_sec:
                shutil.rmtree(ws_dir, ignore_errors=True)
        except Exception:
            pass


def _get_tool_extensions(tool):
    """获取工具支持的文件扩展名"""
    ext_map = {
        'to_docx': ('.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'),
        'to_index': ('.docx', '.doc', '.pdf', '.xlsx'),  # 不过滤
        'to_compare': ('.docx', '.doc'),
        'to_pdf': ('.docx', '.doc'),
        'to_pageNum': ('.docx', '.doc'),
        'to_redhead': ('.docx',)
    }
    return ext_map.get(tool, ('.docx',))


# 首页路由
@app.route('/')
def index():
    return app.send_static_file('index.html')

# ==================== 认证 API ====================

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '请求数据不能为空'})

    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'})
    if len(username) < 2 or len(username) > 32:
        return jsonify({'success': False, 'message': '用户名长度为 2-32 个字符'})
    if not password or len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少 6 个字符'})

    users = _load_json(_get_users_path())
    for uid, uinfo in users.items():
        if uinfo.get('username') == username:
            return jsonify({'success': False, 'message': '用户名已存在'})

    user_id = str(uuid.uuid4())
    users[user_id] = {
        'username': username,
        'password': _hash_password(password),
        'created_at': time.time()
    }
    _save_json(_get_users_path(), users)

    token = _generate_token()
    tokens = _load_json(_get_tokens_path())
    tokens[token] = user_id
    _save_json(_get_tokens_path(), tokens)

    _ensure_user_config(user_id)

    return jsonify({
        'success': True,
        'token': token,
        'username': username,
        'message': '注册成功'
    })

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '请求数据不能为空'})

    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})

    users = _load_json(_get_users_path())
    user_id = None
    for uid, uinfo in users.items():
        if uinfo.get('username') == username:
            if _verify_password(password, uinfo.get('password', '')):
                user_id = uid
            break

    if not user_id:
        return jsonify({'success': False, 'message': '用户名或密码错误'})

    token = _generate_token()
    tokens = _load_json(_get_tokens_path())
    tokens[token] = user_id
    _save_json(_get_tokens_path(), tokens)

    _ensure_user_config(user_id)

    return jsonify({
        'success': True,
        'token': token,
        'username': username,
        'message': '登录成功'
    })

@app.route('/api/logout', methods=['POST'])
def api_logout():
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    elif auth_header:
        token = auth_header

    if not token:
        data = request.get_json(silent=True) or {}
        token = data.get('token') or data.get('client_id')

    if token:
        tokens = _load_json(_get_tokens_path())
        tokens.pop(token, None)
        _save_json(_get_tokens_path(), tokens)

    return jsonify({'success': True, 'message': '已退出登录'})

# 请求体过大处理
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'success': False, 'message': f'上传总大小超过 {MAX_SESSION_SIZE // 1024 // 1024}MB 限制'}), 413

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@app.route('/list_files', methods=['POST'])
@_login_required
def api_list_files(_user_id=None):
    data = request.get_json()
    workdir = data.get('workdir')
    tool = data.get('tool', 'to_docx')
    token = data.get('token') or data.get('client_id')
    show_all = data.get('show_all', False)

    if not workdir and (token or _user_id):
        _update_workspace_activity(_user_id)
        workdir = _get_workspace_workdir(_user_id)

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
    """打开文件夹选择对话框（跨平台兼容版本）"""
    import platform
    import os
    
    system = platform.system()
    
    # 检查是否在无图形界面的 Linux 服务器环境
    if system == 'Linux' and 'DISPLAY' not in os.environ:
        # 无图形环境，返回当前工作目录作为默认路径
        current_dir = os.getcwd()
        return jsonify({'success': True, 'path': current_dir, 'message': '无图形界面，使用当前目录'})
    
    # 有图形环境，尝试使用 tkinter
    try:
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
    except ImportError:
        # tkinter 不可用（如某些 Linux 发行版未安装）
        return jsonify({'success': False, 'message': '图形界面不可用，请通过其他方式指定路径'})
    except Exception as e:
        # 其他错误
        return jsonify({'success': False, 'message': f'文件夹选择失败: {str(e)}'})


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
        import platform
        system = platform.system()
        if system == 'Windows':
            subprocess.Popen(['explorer', path])
        elif system == 'Darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ==================== 配置管理（按用户持久化） ====================

@app.route('/get_config', methods=['POST'])
@_login_required
def api_get_config(_user_id=None):
    data = request.get_json() if request.is_json else {}
    config_path = _ensure_user_config(_user_id)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取配置失败: {str(e)}'})

@app.route('/save_config', methods=['POST'])
@_login_required
def api_save_config(_user_id=None):
    data = request.get_json()
    config = data.get('config')

    if not config:
        return jsonify({'success': False, 'message': '配置不能为空'})

    config_path = _ensure_user_config(_user_id)
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存配置失败: {str(e)}'})

@app.route('/save_workdir', methods=['POST'])
@_login_required
def api_save_workdir(_user_id=None):
    data = request.get_json()
    workdir = data.get('workdir')

    config_path = _ensure_user_config(_user_id)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        config['last_workdir'] = workdir
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/run_tool_with_config', methods=['POST'])
@_login_required
def api_run_tool_with_config(_user_id=None):
    data = request.get_json()
    
    tool = data.get('tool')
    workdir = data.get('workdir')
    files = data.get('files')
    user_config = data.get('userConfig')
    token = data.get('token') or data.get('client_id')
    
    if not tool:
        return jsonify({'success': False, 'message': '未指定工具'})
    
    if not workdir and (token or _user_id):
        _update_workspace_activity(_user_id)
        workdir = _get_workspace_workdir(_user_id)
    
    if not workdir:
        return jsonify({'success': False, 'message': '未指定工作目录'})
    if not os.path.isdir(workdir):
        return jsonify({'success': False, 'message': f'目录不存在: {workdir}'})
    
    if tool not in TOOL_SCRIPTS:
        return jsonify({'success': False, 'message': f'未知的工具: {tool}'})
    
    script = TOOL_SCRIPTS[tool]
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    
    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'脚本不存在: {script}'})
    
    current_request_id = g.get('request_id', '')

    def generate():
        try:
            # 创建临时配置文件（如果用户提供了配置）
            temp_config_path = None
            env = os.environ.copy()
            env['REQUEST_ID'] = current_request_id
            
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
            
            # 如果提供了文件列表，逐个传递文件路径
            # 所有工具脚本现在都支持单文件处理
            if files:
                for f in files:
                    full_path = os.path.join(workdir, f) if not os.path.isabs(f) else f
                    cmd_args.append(full_path)
            else:
                # 未选文件时传递工作目录（工具会处理目录下所有匹配文件）
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





# ==================== Workspace 文件上传/下载/清理 ====================

@app.route('/upload_files', methods=['POST', 'OPTIONS'])
@_login_required
def api_upload_files(_user_id=None):
    _cleanup_expired_workspaces()

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
        save_path = os.path.join(workdir, filename)
        with open(save_path, 'wb') as f:
            f.write(file_content)
        workspace_used += file_size
        saved_files.append(filename)

    return jsonify({
        'success': True,
        'files': saved_files,
        'file_count': len(saved_files)
    })

@app.route('/check_results', methods=['POST'])
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

@app.route('/download_results', methods=['POST'])
@_login_required
def api_download_results(_user_id=None):
    import zipfile
    import io

    data = request.get_json()
    folder_name = data.get('folder_name', 'results')

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

        from flask import send_file
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'打包失败: {str(e)}'})

@app.route('/clear_workspace', methods=['POST'])
@_login_required
def api_clear_workspace(_user_id=None):
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

@app.route('/build_index_from_metadata', methods=['POST'])
@_login_required
def api_build_index_from_metadata(_user_id=None):
    from to_index import build_index_from_metadata

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



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))

    logger.info("=" * 50)
    logger.info("文档处理服务")
    logger.info("访问地址: http://0.0.0.0:%s", port)
    logger.info("=" * 50)

    # 本地运行时打开浏览器（云端部署时无显示器，跳过）
    if port == 5000:
        import webbrowser
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            webbrowser.open(f'http://localhost:{port}')

    app.run(host='0.0.0.0', port=port, debug=(port == 5000), threaded=True)