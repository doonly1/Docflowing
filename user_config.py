# -*- coding: utf-8 -*-
"""
用户配置管理模块

统一配置读取入口：
  - 优先级：USER_CONFIG_PATH 环境变量（服务端临时配置）→ ./config/config.yaml（模板）
  - 配置由浏览器 localStorage 持久化
"""

import os


def load_user_config():
    """加载用户配置文件（统一入口）。

    优先级：
      1. 环境变量 USER_CONFIG_PATH（服务端临时配置，由 server.py 写入）
      2. ./config/config.yaml（项目模板，只读默认配置）

    Returns:
        dict or None: 配置字典
    """
    import yaml

    # 服务端临时配置优先
    user_config_path = os.environ.get('USER_CONFIG_PATH')
    if user_config_path and os.path.exists(user_config_path):
        try:
            with open(user_config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            pass

    # 项目模板（只读默认配置）
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'config', 'config.yaml')
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None
