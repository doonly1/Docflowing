import os
import json
import time
import threading

from logging_config import get_logger

logger = get_logger(__name__)


def _get_p2p_data_dir():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(root, 'workspaces', 'data', 'p2p')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _get_trust_path():
    return os.path.join(_get_p2p_data_dir(), 'trusted_nodes.json')


def _get_remote_fb_path():
    return os.path.join(_get_p2p_data_dir(), 'remote_filebases.json')


class TrustStore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._nodes: dict = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        path = _get_trust_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self._nodes = json.load(f)
            except Exception as e:
                logger.warning("Failed to load trust store: %s", e)

    def _save(self):
        path = _get_trust_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self._nodes, f, ensure_ascii=False, indent=2)

    def add_node(self, node_id: str, display_name: str, addr: str, public_key: str):
        with self._lock:
            self._nodes[node_id] = {
                'display_name': display_name,
                'addr': addr,
                'public_key': public_key,
                'discovered_at': time.time()
            }
            self._save()

    def remove_node(self, node_id: str):
        with self._lock:
            self._nodes.pop(node_id, None)
            self._save()

    def get_public_key(self, node_id: str) -> str | None:
        node = self._nodes.get(node_id)
        return node.get('public_key') if node else None

    def get_node_info(self, node_id: str) -> dict | None:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> dict:
        return dict(self._nodes)


class RemoteFilebaseStore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._filebases: dict = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        path = _get_remote_fb_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self._filebases = json.load(f)
            except Exception as e:
                logger.warning("Failed to load remote filebases: %s", e)

    def _save(self):
        path = _get_remote_fb_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self._filebases, f, ensure_ascii=False, indent=2)

    def add(self, fb_id: str, owner_node_id: str, owner_addr: str, name: str, permission: str):
        with self._lock:
            self._filebases[fb_id] = {
                'owner_node_id': owner_node_id,
                'owner_addr': owner_addr,
                'name': name,
                'permission': permission,
                'created_at': time.time()
            }
            self._save()

    def remove(self, fb_id: str):
        with self._lock:
            self._filebases.pop(fb_id, None)
            self._save()

    def get(self, fb_id: str) -> dict | None:
        return self._filebases.get(fb_id)

    def get_all(self) -> dict:
        return dict(self._filebases)

    def list_by_owner(self, node_id: str) -> list:
        return [fb for fb in self._filebases.values() if fb.get('owner_node_id') == node_id]