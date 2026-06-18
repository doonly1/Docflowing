# -*- coding: utf-8 -*-
"""工具定义共享模块

统一管理工具脚本路径和文件扩展名。
所有模块统一从此处引用，避免维护时遗漏。
"""

import os


def _get_project_root():
    """动态解析项目根目录，运行时计算而非模块加载时硬编码。

    - 开发模式：tools/tool_defs.py → tools/ → 项目根
    - PyInstaller frozen 模式：优先使用 sys._MEIPASS（资源所在目录）
    """
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        meipass = getattr(_sys, '_MEIPASS', None)
        if meipass:
            if os.path.isdir(os.path.join(meipass, 'tools')):
                return meipass
        exe_dir = os.path.dirname(_sys.executable)
        if os.path.isdir(os.path.join(exe_dir, 'tools')):
            return exe_dir
    # 开发模式：向上两级
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
