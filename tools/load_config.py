# -*- coding: utf-8 -*-
"""用户配置加载器

读取配置文件：workspaces/config/user_config.yaml
文件不存在时返回 None，调用方自行使用默认值。"""

import os


def _get_workspace_dir():
    """返回运行时数据目录（与 server.workspace._get_runtime_dir 逻辑一致）。

    优先级：
    1. 环境变量 DOCFLOWING_DATA_DIR / DOCFLOWING_RUNTIME_DIR
    2. %APPDATA%/Docflowing（开发模式与打包模式一致）
    """
    env_dir = (os.environ.get('DOCFLOWING_DATA_DIR')
               or os.environ.get('DOCFLOWING_RUNTIME_DIR'))
    if env_dir:
        return os.path.abspath(env_dir)

    if os.name == 'nt':
        appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
        return os.path.join(appdata, 'Docflowing')
    return os.path.join(os.path.expanduser('~'), '.docflowing')


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
