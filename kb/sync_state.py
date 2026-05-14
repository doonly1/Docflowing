"""
FB 文件库同步 - 同步状态管理器

管理同步状态文件 _sync_state.json
"""

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class FileSyncState:
    """单个文件的同步状态"""
    source: str
    source_mtime: float
    target_mtime: Optional[float] = None
    status: str = "pending"
    error: Optional[str] = None
    retry_count: int = 0
    last_retry: Optional[float] = None


@dataclass
class SyncState:
    """文件库同步状态"""
    filebase_id: str
    last_sync: Optional[float] = None
    total_files: int = 0
    syncable_files: int = 0
    synced_files: int = 0
    files: Dict[str, FileSyncState] = field(default_factory=dict)
    failed_files: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为字典用于 JSON 序列化"""
        return {
            "filebase_id": self.filebase_id,
            "last_sync": self.last_sync,
            "total_files": self.total_files,
            "syncable_files": self.syncable_files,
            "synced_files": self.synced_files,
            "files": {
                path: {
                    "source": state.source,
                    "source_mtime": state.source_mtime,
                    "target_mtime": state.target_mtime,
                    "status": state.status,
                    "error": state.error,
                    "retry_count": state.retry_count,
                    "last_retry": state.last_retry
                }
                for path, state in self.files.items()
            },
            "failed_files": self.failed_files
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SyncState':
        """从字典加载"""
        state = cls(
            filebase_id=data.get("filebase_id", ""),
            last_sync=data.get("last_sync"),
            total_files=data.get("total_files", 0),
            syncable_files=data.get("syncable_files", 0),
            synced_files=data.get("synced_files", 0)
        )

        files_data = data.get("files", {})
        for path, file_data in files_data.items():
            state.files[path] = FileSyncState(
                source=file_data.get("source", path),
                source_mtime=file_data.get("source_mtime", 0),
                target_mtime=file_data.get("target_mtime"),
                status=file_data.get("status", "pending"),
                error=file_data.get("error"),
                retry_count=file_data.get("retry_count", 0),
                last_retry=file_data.get("last_retry")
            )

        state.failed_files = data.get("failed_files", [])

        return state

    def update_file_state(self, file_path: str, state: FileSyncState):
        """更新单个文件的状态"""
        self.files[file_path] = state
        self._recalculate_stats()

    def remove_file(self, file_path: str):
        """移除文件状态"""
        if file_path in self.files:
            del self.files[file_path]
            self.failed_files = [f for f in self.failed_files if f.get("path") != file_path]
            self._recalculate_stats()

    def _recalculate_stats(self):
        """重新计算统计信息"""
        self.synced_files = sum(1 for f in self.files.values() if f.status == "synced")

    def get_display_stats(self) -> Dict[str, int]:
        """获取显示用的统计数据"""
        return {
            "total_files": self.total_files,
            "syncable_files": self.syncable_files,
            "synced_files": self.synced_files
        }


class SyncStateManager:
    """同步状态管理器"""

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
        self._cache: Dict[str, SyncState] = {}
        self._file_locks: Dict[str, threading.Lock] = {}
        self._state_dir_cache: Dict[str, str] = {}

    def _get_state_lock(self, filebase_id: str) -> threading.Lock:
        """获取文件库的锁"""
        if filebase_id not in self._file_locks:
            with self._lock:
                if filebase_id not in self._file_locks:
                    self._file_locks[filebase_id] = threading.Lock()
        return self._file_locks[filebase_id]

    def _create_temp_file(self, target_path: str):
        """创建临时文件用于原子写入"""
        state_dir = os.path.dirname(target_path)
        os.makedirs(state_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix='.tmp', prefix='.sync_')
        return fd, tmp_path

    def _get_state_file_path(self, user_id: str, filebase_id: str) -> str:
        """获取状态文件路径（不创建目录）"""
        if filebase_id not in self._state_dir_cache:
            from server.workspace import _get_workspace_dir
            kb_dir = os.path.join(_get_workspace_dir(user_id), 'kb', 'imported', filebase_id)
            self._state_dir_cache[filebase_id] = kb_dir

        state_dir = self._state_dir_cache[filebase_id]
        return os.path.join(state_dir, '_sync_state.json')

    def load_state(self, user_id: str, filebase_id: str) -> SyncState:
        """加载同步状态"""
        cache_key = f"{user_id}:{filebase_id}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        state_file = self._get_state_file_path(user_id, filebase_id)

        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                state = SyncState.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load sync state from {state_file}: {e}")
                state = SyncState(filebase_id=filebase_id)
        else:
            state = SyncState(filebase_id=filebase_id)

        self._cache[cache_key] = state
        return state

    def save_state(self, user_id: str, filebase_id: str, state: SyncState):
        """保存同步状态"""
        cache_key = f"{user_id}:{filebase_id}"
        state.last_sync = time.time()

        try:
            state_file = self._get_state_file_path(user_id, filebase_id)
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            fd, tmp_path = self._create_temp_file(state_file)

            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, state_file)
            self._cache[cache_key] = state

        except Exception as e:
            logger.error(f"Failed to save sync state for {filebase_id}: {e}")

    def update_file_state(self, user_id: str, filebase_id: str, file_path: str,
                         source_mtime: float, status: str,
                         error: Optional[str] = None, target_mtime: Optional[float] = None):
        """更新单个文件的同步状态"""
        state = self.load_state(user_id, filebase_id)

        file_state = FileSyncState(
            source=file_path,
            source_mtime=source_mtime,
            target_mtime=target_mtime,
            status=status,
            error=error
        )

        if error:
            file_state.retry_count = state.files.get(file_path, FileSyncState(source=file_path, source_mtime=source_mtime)).retry_count + 1
            file_state.last_retry = time.time()

            if file_state.retry_count <= 3:
                state.failed_files.append({
                    "path": file_path,
                    "reason": error,
                    "retry_count": file_state.retry_count,
                    "last_retry": file_state.last_retry
                })

        state.update_file_state(file_path, file_state)
        self.save_state(user_id, filebase_id, state)

    def remove_file(self, user_id: str, filebase_id: str, file_path: str):
        """移除文件的同步状态"""
        state = self.load_state(user_id, filebase_id)
        state.remove_file(file_path)
        self.save_state(user_id, filebase_id, state)

    def get_state(self, user_id: str, filebase_id: str) -> SyncState:
        """获取同步状态"""
        return self.load_state(user_id, filebase_id)

    def invalidate_cache(self, user_id: str, filebase_id: str):
        """使缓存失效"""
        cache_key = f"{user_id}:{filebase_id}"
        if cache_key in self._cache:
            del self._cache[cache_key]

    def clear_all_state(self, user_id: str, filebase_id: str):
        """清除所有状态（包括状态文件和缓存）"""
        cache_key = f"{user_id}:{filebase_id}"

        if cache_key in self._cache:
            del self._cache[cache_key]

        state_file = self._get_state_file_path(user_id, filebase_id)
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except Exception as e:
                logger.error(f"Failed to remove state file {state_file}: {e}")


_sync_state_manager = None


def get_sync_state_manager() -> SyncStateManager:
    """获取同步状态管理器单例"""
    global _sync_state_manager
    if _sync_state_manager is None:
        _sync_state_manager = SyncStateManager()
    return _sync_state_manager
