"""
FB 文件库同步 - 同步状态管理器

管理同步状态，存储于数据库 filebase_sync_states 表中
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
    """同步状态管理器（数据库存储）"""

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
        self._cache_lock = threading.Lock()

    def _cache_key(self, user_id: str, filebase_id: str) -> str:
        return f"{user_id}:{filebase_id}"

    def _get_db(self):
        from fb.database import get_db
        return get_db()

    def load_state(self, user_id: str, filebase_id: str) -> SyncState:
        """从数据库加载同步状态"""
        cache_key = self._cache_key(user_id, filebase_id)

        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            db = self._get_db()
            row = db.execute(
                "SELECT state_json FROM filebase_sync_states WHERE filebase_id = ? AND user_id = ?",
                (filebase_id, user_id)
            ).fetchone()

            if row:
                data = json.loads(row['state_json'])
                state = SyncState.from_dict(data)
            else:
                state = SyncState(filebase_id=filebase_id)

            with self._cache_lock:
                self._cache[cache_key] = state
            return state

        except Exception as e:
            logger.warning(f"Failed to load sync state for {filebase_id}: {e}")
            state = SyncState(filebase_id=filebase_id)
            with self._cache_lock:
                self._cache[cache_key] = state
            return state

    def save_state(self, user_id: str, filebase_id: str, state: SyncState):
        """保存同步状态到数据库"""
        cache_key = self._cache_key(user_id, filebase_id)
        state.last_sync = time.time()

        try:
            db = self._get_db()
            state_json = json.dumps(state.to_dict(), ensure_ascii=False)
            db.execute(
                """
                INSERT INTO filebase_sync_states (filebase_id, user_id, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(filebase_id, user_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (filebase_id, user_id, state_json, state.last_sync)
            )
            db.commit()

            with self._cache_lock:
                self._cache[cache_key] = state

        except Exception as e:
            logger.error(f"Failed to save sync state for {filebase_id}: {e}")

    def update_file_state(self, user_id: str, filebase_id: str, file_path: str,
                         source_mtime: float, status: str,
                         error: Optional[str] = None, target_mtime: Optional[float] = None):
        """更新单个文件的同步状态（立即持久化）"""
        state = self.load_state(user_id, filebase_id)
        self._apply_file_state(state, file_path, source_mtime, status, error, target_mtime)
        self.save_state(user_id, filebase_id, state)

    def batch_update_file_states(self, user_id: str, filebase_id: str,
                                 updates: list) -> SyncState:
        """批量更新文件同步状态，最后只持久化一次

        updates: [(file_path, source_mtime, status, error, target_mtime), ...]
        """
        state = self.load_state(user_id, filebase_id)
        for file_path, source_mtime, status, error, target_mtime in updates:
            self._apply_file_state(state, file_path, source_mtime, status, error, target_mtime)
        self.save_state(user_id, filebase_id, state)
        return state

    def _apply_file_state(self, state: SyncState, file_path: str,
                          source_mtime: float, status: str,
                          error: Optional[str] = None,
                          target_mtime: Optional[float] = None):
        """在内存中应用一个文件的状态更新（不持久化）"""
        existing_retry = 0
        if file_path in state.files:
            existing_retry = state.files[file_path].retry_count

        file_state = FileSyncState(
            source=file_path,
            source_mtime=source_mtime,
            target_mtime=target_mtime,
            status=status,
            error=error
        )

        if error:
            file_state.retry_count = existing_retry + 1
            file_state.last_retry = time.time()

            if file_state.retry_count <= 3:
                state.failed_files = [
                    f for f in state.failed_files if f.get("path") != file_path
                ]
                state.failed_files.append({
                    "path": file_path,
                    "reason": error,
                    "retry_count": file_state.retry_count,
                    "last_retry": file_state.last_retry
                })

        state.update_file_state(file_path, file_state)

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
        cache_key = self._cache_key(user_id, filebase_id)
        with self._cache_lock:
            if cache_key in self._cache:
                del self._cache[cache_key]

    def clear_all_state(self, user_id: str, filebase_id: str):
        """清除所有状态（包括数据库记录和缓存）"""
        cache_key = self._cache_key(user_id, filebase_id)

        with self._cache_lock:
            if cache_key in self._cache:
                del self._cache[cache_key]

        try:
            db = self._get_db()
            db.execute(
                "DELETE FROM filebase_sync_states WHERE filebase_id = ? AND user_id = ?",
                (filebase_id, user_id)
            )
            db.commit()
        except Exception as e:
            logger.error(f"Failed to clear sync state for {filebase_id}: {e}")


_sync_state_manager = None


def get_sync_state_manager() -> SyncStateManager:
    """获取同步状态管理器单例"""
    global _sync_state_manager
    if _sync_state_manager is None:
        _sync_state_manager = SyncStateManager()
    return _sync_state_manager
