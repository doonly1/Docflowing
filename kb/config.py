"""知识库配置加载器（用户级 + 模板级）

优先级：
  1. ~/.config/DocProc/kb_config.yaml（用户持久化配置）
  2. ./config/kb_config.yaml（项目模板，只读默认配置）"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict

_TEMPLATE_PATH = Path(__file__).parent.parent / 'config' / 'kb_config.yaml'

_cache: Dict[str, Any] = {}
_cache_mtime: float = 0


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
    return cfg.get('llm', {})
