"""工具脚本执行 + SSE 流式输出（进程内执行，不启动子进程）"""

import os
import json
import threading
import time

from flask import Blueprint, request, jsonify, Response, stream_with_context, g
from server.auth import login_required
from server.workspace import _get_workspace_dir
from tools.tool_defs import get_tool_script_path
from server.tool_runner import run_tool_in_process

# 单个工具执行最大秒数（文档处理可能较慢，设为 10 分钟）
_TOOL_TIMEOUT_SECONDS = 600

runner_bp = Blueprint('runner', __name__)

# SSE 并发限制
_SSE_SEMAPHORE = threading.BoundedSemaphore(3)


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

    if tool not in ['to_docx', 'to_index', 'to_compare', 'to_pdf', 'to_pageNum', 'to_redhead']:
        return jsonify({'success': False, 'message': f'未知的工具: {tool}'})

    script_path = get_tool_script_path(tool)
    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'脚本不存在: {tool}'})

    target_path = directory
    file_list = files if files else []

    def generate():
        acquired = _SSE_SEMAPHORE.acquire(blocking=False)
        if not acquired:
            yield f'data: {json.dumps({"type": "end", "success": False, "error": "服务器繁忙，请稍后再试"})}\n\n'
            return
        try:
            yield from run_tool_in_process(tool, file_list, target_path, script_path)
        except Exception as e:
            yield f'data: {json.dumps({"type": "end", "success": False, "error": str(e)})}\n\n'
        finally:
            _SSE_SEMAPHORE.release()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')