# -*- coding: utf-8 -*-
"""用户配置加载器

通过环境变量 USER_ID 读取持久化配置：workspaces/{user_id}/config/user_config.yaml

不设置 USER_ID 或文件不存在时返回 None，调用方自行使用默认值。"""

import os


def load_user_config():
    """加载用户配置文件。

    Returns:
        dict or None: 配置字典
    """
    import yaml

    user_id = os.environ.get('USER_ID')
    if not user_id:
        return None

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'workspaces', user_id, 'config', 'user_config.yaml'
    )

    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None
