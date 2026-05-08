"""用户配置持久化 + 配置管理 API"""

import os
import yaml

from flask import Blueprint, request, jsonify
from server.auth import _login_required

settings_bp = Blueprint('settings', __name__)

# ==================== 用户配置路径 / 初始化 ====================

def _get_config_base_dir():
    config_dir = os.path.join(os.path.expanduser('~'), '.config', 'DocProc')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def _get_user_config_dir():
    users_dir = os.path.join(_get_config_base_dir(), 'users')
    os.makedirs(users_dir, exist_ok=True)
    return users_dir

def _get_user_config_path(user_id):
    return os.path.join(_get_user_config_dir(), f'{user_id}.yaml')

def ensure_user_config(user_id):
    config_path = _get_user_config_path(user_id)
    if not os.path.exists(config_path):
        template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     'config', 'config.yaml')
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            if 'last_workdir' in config:
                del config['last_workdir']
            if 'knowledge_base' in config:
                del config['knowledge_base']
            if 'fb' in config:
                del config['fb']
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
        config.pop('knowledge_base', None)
        config.pop('fb', None)
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
        config.pop('knowledge_base', None)
        config.pop('fb', None)
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
        config.pop('knowledge_base', None)
        config.pop('fb', None)
        config['last_workdir'] = workdir
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
