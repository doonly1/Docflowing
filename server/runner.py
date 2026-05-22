"""工具脚本执行 + SSE 流式输出"""

import os
import json
import sys
import subprocess

from flask import Blueprint, request, jsonify, Response, stream_with_context, g
from server.auth import login_required
from server.workspace import _get_workspace_dir
from tools.tool_defs import TOOL_SCRIPTS

runner_bp = Blueprint('runner', __name__)


@runner_bp.route('/run_tool_with_config', methods=['POST'])
@login_required
def api_run_tool_with_config():
    data = request.get_json()

    tool = data.get('tool')
    directory = data.get('directory')
    files = data.get('files')

    if not tool:
        return jsonify({'success': False, 'message': '未指定工具'})

    if not directory:
        return jsonify({'success': False, 'message': '未指定目录'})
    if not os.path.isdir(directory):
        return jsonify({'success': False, 'message': f'目录不存在: {directory}'})

    if tool not in TOOL_SCRIPTS:
        return jsonify({'success': False, 'message': f'未知的工具: {tool}'})

    script = TOOL_SCRIPTS[tool]
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), script)

    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'脚本不存在: {script}'})

    _request_id = g.get('request_id', '')
    _user_id = g.user_id

    def generate():
        try:
            env = os.environ.copy()
            env['REQUEST_ID'] = _request_id
            env['PYTHONPATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env['USER_ID'] = _user_id

            cmd_args = [sys.executable, "-u", script_path]

            if files:
                for f in files:
                    full_path = os.path.join(directory, f) if not os.path.isabs(f) else f
                    cmd_args.append(full_path)
            else:
                cmd_args.append(directory)

            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=directory,
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

            success = process.returncode == 0
            if not success:
                error_msg = '\n'.join(output_lines) if output_lines else "执行失败"
                yield f'data: {json.dumps({"type": "end", "success": False, "error": error_msg})}\n\n'
            else:
                yield f'data: {json.dumps({"type": "end", "success": True})}\n\n'

        except Exception as e:
            yield f'data: {json.dumps({"type": "end", "success": False, "error": str(e)})}\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
