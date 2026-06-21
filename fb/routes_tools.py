"""文件库工具执行和文档转换"""

import os
import sys
import json
import threading
from flask import Blueprint, request, jsonify, Response, stream_with_context, g

from server.auth import login_required
from fb.database import get_db
from fb.decorators import _require_fb_permission, require_fb_perm, _ensure_local_fb_route, _get_node_identity
from server.tool_runner import run_tool_in_process
from tools.tool_defs import get_tool_script_path, TOOL_EXTENSIONS

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')

# SSE 并发限制：最多允许 3 个同时运行的 tool 流
_SSE_SEMAPHORE = threading.BoundedSemaphore(3)


def _run_tool_in_process(tool, files, target_path, script_path):
    """代理到 server.tool_runner.run_tool_in_process"""
    yield from run_tool_in_process(tool, files, target_path, script_path)


@fb_bp.route('/<fb_id>/run-tool', methods=['POST'])
@login_required
@require_fb_perm('edit')
@_ensure_local_fb_route
def run_tool_on_fb(filebase_id):
    """在文件库上执行工具"""
    if getattr(g, 'is_remote_fb', False):
        from p2p import proxy as p2p_proxy
        node = _get_node_identity()
        info = g.remote_fb_info
        data = request.get_json() or {}
        resp = p2p_proxy.remote_run_tool(info['owner_addr'], node, filebase_id, data.get('tool'), data.get('files', []), data.get('subdir', ''))
        if resp:
            return Response(resp.iter_content(chunk_size=4096), mimetype='text/event-stream', content_type='text/event-stream')
        return jsonify({'success': False, 'message': '远程节点不可用'})

    data = request.get_json()
    tool = data.get('tool')
    subdir = data.get('subdir', '').strip()
    files = data.get('files')

    if not tool:
        return jsonify({'success': False, 'message': '未指定工具'})

    if tool not in ['to_docx', 'to_index', 'to_compare', 'to_pdf', 'to_pageNum', 'to_redhead']:
        return jsonify({'success': False, 'message': f'未知的工具: {tool}'})

    script_path = get_tool_script_path(tool)
    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': f'脚本不存在: {tool}'})

    db = get_db()
    kb_row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = kb_row['local_path']
    target_path = os.path.normpath(os.path.join(local_path, subdir)) if subdir else local_path

    if not target_path.startswith(os.path.normpath(local_path) + os.sep) and target_path != os.path.normpath(local_path):
        return jsonify({'success': False, 'message': '不允许访问的路径'})

    if not os.path.isdir(target_path):
        return jsonify({'success': False, 'message': f'目录不存在: {subdir or "根目录"}'})

    if not files:
        extensions = TOOL_EXTENSIONS.get(tool, ('.docx',))
        files = []
        for f in os.listdir(target_path):
            full = os.path.join(target_path, f)
            if os.path.isfile(full) and f.lower().endswith(extensions):
                files.append(f)

    def generate():
        acquired = _SSE_SEMAPHORE.acquire(blocking=False)
        if not acquired:
            yield f'data: {json.dumps({"type": "end", "success": False, "error": "服务器繁忙，请稍后再试"})}\n\n'
            return
        try:
            # 始终用进程内导入工具模块运行（不再使用子进程）
            # 这样可以完全避免子进程触发单实例锁的问题
            yield from _run_tool_in_process(tool, files, target_path, script_path)

        except Exception as e:
            yield f'data: {json.dumps({"type": "end", "success": False, "error": str(e)})}\n\n'
        finally:
            _SSE_SEMAPHORE.release()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@fb_bp.route('/<fb_id>/convert-doc', methods=['POST'])
@login_required
@require_fb_perm('edit')
def convert_doc_files(filebase_id):
    """扫描文件库中的 .doc 文件并转换为 .docx"""
    db = get_db()
    row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件库不存在'}), 404

    local_path = row['local_path']
    if not local_path or not os.path.exists(local_path):
        return jsonify({'success': False, 'message': '文件库路径不存在'}), 400

    from tools.doc_process import doc_to_docx
    import logging
    logger = logging.getLogger(__name__)

    doc_dirs = set()
    for root, dirs, files in os.walk(local_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.lower().endswith('.doc') and not f.startswith('~$'):
                doc_dirs.add(root)

    if not doc_dirs:
        return jsonify({'success': True, 'message': '没有需要转换的 .doc 文件', 'converted': 0, 'failed': 0})

    total_ok = 0
    total_err = 0
    errors = []

    for workdir in sorted(doc_dirs):
        err_msg = doc_to_docx(workdir)
        if err_msg:
            total_err += 1
            errors.append(err_msg)
            logger.warning(f"doc 转换失败 [{workdir}]: {err_msg}")
        else:
            count = sum(1 for f in os.listdir(workdir)
                        if f.lower().endswith('.doc') and not f.startswith('~$'))
            total_ok += count

    return jsonify({
        'success': True,
        'message': f'转换完成: {total_ok} 成功, {total_err} 个目录有失败',
        'converted': total_ok,
        'failed_dirs': total_err,
        'errors': errors if errors else None
    })
