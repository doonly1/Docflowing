"""知识库配置加载器（用户级 + 模板级）

优先级：
  1. ~/.config/DocProc/kb_config.yaml（用户持久化配置）
  2. ./config/kb_config.yaml（项目模板，只读默认配置）

支持加密存储 API Key（Fernet 对称加密），密钥保存在 ~/.config/DocProc/_llm_key。"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict

try:
    from cryptography.fernet import Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

_TEMPLATE_PATH = Path(__file__).parent.parent / 'config' / 'kb_config.yaml'

_cache: Dict[str, Any] = {}
_cache_mtime: float = 0

# ==================== API Key 加密/解密 ====================

_ENCRYPTION_KEY_FILE = '_llm_key'


def _get_config_dir() -> str:
    d = os.path.join(os.path.expanduser('~'), '.config', 'DocProc')
    os.makedirs(d, exist_ok=True)
    return d


def _get_or_create_encryption_key() -> bytes:
    """获取或创建 Fernet 加密密钥"""
    key_path = os.path.join(_get_config_dir(), _ENCRYPTION_KEY_FILE)
    if os.path.exists(key_path):
        with open(key_path, 'rb') as f:
            return f.read().strip()
    if not HAS_FERNET:
        return b''
    key = Fernet.generate_key()
    with open(key_path, 'wb') as f:
        f.write(key)
    return key


def _encrypt_api_key(api_key: str) -> str:
    if not api_key or not HAS_FERNET:
        return api_key
    try:
        key = _get_or_create_encryption_key()
        f = Fernet(key)
        return f.encrypt(api_key.encode()).decode()
    except Exception:
        return api_key


def _decrypt_api_key(value: str) -> str:
    """尝试解密 API Key；若无法解密（明文或解密失败）则原样返回"""
    if not value or not HAS_FERNET:
        return value
    try:
        key = _get_or_create_encryption_key()
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


def _get_user_kb_config_path() -> str:
    return os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'kb_config.yaml')


def _load_raw() -> Dict[str, Any]:
    user_path = _get_user_kb_config_path()
    if os.path.exists(user_path):
        try:
            with open(user_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data:
                    return data
        except Exception:
            pass

    if _TEMPLATE_PATH.exists():
        try:
            with open(_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data:
                    return data
        except Exception:
            pass

    return {}


def get_kb_config() -> Dict[str, Any]:
    global _cache, _cache_mtime
    paths_to_check = [_get_user_kb_config_path(), str(_TEMPLATE_PATH)]
    max_mtime = 0
    for p in paths_to_check:
        try:
            m = os.path.getmtime(p)
            if m > max_mtime:
                max_mtime = m
        except OSError:
            pass
    if max_mtime != _cache_mtime or not _cache:
        _cache = _load_raw()
        _cache_mtime = max_mtime
    return _cache


def get_kb_section() -> Dict[str, Any]:
    cfg = get_kb_config()
    return cfg.get('knowledge_base', {})


def get_llm_config() -> Dict[str, Any]:
    cfg = get_kb_config()
    llm_cfg = cfg.get('llm', {})
    if llm_cfg:
        api_key = llm_cfg.get('api_key', '')
        decrypted = _decrypt_api_key(api_key)
        if decrypted != api_key:
            llm_cfg = dict(llm_cfg)
            llm_cfg['api_key'] = decrypted
    return llm_cfg


# ==================== 配置保存 ====================


def save_llm_config(llm_cfg: dict) -> bool:
    """保存 LLM 配置到用户配置文件，API Key 自动加密存储"""
    user_path = _get_user_kb_config_path()

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
        llm_cfg['api_key'] = _encrypt_api_key(api_key)

    config['llm'] = llm_cfg

    os.makedirs(os.path.dirname(user_path), exist_ok=True)
    try:
        with open(user_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        global _cache, _cache_mtime
        _cache = {}
        _cache_mtime = 0
        return True
    except Exception:
        return False
