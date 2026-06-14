"""
动态加载用户自建工具。

每个工具是一个独立的 .py 文件，必须导出：
    SCHEMA  — OpenAI function calling schema (dict)
    execute — 执行函数 def execute(args: dict, user_id: str) -> str

文件放在 workspaces/user_tools/ 目录下，打包后可持久化写入。
"""

import importlib.util
import logging
import os
import sys
from typing import Dict, List

logger = logging.getLogger(__name__)

# 运行时目录：由 server.workspace._get_workspace_dir 统一解析
# 开发模式 -> 项目根 /workspaces/user_tools
# 打包模式 -> %APPDATA%/Docflowing/user_tools
from server.workspace import _get_workspace_dir
_RUNTIME_DIR = _get_workspace_dir()
_TOOLS_DIR = os.path.join(_RUNTIME_DIR, 'user_tools')


def load_user_tools() -> tuple:
    """扫描 workspaces/user_tools/ 并返回 (schemas, executors)

    schemas: 可用于 ALL_TOOL_SCHEMAS 的 schema 列表
    executors: {tool_name: execute_function} 映射
    """
    schemas: List[dict] = []
    executors: Dict[str, callable] = {}

    if not os.path.isdir(_TOOLS_DIR):
        os.makedirs(_TOOLS_DIR, exist_ok=True)
        return schemas, executors

    for fname in sorted(os.listdir(_TOOLS_DIR)):
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(_TOOLS_DIR, fname)
        if not os.path.isfile(fpath):
            continue

        module_name = f'user_tools.{fname[:-3]}'
        try:
            spec = importlib.util.spec_from_file_location(module_name, fpath)
            if spec is None or spec.loader is None:
                logger.warning('无法加载用户工具: %s (spec is None)', fname)
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if not hasattr(module, 'SCHEMA') or not hasattr(module, 'execute'):
                logger.warning('用户工具 %s 缺少 SCHEMA 或 execute，跳过', fname)
                continue

            schema = module.SCHEMA
            tool_name = schema.get('function', {}).get('name', '')
            if not tool_name:
                logger.warning('用户工具 %s 的 SCHEMA 缺少 name，跳过', fname)
                continue
            if tool_name in executors:
                logger.warning('用户工具 %s 的工具名 "%s" 已存在，跳过', fname, tool_name)
                continue

            schemas.append(schema)
            executors[tool_name] = module.execute
            logger.info('已加载用户工具: %s (name=%s)', fname, tool_name)
        except Exception as e:
            logger.error('加载用户工具 %s 失败: %s', fname, e, exc_info=True)

    return schemas, executors


def reload_user_tools() -> tuple:
    """重新加载所有用户工具（热更新用）"""
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith('user_tools.'):
            del sys.modules[mod_name]
    return load_user_tools()
