# -*- coding: utf-8 -*-
"""工具定义共享模块

统一管理 TOOL_SCRIPTS（工具名→脚本路径）和 TOOL_EXTENSIONS（工具名→支持的文件扩展名）。
所有模块统一从此处引用，避免维护时遗漏。
"""

import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _script_path(name: str) -> str:
    return os.path.join(_project_root, 'tools', f'{name}.py')


# ==================== 工具脚本路径映射 ====================

TOOL_SCRIPTS = {
    'to_docx': _script_path('to_docx'),
    'to_index': _script_path('to_index'),
    'to_compare': _script_path('to_compare'),
    'to_pdf': _script_path('to_pdf'),
    'to_pageNum': _script_path('to_pageNum'),
    'to_redhead': _script_path('to_redhead'),
}

# ==================== 工具支持的文件扩展名 ====================

TOOL_EXTENSIONS = {
    'to_docx': ('.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'),
    'to_index': ('.docx', '.doc', '.pdf', '.xlsx'),
    'to_compare': ('.docx', '.doc'),
    'to_pdf': ('.docx', '.doc'),
    'to_pageNum': ('.docx', '.doc'),
    'to_redhead': ('.docx',),
}


def get_tool_extensions(tool: str) -> tuple:
    """获取工具支持的文件扩展名"""
    return TOOL_EXTENSIONS.get(tool, ('.docx',))
