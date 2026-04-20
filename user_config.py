# -*- coding: utf-8 -*-
"""
用户配置管理模块

统一配置读写入口：
  - 唯一真实配置：~/.config/doc_tool/config.yaml
  - 模板：./config/config.yaml（仅首次初始化时复制）
  - 服务端临时配置：通过 USER_CONFIG_PATH 环境变量传递
"""

import os


def get_user_config_path():
    """获取用户配置文件路径，如不存在则从项目模板初始化。

    统一使用 ~/.config/doc_tool/config.yaml 作为用户配置，
    ./config/config.yaml 仅作为首次初始化的模板。

    Returns:
        str: 用户配置文件的绝对路径
    """
    import shutil

    user_config_dir = os.path.join(os.path.expanduser('~'), '.config', 'doc_tool')
    user_config_path = os.path.join(user_config_dir, 'config.yaml')

    if not os.path.exists(user_config_path):
        # 从项目模板复制
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'config', 'config.yaml')
        if os.path.exists(template_path):
            os.makedirs(user_config_dir, exist_ok=True)
            shutil.copy2(template_path, user_config_path)
        else:
            # 模板也不存在，创建空配置
            os.makedirs(user_config_dir, exist_ok=True)
            with open(user_config_path, 'w', encoding='utf-8') as f:
                f.write('compare:\n  sentence_similarity_threshold: 0.40\n  para_similarity_threshold: 0.40\n\nlast_workdir: ""\n')

    return user_config_path


def load_user_config():
    """加载用户配置文件（统一入口）。

    优先级：
      1. 环境变量 USER_CONFIG_PATH（服务端临时配置）
      2. ~/.config/doc_tool/config.yaml（用户持久配置）

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

    # 用户持久配置
    config_path = get_user_config_path()
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def save_user_config(config):
    """保存配置到用户配置文件。

    Args:
        config: 配置字典
    """
    import yaml

    config_path = get_user_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
