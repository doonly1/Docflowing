# -*- coding: utf-8 -*-
"""用户配置加载器

优先级：
  1. USER_CONFIG_PATH 环境变量（调用方临时配置）
  2. workspaces/data/config.yaml（用户配置，可读写）
  3. ./config/config.yaml（项目模板，只读默认配置）"""

import os
import shutil


def _get_data_dir():
    """获取全局数据存储目录：workspaces/data/"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'workspaces', 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _migrate_old_config():
    """从旧路径 ~/.config/DocProc/config.yaml 迁移配置到新路径"""
    old_path = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'config.yaml')
    new_path = os.path.join(_get_data_dir(), 'config.yaml')

    if os.path.exists(old_path) and not os.path.exists(new_path):
        try:
            shutil.copy2(old_path, new_path)
        except Exception:
            pass


def load_user_config():
    """加载用户配置文件（统一入口）。

    优先级：
      1. 环境变量 USER_CONFIG_PATH（调用方写入的临时配置文件路径）
      2. workspaces/data/config.yaml（用户持久化配置）
      3. ./config/config.yaml（项目模板，只读默认配置）

    Returns:
        dict or None: 配置字典
    """
    import yaml

    # 调用方临时配置优先
    user_config_path = os.environ.get('USER_CONFIG_PATH')
    if user_config_path and os.path.exists(user_config_path):
        try:
            with open(user_config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            pass

    # 迁移旧配置
    _migrate_old_config()

    # 用户持久化配置
    home_config = os.path.join(_get_data_dir(), 'config.yaml')
    if os.path.exists(home_config):
        try:
            with open(home_config, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            pass

    # 项目模板（只读默认配置）
    template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'config', 'config.yaml')
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None
