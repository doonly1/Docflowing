"""
FB 文件库同步 - 后台同步线程

定时扫描启用了同步的文件库，执行增量同步
"""

import logging
import os
import threading
import time
from typing import Dict, Set, Optional
from queue import Queue, Empty

from .sync_converters import can_convert, convert_file
from .sync_state import get_sync_state_manager
from .routes import _get_kb_root

logger = logging.getLogger(__name__)


class SyncWorker:
    """后台同步工作线程"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, interval: int = 60):
        if self._initialized:
            return
        self._initialized = True

        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processing_filebases: Set[str] = set()
        self._trigger_queue: Queue = Queue()
        self._max_concurrent = 3
        self._semaphore = threading.Semaphore(self._max_concurrent)

        self._state_manager = get_sync_state_manager()

    def start(self):
        """启动同步线程"""
        if self._running:
            logger.info("Sync worker already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="SyncWorker")
        self._thread.start()
        logger.info("Sync worker started")

    def stop(self):
        """停止同步线程"""
        if not self._running:
            return

        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Sync worker stopped")

    def _run(self):
        """同步线程主循环"""
        while self._running:
            try:
                self._process_triggered_syncs()
                self._sync_all_enabled_filebases()
            except Exception as e:
                logger.error(f"Sync worker error: {e}", exc_info=True)

            time.sleep(self.interval)

    def _process_triggered_syncs(self):
        """处理手动触发的同步请求"""
        while True:
            try:
                user_id, filebase_id = self._trigger_queue.get_nowait()

                if filebase_id in self._processing_filebases:
                    logger.info(f"Filebase {filebase_id} already being processed, skipping trigger")
                    continue

                thread = threading.Thread(
                    target=self._sync_filebase,
                    args=(user_id, filebase_id),
                    daemon=True
                )
                thread.start()

            except Empty:
                break

    def _sync_all_enabled_filebases(self):
        """扫描所有启用了同步的文件库"""
        try:
            enabled_filebases = self._get_enabled_filebases()

            for filebase_info in enabled_filebases:
                user_id = filebase_info['user_id']
                filebase_id = filebase_info['id']

                if filebase_id not in self._processing_filebases:
                    self._trigger_sync(user_id, filebase_id)

        except Exception as e:
            logger.error(f"Failed to get enabled filebases: {e}")

    def _get_enabled_filebases(self):
        """获取所有启用了同步的文件库"""
        try:
            from fb.database import get_db
            from fb.models import MIGRATIONS

            db = get_db()

            for migration in MIGRATIONS:
                try:
                    db.execute(migration)
                except:
                    pass

            rows = db.execute("""
                SELECT id, owner_id, name, is_synced_to_kb
                FROM filebases
                WHERE is_synced_to_kb = 1
            """).fetchall()

            return [
                {'id': row['id'], 'user_id': row['owner_id'], 'name': row['name']}
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to query enabled filebases: {e}")
            return []

    def _trigger_sync(self, user_id: str, filebase_id: str):
        """触发同步（加入队列）"""
        self._trigger_queue.put((user_id, filebase_id))

    def trigger_sync_now(self, user_id: str, filebase_id: str):
        """立即触发同步（用于手动触发）"""
        self._trigger_sync(user_id, filebase_id)

    def _sync_filebase(self, user_id: str, filebase_id: str):
        """同步单个文件库"""
        self._processing_filebases.add(filebase_id)

        try:
            logger.info(f"Starting sync for filebase {filebase_id} (user: {user_id})")

            filebase_info = self._get_filebase_info(filebase_id)
            if not filebase_info:
                logger.warning(f"Filebase {filebase_id} not found or sync not enabled")
                return

            source_dir = filebase_info['local_path']
            if not source_dir or not os.path.exists(source_dir):
                logger.warning(f"Filebase {filebase_id} has no valid source path")
                return

            current_files = self._scan_filebase(source_dir)

            state = self._state_manager.load_state(user_id, filebase_id)

            self._process_changes(user_id, filebase_id, source_dir, current_files, state)

            self._cleanup_deleted(user_id, filebase_id, source_dir, state)

            state.total_files = len(current_files)
            self._state_manager.save_state(user_id, filebase_id, state)

            logger.info(
                f"Sync completed for filebase {filebase_id}: "
                f"{state.total_files}/{state.syncable_files}/{state.synced_files}"
            )

        except Exception as e:
            logger.error(f"Failed to sync filebase {filebase_id}: {e}", exc_info=True)

        finally:
            self._processing_filebases.discard(filebase_id)

    def _get_filebase_info(self, filebase_id: str) -> Optional[Dict]:
        """获取文件库信息"""
        try:
            from fb.database import get_db

            db = get_db()
            row = db.execute("""
                SELECT id, owner_id, name, local_path, is_synced_to_kb
                FROM filebases
                WHERE id = ? AND is_synced_to_kb = 1
            """, (filebase_id,)).fetchone()

            if row:
                return {
                    'id': row['id'],
                    'user_id': row['owner_id'],
                    'name': row['name'],
                    'local_path': row['local_path']
                }

        except Exception as e:
            logger.error(f"Failed to get filebase info for {filebase_id}: {e}")

        return None

    def _scan_filebase(self, source_dir: str) -> Dict[str, Dict]:
        """扫描文件库，返回所有文件的路径和状态"""
        files = {}

        for root, dirs, filenames in os.walk(source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for filename in filenames:
                if filename.startswith('.') or filename.startswith('~'):
                    continue

                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, source_dir)

                try:
                    stat = os.stat(file_path)
                    files[relative_path] = {
                        'path': file_path,
                        'relative_path': relative_path,
                        'mtime': stat.st_mtime,
                        'size': stat.st_size,
                        'syncable': can_convert(file_path)
                    }
                except Exception as e:
                    logger.warning(f"Failed to stat file {file_path}: {e}")

        return files

    def _process_changes(self, user_id: str, filebase_id: str, source_dir: str,
                        current_files: Dict, state):
        """处理文件变化：新增和修改"""
        files_to_sync = []

        for relative_path, file_info in current_files.items():
            if not file_info['syncable']:
                continue

            existing = state.files.get(relative_path)
            source_mtime = file_info['mtime']

            needs_sync = (
                existing is None or
                existing.source_mtime < source_mtime or
                (existing.status == 'failed' and existing.retry_count < 3)
            )

            if needs_sync:
                files_to_sync.append((relative_path, file_info))

        state.syncable_files = sum(1 for f in current_files.values() if f['syncable'])

        if not files_to_sync:
            return

        logger.info(f"Filebase {filebase_id}: {len(files_to_sync)} files to sync")

        for i, (relative_path, file_info) in enumerate(files_to_sync):
            self._semaphore.acquire()

            thread = threading.Thread(
                target=self._convert_and_sync,
                args=(user_id, filebase_id, relative_path, file_info, state),
                daemon=True
            )
            thread.start()

        for _ in range(self._max_concurrent):
            self._semaphore.acquire()

    def _convert_and_sync(self, user_id: str, filebase_id: str,
                         relative_path: str, file_info: Dict, state):
        """转换并同步单个文件"""
        try:
            source_path = file_info['path']
            source_mtime = file_info['mtime']

            logger.debug(f"Converting: {relative_path}")

            md_content = convert_file(source_path, relative_path, filebase_id)

            if md_content is None:
                self._state_manager.update_file_state(
                    user_id, filebase_id, relative_path,
                    source_mtime, 'failed',
                    error='conversion_failed'
                )
                logger.warning(f"Failed to convert: {relative_path}")
                return

            target_path = self._get_target_path(user_id, filebase_id, relative_path)

            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            target_mtime = os.path.getmtime(target_path)

            self._state_manager.update_file_state(
                user_id, filebase_id, relative_path,
                source_mtime, 'synced',
                target_mtime=target_mtime
            )

            self._update_search_index(user_id, target_path)

            logger.debug(f"Synced: {relative_path}")

        except Exception as e:
            self._state_manager.update_file_state(
                user_id, filebase_id, relative_path,
                file_info['mtime'], 'failed',
                error=str(e)
            )
            logger.error(f"Error syncing {relative_path}: {e}")

        finally:
            self._semaphore.release()

    def _get_target_path(self, user_id: str, filebase_id: str, relative_path: str) -> str:
        """获取 KB 中的目标路径"""
        kb_root = _get_kb_root(user_id)
        target_dir = os.path.join(kb_root, 'imported', filebase_id)
        target_file = os.path.join(target_dir, relative_path)

        if not target_file.lower().endswith('.md'):
            target_file += '.md'

        return target_file

    def _cleanup_deleted(self, user_id: str, filebase_id: str, source_dir: str, state):
        """清理已删除的文件"""
        current_files = self._scan_filebase(source_dir)
        current_paths = set(current_files.keys())

        synced_paths = set(state.files.keys())

        deleted_paths = synced_paths - current_paths

        for relative_path in deleted_paths:
            try:
                target_path = self._get_target_path(user_id, filebase_id, relative_path)

                if os.path.exists(target_path):
                    os.remove(target_path)

                self._state_manager.remove_file(user_id, filebase_id, relative_path)

                self._remove_from_search_index(user_id, target_path)

                logger.debug(f"Deleted synced file: {relative_path}")

            except Exception as e:
                logger.error(f"Failed to delete synced file {relative_path}: {e}")

    def _update_search_index(self, user_id: str, file_path: str):
        """更新 KB 搜索索引"""
        try:
            from .routes import update_search_index, _extract_title_from_md

            kb_root = _get_kb_root(user_id)
            relative_path = os.path.relpath(file_path, kb_root).replace('\\', '/')

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            title = _extract_title_from_md(content) or os.path.splitext(os.path.basename(file_path))[0]

            update_search_index(user_id, relative_path, title, content)

        except Exception as e:
            logger.error(f"Failed to update search index for {file_path}: {e}")

    def _remove_from_search_index(self, user_id: str, file_path: str):
        """从 KB 搜索索引中移除"""
        try:
            from .routes import remove_from_index

            kb_root = _get_kb_root(user_id)
            relative_path = os.path.relpath(file_path, kb_root).replace('\\', '/')

            remove_from_index(user_id, relative_path)

        except Exception as e:
            logger.error(f"Failed to remove from search index: {file_path}: {e}")

    def get_sync_status(self, user_id: str, filebase_id: str) -> Dict:
        """获取同步状态"""
        state = self._state_manager.get_state(user_id, filebase_id)

        return {
            'enabled': self._is_sync_enabled(filebase_id),
            'status': state.get_display_stats(),
            'last_sync': state.last_sync,
            'is_syncing': filebase_id in self._processing_filebases
        }

    def _is_sync_enabled(self, filebase_id: str) -> bool:
        """检查文件库是否启用了同步"""
        try:
            from fb.database import get_db

            db = get_db()
            row = db.execute(
                "SELECT is_synced_to_kb FROM filebases WHERE id = ?",
                (filebase_id,)
            ).fetchone()

            return row and row['is_synced_to_kb'] == 1

        except Exception as e:
            logger.error(f"Failed to check sync status for {filebase_id}: {e}")
            return False

    def cleanup_filebase(self, user_id: str, filebase_id: str):
        """清理文件库的同步数据"""
        try:
            kb_root = _get_kb_root(user_id)
            imported_dir = os.path.join(kb_root, 'imported', filebase_id)

            if os.path.exists(imported_dir):
                import shutil
                shutil.rmtree(imported_dir)

            self._state_manager.clear_all_state(user_id, filebase_id)

            logger.info(f"Cleaned up sync data for filebase {filebase_id}")

        except Exception as e:
            logger.error(f"Failed to cleanup filebase {filebase_id}: {e}")


_sync_worker = None


def get_sync_worker() -> SyncWorker:
    """获取同步工作线程单例"""
    global _sync_worker
    if _sync_worker is None:
        _sync_worker = SyncWorker()
    return _sync_worker
