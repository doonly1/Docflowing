# -*- coding: utf-8 -*-
"""工具定义共享模块

统一管理工具脚本路径和文件扩展名。
所有模块统一从此处引用，避免维护时遗漏。
"""

import os


def _get_project_root():
    """动态解析项目根目录，运行时计算而非模块加载时固定。
    
    在打包场景下（PyInstaller），__file__ 行为变化，
    但此函数在调用时才计算，确保路径始终正确。
    """
    # tools/tool_defs.py → 父目录 tools/ → 父目录 项目根
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ==================== 工具名称列表 ====================

TOOL_NAMES = ['to_docx', 'to_index', 'to_compare', 'to_pdf', 'to_pageNum', 'to_redhead']


# ==================== 脚本路径（函数式，避免模块级硬编码） ====================

def get_tool_script_path(name: str) -> str:
    """获取工具脚本的完整路径，运行时动态解析"""
    return os.path.join(_get_project_root(), 'tools', f'{name}.py')


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
