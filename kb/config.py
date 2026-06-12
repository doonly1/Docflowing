"""知识库配置加载器

优先级：
 1. workspaces/config/kb_config.yaml（用户持久化配置）
 2. 代码内置默认值

支持加密存储 API Key（Fernet 对称加密），密钥保存在 workspaces/config/_llm_key。"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict

try:
    from cryptography.fernet import Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

# 缓存
_cache: Dict[str, Any] = {}
_cache_mtime: Dict[str, float] = {}

# ==================== 默认配置 ====================

_DEFAULT_KB_CONFIG = {
    'knowledge_base': {
        'default_name': 'Knowledge Base',
        'default_icon': '\U0001f4da',
        'default_permissions': 'user',
        'search': {
            'max_chars': 4000,
            'max_sources': 5,
        },
        'memory': {
            'enabled': True,
            'memory_limit': 2200,
            'user_limit': 1375,
        },
        'session_store': {
            'enabled': True,
            'retention_days': 90,
            'search_limit': 20,
        },
        'skills': {
            'enabled': True,
            'stale_days': 30,
            'archive_days': 90,
        },
        'curator': {
            'enabled': True,
            'interval_hours': 168,
            'min_idle_hours': 2,
        },
    },
    'llm': {
        'enabled': False,
        'api_key': '',
        'base_url': '',
        'model': '',
        'temperature': 0.7,
        'max_tokens': 4096,
    },
}

# ==================== API Key 加密/解密 ====================

_ENCRYPTION_KEY_FILE = '_llm_key'


def _get_user_config_dir(user_id: str = None) -> str:
    """获取配置目录：workspaces/config/"""
    from server.workspace import _get_workspace_dir
    config_dir = os.path.join(_get_workspace_dir(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def _get_or_create_encryption_key(user_id: str = None) -> bytes:
    """获取或创建 Fernet 加密密钥（按用户存储）"""
    if user_id is None:
        user_id = 'anonymous'
    key_path = os.path.join(_get_user_config_dir(user_id), _ENCRYPTION_KEY_FILE)
    if os.path.exists(key_path):
        with open(key_path, 'rb') as f:
            return f.read().strip()
    if not HAS_FERNET:
        return b''
    key = Fernet.generate_key()
    with open(key_path, 'wb') as f:
        f.write(key)
    return key


def _encrypt_api_key(api_key: str, user_id: str = None) -> str:
    if not api_key or not HAS_FERNET:
        return api_key
    try:
        key = _get_or_create_encryption_key(user_id)
        f = Fernet(key)
        return f.encrypt(api_key.encode()).decode()
    except Exception:
        return api_key


def _decrypt_api_key(value: str, user_id: str = None) -> str:
    """尝试解密 API Key；若无法解密（明文或解密失败）则原样返回"""
    if not value or not HAS_FERNET:
        return value
    try:
        key = _get_or_create_encryption_key(user_id)
        f = Fernet(key)
        return f.decrypt(value.encode()).decode()
    except Exception:
        return value


def _mask_api_key(api_key: str) -> str:
    """脱敏 API Key，仅保留首尾各 4 字符"""
    if not api_key or len(api_key) <= 8:
        return api_key[:4] + '****' if api_key else ''
    return api_key[:4] + '*' * (len(api_key) - 8) + api_key[-4:]


# ==================== 配置读取 ====================


def _get_user_kb_config_path(user_id: str = None) -> str:
    """获取用户 KB 配置文件路径"""
    return os.path.join(_get_user_config_dir(user_id), 'kb_config.yaml')


def _load_raw(user_id: str = None) -> Dict[str, Any]:
    """加载配置：优先用户文件，回退默认值"""
    user_path = _get_user_kb_config_path(user_id)
    if os.path.exists(user_path):
        try:
            with open(user_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data:
                    return data
        except Exception:
            pass

    return dict(_DEFAULT_KB_CONFIG)


def get_kb_config(user_id: str = None) -> Dict[str, Any]:
    if user_id is None:
        return dict(_DEFAULT_KB_CONFIG)
    cache_key = user_id
    try:
        m = os.path.getmtime(_get_user_kb_config_path(user_id))
    except OSError:
        m = 0
    if cache_key in _cache_mtime:
        if m == _cache_mtime.get(cache_key, 0) and cache_key in _cache:
            return _cache[cache_key]
    _cache[cache_key] = _load_raw(user_id)
    _cache_mtime[cache_key] = m
    return _cache[cache_key]


def get_kb_section(user_id: str = None) -> Dict[str, Any]:
    cfg = get_kb_config(user_id)
    return cfg.get('knowledge_base', {})


def get_llm_config(user_id: str = None) -> Dict[str, Any]:
    cfg = get_kb_config(user_id)
    llm_cfg = cfg.get('llm', {})
    if llm_cfg:
        api_key = llm_cfg.get('api_key', '')
        decrypted = _decrypt_api_key(api_key, user_id)
        if decrypted != api_key:
            llm_cfg = dict(llm_cfg)
            llm_cfg['api_key'] = decrypted
    return llm_cfg


# ==================== 配置保存 ====================


def save_llm_config(llm_cfg: dict, user_id: str = None) -> bool:
    """保存 LLM 配置到用户配置文件，API Key 自动加密存储"""
    user_path = _get_user_kb_config_path(user_id)

    # 读取已有配置
    config = {}
    if os.path.exists(user_path):
        try:
            with open(user_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    # 加密 api_key
    api_key = llm_cfg.get('api_key', '')
    if api_key:
        llm_cfg['api_key'] = _encrypt_api_key(api_key, user_id)

    config['llm'] = llm_cfg

    os.makedirs(os.path.dirname(user_path), exist_ok=True)
    try:
        with open(user_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        # 清除缓存
        cache_key = user_id or 'anonymous'
        _cache.pop(cache_key, None)
        _cache_mtime.pop(cache_key, None)
        return True
    except Exception:
        return False
