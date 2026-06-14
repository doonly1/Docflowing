# -*- coding: utf-8 -*-
"""用户配置加载器

读取配置文件：workspaces/config/user_config.yaml
文件不存在时返回 None，调用方自行使用默认值。"""

import os


def _get_workspace_dir():
    """返回运行时数据目录（与 server.workspace._get_runtime_dir 逻辑一致）。
    
    优先级：
    1. 环境变量 DOCFLOWING_DATA_DIR / DOCFLOWING_RUNTIME_DIR
    2. 项目根目录 /workspaces
    """
    env_dir = (os.environ.get('DOCFLOWING_DATA_DIR')
               or os.environ.get('DOCFLOWING_RUNTIME_DIR'))
    if env_dir:
        return os.path.abspath(env_dir)

    # 本文件在 tools/load_config.py，项目根在 ../../ 两级上
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, 'workspaces')


def load_user_config():
    """加载配置文件。

    Returns:
        dict or None: 配置字典
    """
    import yaml

    config_path = os.path.join(_get_workspace_dir(), 'config', 'user_config.yaml')

    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None
