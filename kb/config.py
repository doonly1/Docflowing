"""知识库配置加载器

优先级：
 1. workspaces/config/kb_config.yaml（用户持久化配置）
 2. 代码内置默认值

API Key 使用 p2p node_id 做 XOR 混淆后存储（防 YAML 误同步泄漏）。
同机恶意软件仍可读取两文件解码，桌面单用户模式可接受。"""

import os
import yaml
import base64
from pathlib import Path
from typing import Any, Dict

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
        'provider': 'openai',           # openai / cc_switch
        'api_key': '',
        'base_url': '',
        'model': '',
        'temperature': 0.7,
        'max_tokens': 4096,
        # CC Switch 配置（默认代理端口 15721，用户可在 CC Switch 设置中修改）
        'cc_switch': {
            'proxy_url': 'http://127.0.0.1:15721',
            'route': 'codex',  # claude / codex / gemini
        },
    },
}

# ==================== API Key 处理（node_id XOR 混淆） ====================
#
# API Key 使用 p2p 节点 node_id 的前 16 字节做 XOR 混淆后存储。
# API Key 和 node_id 在同一机器的不同 YAML 文件中（kb_config.yaml vs p2p_node.yaml），
# 意外同步到云端时不会同时泄漏两者，起到防误泄漏的作用。
# 同机恶意软件仍能读取两文件解码，这是桌面单用户应用的可接受安全模型。


def _get_user_config_dir(user_id: str = None) -> str:
    """获取配置目录：workspaces/config/"""
    from server.workspace import _get_workspace_dir
    config_dir = os.path.join(_get_workspace_dir(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def _get_node_key() -> bytes:
    """获取节点密钥（node_id 前 16 字节），用于 API Key 混淆"""
    try:
        from p2p.node import _get_config_path as _p2p_config
        import yaml
        cfg_path = _p2p_config()
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            node_id = cfg.get('node_id', '')
            if node_id:
                return node_id.encode('utf-8')[:16]
    except Exception:
        pass
    return b'docflowing-fallback'  # 极低概率回退（无 p2p 配置时）


def _xor_obfuscate(data: bytes, key: bytes) -> bytes:
    """XOR 混淆/去混淆"""
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))


def _encrypt_api_key(api_key: str, user_id: str = None) -> str:
    """用 node_id 做 XOR 混淆后存储"""
    if not api_key:
        return ''
    key = _get_node_key()
    raw = api_key.encode('utf-8')
    obfuscated = _xor_obfuscate(raw, key)
    return '!xor:' + base64.b64encode(obfuscated).decode()


def _decrypt_api_key(value: str, user_id: str = None) -> str:
    """用 node_id 解码 XOR 混淆"""
    if not value:
        return value
    if not value.startswith('!xor:'):
        return value  # 明文兼容（旧配置）
    key = _get_node_key()
    try:
        obfuscated = base64.b64decode(value[5:])
        return _xor_obfuscate(obfuscated, key).decode('utf-8')
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

    # base_url 安全校验（只允许 http/https 协议）
    base_url = (llm_cfg.get('base_url') or '').strip()
    if base_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            if parsed.scheme not in ('http', 'https'):
                logger.warning("拒绝保存 LLM base_url：协议 '%s' 不受支持", parsed.scheme)
                return False
            if not parsed.hostname:
                logger.warning("拒绝保存 LLM base_url：缺少主机名")
                return False
        except Exception:
            logger.warning("拒绝保存 LLM base_url：解析失败")
            return False

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
