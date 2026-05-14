"""工具脚本执行 + SSE 流式输出"""

import os
import json
import sys
import yaml
import tempfile
import shutil
import subprocess

from flask import Blueprint, request, jsonify, Response, g
from server.auth import login_required
from server.workspace import _get_workspace_dir, _get_workspace_workdir, _update_workspace_activity

runner_bp = Blueprint('runner', __name__)

# 工具脚本映射
TOOL_SCRIPTS = {
    'to_docx': os.path.join('tools', 'to_docx.py'),
    'to_index': os.path.join('tools', 'to_index.py'),
    'to_compare': os.path.join('tools', 'to_compare.py'),
    'to_pdf': os.path.join('tools', 'to_pdf.py'),
    'to_pageNum': os.path.join('tools', 'to_pageNum.py'),
    'to_redhead': os.path.join('tools', 'to_redhead.py')
}


@runner_bp.route('/run_tool_with_config', methods=['POST'])
@login_required
def api_run_tool_with_config():
    data = request.get_json()

    tool = data.get('tool')
    workdir = data.get('workdir')
    files = data.get('files')
    user_config = data.get('userConfig')
    token = data.get('token') or data.get('client_id')

    if not tool:
        return jsonify({'success': False, 'message': '未指定工具'})

    if workdir and not os.path.isabs(workdir):
        ws_root = _get_workspace_dir(g.user_id)
        workdir = os.path.normpath(os.path.join(ws_root, workdir))

    if not workdir and (token or g.user_id):
        _update_workspace_activity(g.user_id)
        workdir = _get_workspace_workdir(g.user_id)

    if not workdir:
        return jsonify({'success': False, 'message': '未指定工作目录'})
    if not os.path.isdir(workdir):
        return jsonify({'success': False, 'message': f'目录不存在: {workdir}'})

    if tool not in TOOL_SCRIPTS:
        return jsonify({'success': False, 'message': f'未知的工具: {tool}'})

    script = TOOL_SCRIPTS[tool]
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), script)

    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'脚本不存在: {script}'})

    current_request_id = g.get('request_id', '')

    def generate():
        try:
            temp_config_path = None
            env = os.environ.copy()
            env['REQUEST_ID'] = current_request_id
            env['PYTHONPATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            if user_config:
                try:
                    temp_dir = tempfile.mkdtemp()
                    temp_config_path = os.path.join(temp_dir, 'config.yaml')

                    with open(temp_config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(user_config, f, allow_unicode=True, default_flow_style=False)

                    env['USER_CONFIG_PATH'] = temp_config_path

                except Exception as e:
                    yield f'data: {json.dumps({"type": "end", "success": False, "error": f"创建临时配置文件失败: {str(e)}"})}\n\n'
                    return

            cmd_args = [sys.executable, "-u", script_path]

            if files:
                for f in files:
                    full_path = os.path.join(workdir, f) if not os.path.isabs(f) else f
                    cmd_args.append(full_path)
            else:
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
