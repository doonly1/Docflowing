# -*- coding: utf-8 -*-
"""用户配置加载器

读取配置文件：workspaces/config/user_config.yaml

文件不存在时返回 None，调用方自行使用默认值。"""

import os


def load_user_config():
    """加载配置文件。

    Returns:
        dict or None: 配置字典
    """
    import yaml

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'workspaces', 'config', 'user_config.yaml'
    )

    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None
