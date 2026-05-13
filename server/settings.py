"""用户配置持久化 + 配置管理 API

配置存储位置：workspaces/{user_id}/config/user_config.yaml
迁移：从旧路径 ~/.config/DocProc/users/{user_id}.yaml 自动迁移
"""

import os
import yaml
import shutil

from flask import Blueprint, request, jsonify
from server.auth import _login_required
from server.workspace import _get_workspace_dir

settings_bp = Blueprint('settings', __name__)

# ==================== 用户配置路径 / 初始化 ====================

def _get_user_config_dir(user_id):
    """获取用户配置目录：workspaces/{user_id}/config/"""
    config_dir = os.path.join(_get_workspace_dir(user_id), 'config')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def _get_user_config_path(user_id):
    """获取用户配置文件路径"""
    return os.path.join(_get_user_config_dir(user_id), 'user_config.yaml')

def _get_project_config_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')

def _migrate_old_config(user_id):
    """从旧路径 ~/.config/DocProc/users/ 迁移配置到新路径"""
    old_dir = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'users')
    old_path = os.path.join(old_dir, f'{user_id}.yaml')
    new_path = _get_user_config_path(user_id)

    if os.path.exists(old_path) and not os.path.exists(new_path):
        try:
            shutil.copy2(old_path, new_path)
        except Exception:
            pass

def ensure_user_config(user_id):
    """确保用户配置文件存在（从模板创建或迁移旧配置）"""
    _migrate_old_config(user_id)

    config_path = _get_user_config_path(user_id)
    if not os.path.exists(config_path):
        template_path = os.path.join(_get_project_config_dir(), 'config.yaml')
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            if 'last_workdir' in config:
                del config['last_workdir']
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        except Exception:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump({}, f, allow_unicode=True, default_flow_style=False)

    return config_path

# ==================== 配置 API ====================

@settings_bp.route('/get_config', methods=['POST'])
@_login_required
def api_get_config(_user_id=None):
    data = request.get_json() if request.is_json else {}
    config_path = ensure_user_config(_user_id)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取配置失败: {str(e)}'})

@settings_bp.route('/save_config', methods=['POST'])
@_login_required
def api_save_config(_user_id=None):
    data = request.get_json()
    config = data.get('config')

    if not config:
        return jsonify({'success': False, 'message': '配置不能为空'})

    config_path = ensure_user_config(_user_id)
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存配置失败: {str(e)}'})

@settings_bp.route('/save_workdir', methods=['POST'])
@_login_required
def api_save_workdir(_user_id=None):
    data = request.get_json()
    workdir = data.get('workdir')

    config_path = ensure_user_config(_user_id)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        config['last_workdir'] = workdir
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
