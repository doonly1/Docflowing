"""用户配置持久化 + 配置管理 API

配置存储位置：workspaces/config/user_config.yaml（首次启动自动用默认值生成）
"""

import json
import os
import platform

import yaml

from flask import Blueprint, request, jsonify, g
from server.auth import login_required

settings_bp = Blueprint('settings', __name__)

# ==================== 默认配置 ====================

_DEFAULT_DOC_CONFIG = {
    'compare': {
        'sentence_similarity_threshold': 0.40,
        'para_similarity_threshold': 0.40,
        'short_para_char_threshold': 60,
        'semantic_unit_thresholds': [30, 30],  # 仅数字，标点由 to_compare.py 的 PUNCTUATION_LEVELS 按序匹配
    },
    'last_workdir': '',
    '哈喽沃尔得有限公司': {
        '简称': ['哈喽公司', '沃尔得'],
        '代字': '哈沃发',
        '印章位置': './config/哈喽沃尔得有限公司.png',
    },
}

_DEFAULT_APP_SETTINGS = {
    'autostart': False,
    'close_action': 'exit',
    # Word 保活默认关闭（Windows 用户需要时在设置中手动开启；
    # 非 Windows 平台该功能强制禁用，见 desktop_app.setWordKeepAlive）
    'word_keep_alive': False,
}

# ==================== 配置路径 / 初始化 ====================

def _get_user_config_dir(user_id=None):
    """获取用户配置目录：workspaces/config/"""
    from server.workspace import _get_workspace_dir
    config_dir = os.path.join(_get_workspace_dir(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def _get_user_config_path(user_id=None):
    """获取用户配置文件路径"""
    return os.path.join(_get_user_config_dir(), 'user_config.yaml')

def _get_app_settings_path():
    """获取应用设置文件路径"""
    return os.path.join(_get_user_config_dir(), 'app_settings.json')

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

# ==================== 文档配置 API ====================

@settings_bp.route('/get_config', methods=['POST'])
@login_required
def api_get_config():
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

# ==================== 应用设置 API（开机自启/关闭行为）====================

def _load_app_settings():
    """加载应用设置"""
    settings_path = _get_app_settings_path()
    try:
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            settings = dict(_DEFAULT_APP_SETTINGS)
            settings.update(saved)
            return settings
    except Exception:
        pass
    return dict(_DEFAULT_APP_SETTINGS)


def _save_app_settings(settings):
    """保存应用设置"""
    settings_path = _get_app_settings_path()
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _is_autostart_enabled():
    """检查开机自启是否已启用（Windows）"""
    if platform.system() != 'Windows':
        return False
    try:
        import winreg
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, 'Docflowing')
            return True
    except (FileNotFoundError, OSError):
        return False


def _set_autostart(enabled):
    """设置或取消开机自启动（Windows）"""
    if platform.system() != 'Windows':
        return False
    try:
        import winreg
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        if enabled:
            python_exe = _find_pythonw()
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app_desktop.py')
            cmd = f'"{python_exe}" "{script_path}"'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, 'Docflowing', 0, winreg.REG_SZ, cmd)
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, 'Docflowing')
        return True
    except Exception:
        return False


def _find_pythonw():
    """查找 pythonw.exe 路径"""
    import sys
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if os.path.isfile(pythonw):
        return pythonw
    return sys.executable


@settings_bp.route('/get_app_settings', methods=['POST'])
@login_required
def api_get_app_settings():
    settings = _load_app_settings()
    settings['autostart'] = _is_autostart_enabled()
    return jsonify({'success': True, 'settings': settings})


@settings_bp.route('/save_app_settings', methods=['POST'])
@login_required
def api_save_app_settings():
    data = request.get_json()
    new_settings = data.get('settings')

    if not new_settings:
        return jsonify({'success': False, 'message': '设置不能为空'})

    if 'autostart' in new_settings:
        _set_autostart(True if new_settings['autostart'] else False)

    current = _load_app_settings()
    current.update(new_settings)
    ok = _save_app_settings(current)

    if ok:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': '保存设置失败'})
