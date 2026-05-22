"""用户配置持久化 + 配置管理 API

配置存储位置：workspaces/config/user_config.yaml（首次启动自动用默认值生成）
"""

import os
import yaml

from flask import Blueprint, request, jsonify, g
from server.auth import login_required

settings_bp = Blueprint('settings', __name__)

# ==================== 默认配置 ====================

_DEFAULT_DOC_CONFIG = {
    'compare': {
        'sentence_similarity_threshold': 0.40,
        'para_similarity_threshold': 0.40,
        'short_para_char_threshold': 50,
    },
    'last_workdir': '',
}

# ==================== 配置路径 / 初始化 ====================

def _get_user_config_dir(user_id=None):
    """获取用户配置目录：workspaces/config/"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_dir = os.path.join(project_root, 'workspaces', 'config')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def _get_user_config_path(user_id=None):
    """获取用户配置文件路径"""
    return os.path.join(_get_user_config_dir(), 'user_config.yaml')

def ensure_user_config(user_id=None):
    """确保配置文件存在（首次用默认值创建）"""
    config_path = _get_user_config_path()
    if not os.path.exists(config_path):
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(_DEFAULT_DOC_CONFIG, f, allow_unicode=True, default_flow_style=False)
        except Exception:
            pass
    return config_path

# ==================== 配置 API ====================

@settings_bp.route('/get_config', methods=['POST'])
@login_required
def api_get_config():
    data = request.get_json() if request.is_json else {}
    config_path = ensure_user_config(g.user_id)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取配置失败: {str(e)}'})

@settings_bp.route('/save_config', methods=['POST'])
@login_required
def api_save_config():
    data = request.get_json()
    config = data.get('config')

    if not config:
        return jsonify({'success': False, 'message': '配置不能为空'})

    config_path = ensure_user_config(g.user_id)
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存配置失败: {str(e)}'})
