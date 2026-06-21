"""工具进程内执行器 —— 替代 subprocess，避免打包后单实例锁"""

import os
import sys
import json
import io
import logging
import importlib
from contextlib import redirect_stdout


def run_tool_in_process(tool, files, target_path, script_path):
    """导入工具模块并在当前进程中运行，产出 SSE event 行

    参数
    ----
    tool         : str  工具名（如 'to_docx'）
    files        : list 文件名列表（不含路径）
    target_path  : str  工作目录（files 中每个文件在此目录下）
    script_path  : str  工具 .py 脚本的绝对路径

    生成
    ----
    'data: {json}\n\n'  格式的 SSE 事件行
    """
    tools_dir = os.path.dirname(script_path)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s'
    ))

    try:
        mod = importlib.import_module(tool)
    except Exception as e:
        yield f'data: {json.dumps({"type": "end", "success": False, "error": f"导入工具模块失败: {e}"})}\n\n'
        return

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    old_level = root_logger.level
    root_logger.setLevel(logging.INFO)

    file_paths = [os.path.join(target_path, f) for f in files] if files else [target_path]

    _TOOL_DISPATCH = {
        'to_docx': lambda: [
            mod.generate_docx(p) if os.path.isfile(p) else mod.convert_folder(p)
            for p in file_paths
        ],
        'to_compare': lambda: (
            mod.main(os.path.dirname(file_paths[0]), file_paths[0], file_paths[1])
            if len(file_paths) >= 2 else mod.main(file_paths[0])
        ),
        'to_pdf': lambda: [
            mod.convert_single_to_pdf(p) if os.path.isfile(p) else mod.convert_to_pdf(p)
            for p in file_paths
        ],
        'to_pageNum': lambda: [
            mod.add_page_number_single(p) if os.path.isfile(p) else mod.add_page_numbers(p)
            for p in file_paths
        ],
        'to_redhead': lambda: [
            mod.add_seal_single(p) if os.path.isfile(p) else mod.add_seal(p)
            for p in file_paths
        ],
        'to_index': lambda: mod.build_index(file_paths[0] if file_paths else '.'),
    }

    stdout_buf = io.StringIO()
    try:
        with redirect_stdout(stdout_buf):
            runner = _TOOL_DISPATCH.get(tool)
            if runner:
                runner()
            else:
                raise ValueError(f'未知工具: {tool}')
    except Exception as e:
        stdout_text = stdout_buf.getvalue()
        log_text = log_buf.getvalue()
        all_output = stdout_text + log_text
        for line in all_output.splitlines():
            yield f'data: {json.dumps({"type": "output", "content": line})}\n\n'
        yield f'data: {json.dumps({"type": "end", "success": False, "error": str(e)})}\n\n'
        return
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(old_level)
        handler.close()

    stdout_text = stdout_buf.getvalue()
    log_text = log_buf.getvalue()
    for line in (stdout_text + log_text).splitlines():
        yield f'data: {json.dumps({"type": "output", "content": line})}\n\n'
    yield f'data: {json.dumps({"type": "end", "success": True})}\n\n'