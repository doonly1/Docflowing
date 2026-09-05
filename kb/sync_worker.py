"""
FB 文件库同步 - 后台同步线程（优化版）

定时扫描启用了同步的文件库，执行增量同步
优化项：
- 消除重复目录扫描
- 批量持久化同步状态
- 一次性迁移标记
- md/txt 轻量文件内联处理
- 减少主循环阻塞等待
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Dict, Optional, Set
from queue import Empty, Queue

from .sync_converters import can_convert, convert_file
from .sync_state import get_sync_state_manager

logger = logging.getLogger(__name__)

# 无需线程开销的轻量文件扩展名（转换就是读文件，几乎无耗时）
_LIGHT_EXTENSIONS = {'.md', '.txt'}


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
        self._trigger_event = threading.Event()
        self._max_concurrent = 3
        self._semaphore = threading.Semaphore(self._max_concurrent)

        self._state_manager = get_sync_state_manager()
        # 标记已执行过一次迁移的文件库，避免每轮主循环重复检查
        self._migrated_filebases: Set[str] = set()

        # 定时轮询：检测 OS 级文件变动（目录删除、新增文件等）
        self._last_poll_time = 0.0
        self._poll_interval = interval  # 秒，默认 60

        # 文件库扫描统计缓存（供 get_sync_status 直接读取，避免 os.walk）
        self._filebase_stats: Dict[str, Dict] = {}
        # 轮询运行标志，防止 _sync_all_enabled_filebases 重入
        self._poll_running = False

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
        """同步线程主循环 - 事件驱动 + 定时轮询"""
        self._run_migration_once()
        while self._running:
            self._process_triggered_syncs()

            # 定时轮询：检测 OS 级文件变动（目录删除、新增文件等）
            # 加 _poll_running 防重入 —— 若扫描耗时超过 poll_interval，
            # 下一轮不再触发，避免多个全量扫描并发，也避免与触发同步冲突
            now = time.time()
            if now - self._last_poll_time >= self._poll_interval and not self._poll_running:
                self._last_poll_time = now
                self._poll_running = True
                try:
                    self._sync_all_enabled_filebases()
                finally:
                    self._poll_running = False

            self._trigger_event.wait(timeout=1)
            self._trigger_event.clear()

    def _process_triggered_syncs(self):
        """处理手动触发的同步请求"""
        skipped = []  # 正在处理中的项，处理完后放回队列
        while True:
            try:
                user_id, filebase_id = self._trigger_queue.get_nowait()

                if filebase_id in self._processing_filebases:
                    logger.info(f"Filebase {filebase_id} already being processed, deferring")
                    skipped.append((user_id, filebase_id))
                    continue

                thread = threading.Thread(
                    target=self._sync_filebase,
                    args=(user_id, filebase_id),
                    daemon=True
                )
                thread.start()

            except Empty:
                break

        # 把跳过的项放回队列，等待下次轮询时重新处理
        for item in skipped:
            self._trigger_queue.put(item)
            self._trigger_event.set()

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
                WHERE is_synced_to_kb = 1 AND COALESCE(status, 'active') != 'trashed'
            """).fetchall()

            return [
                {'id': row['id'], 'user_id': row['owner_id'], 'name': row['name']}
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to query enabled filebases: {e}")
            return []

    def _trigger_sync(self, user_id: str, filebase_id: str):
        """触发同步（加入队列并通知工作线程）"""
        self._trigger_queue.put((user_id, filebase_id))
        self._trigger_event.set()

    def trigger_sync_now(self, user_id: str, filebase_id: str):
        """立即触发同步"""
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
                logger.warning(f"Filebase {filebase_id} source directory missing, cleaning up synced data")
                self.cleanup_filebase(user_id, filebase_id)
                return

            current_files = self._scan_filebase(source_dir)

            self._filebase_stats[filebase_id] = {
                'total_files': len(current_files),
                'syncable_files': sum(1 for f in current_files.values() if f['syncable'])
            }

            state = self._state_manager.load_state(user_id, filebase_id)

            self._process_changes(user_id, filebase_id, source_dir, current_files, state)

            self._cleanup_deleted(user_id, filebase_id, current_files, state)

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
        """处理文件变化：新增和修改（优化版：轻量文件内联 + 批量持久化）"""
        heavy_files = []
        light_files = []

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
                ext = os.path.splitext(file_info['path'])[1].lower()
                if ext in _LIGHT_EXTENSIONS:
                    light_files.append((relative_path, file_info))
                else:
                    heavy_files.append((relative_path, file_info))

        state.syncable_files = sum(1 for f in current_files.values() if f['syncable'])

        if not light_files and not heavy_files:
            # 无 syncable 文件需要处理，但可能有非 syncable 文件需要索引文件名
            self._index_non_syncable(user_id, filebase_id, current_files, state)
            return

        logger.info(
            f"Filebase {filebase_id}: {len(light_files)} light + "
            f"{len(heavy_files)} heavy files to sync"
        )

        light_updates = []
        for relative_path, file_info in light_files:
            result = self._convert_single(
                user_id, filebase_id, relative_path, file_info, state
            )
            if result:
                light_updates.append(result)

        if light_updates:
            self._state_manager.batch_update_file_states(
                user_id, filebase_id, light_updates
            )
            logger.debug(f"Filebase {filebase_id}: batch saved {len(light_updates)} light files")

        if not heavy_files:
            return

        # ─── 打包环境（PyInstaller frozen）降级路径 ───
        # frozen 时 sys.executable 是应用 exe，无法当解释器执行 sync_subprocess.py
        # （会把整个应用再启动一遍，stdout 是应用日志而非 JSON，导致 docx/xlsx/pptx
        # 全部转换失败 "Expecting value...")。这里退化为与轻量文件一致的
        # 主进程内串行转换（同线程调用 _convert_single，无并发 DB 写竞态），
        # 保证打包版重文件同步可用；每轮给 15 分钟预算，剩余留待下轮轮询。
        if getattr(sys, 'frozen', False):
            deadline = time.time() + 900
            heavy_updates = []
            for relative_path, file_info in heavy_files:
                if time.time() > deadline:
                    logger.warning(
                        f"Sync timeout for {filebase_id}: heavy inline conversion reached deadline"
                    )
                    break
                result = self._convert_single(
                    user_id, filebase_id, relative_path, file_info, state
                )
                if result:
                    heavy_updates.append(result)
            if heavy_updates:
                self._state_manager.batch_update_file_states(
                    user_id, filebase_id, heavy_updates
                )
                logger.info(
                    f"Filebase {filebase_id}: inline converted {len(heavy_updates)} heavy files (frozen)"
                )
            self._index_non_syncable(user_id, filebase_id, current_files, state)
            return

        heavy_updates_lock = threading.Lock()
        heavy_updates = []
        heavy_index_updates = []

        deadline = time.time() + 300

        def _sync_heavy(relative_path, file_info):
            try:
                source_path = file_info['path']
                source_mtime = file_info['mtime']
                script_path = os.path.join(os.path.dirname(__file__), 'sync_subprocess.py')
                proc = subprocess.run(
                    [sys.executable, script_path, source_path, relative_path, str(source_mtime)],
                    capture_output=True, text=True, timeout=120
                )
                if proc.returncode == 0 and proc.stdout:
                    data = json.loads(proc.stdout.strip())
                    _, _, status, error, target_mtime, md_content = data

                    if status == 'synced' and md_content:
                        kb_relative_path = f"imported/{filebase_id}/{relative_path}"
                        if not kb_relative_path.lower().endswith('.md'):
                            kb_relative_path += '.md'
                        from .routes import _extract_title_from_md
                        title = _extract_title_from_md(md_content) or os.path.splitext(os.path.basename(source_path))[0]
                        with heavy_updates_lock:
                            heavy_index_updates.append((kb_relative_path, title, md_content))
                            heavy_updates.append((relative_path, source_mtime, 'synced', None, time.time()))
                    else:
                        with heavy_updates_lock:
                            heavy_updates.append((relative_path, source_mtime, 'failed', error or 'conversion_failed', None))
                else:
                    with heavy_updates_lock:
                        heavy_updates.append((relative_path, source_mtime, 'failed', proc.stderr or 'subprocess_error', None))
            except subprocess.TimeoutExpired:
                with heavy_updates_lock:
                    heavy_updates.append((relative_path, file_info['mtime'], 'failed', 'timeout', None))
            except Exception as e:
                logger.error(f"Error syncing heavy file {relative_path}: {e}")
                with heavy_updates_lock:
                    heavy_updates.append((relative_path, file_info['mtime'], 'failed', str(e), None))
            finally:
                self._semaphore.release()

        for i, (relative_path, file_info) in enumerate(heavy_files):
            remaining = deadline - time.time()
            if remaining <= 0:
                logger.warning(f"Sync timeout for {filebase_id}: no time left to start more conversions")
                break
            if not self._semaphore.acquire(timeout=min(remaining, 60)):
                logger.warning(f"Sync timeout for {filebase_id}: timeout waiting to start conversion of {relative_path}")
                break

            thread = threading.Thread(
                target=_sync_heavy,
                args=(relative_path, file_info),
                daemon=True
            )
            thread.start()

        for _ in range(self._max_concurrent):
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            self._semaphore.acquire(timeout=min(remaining, 60))

        if heavy_index_updates:
            from .routes import batch_update_search_index
            batch_update_search_index(user_id, heavy_index_updates)
            logger.debug(f"Filebase {filebase_id}: batch updated {len(heavy_index_updates)} search index entries")

        if heavy_updates:
            self._state_manager.batch_update_file_states(
                user_id, filebase_id, heavy_updates
            )
            logger.debug(f"Filebase {filebase_id}: batch saved {len(heavy_updates)} heavy files")

        # 处理非 syncable 文件：不提取内容，只索引文件名和路径
        self._index_non_syncable(user_id, filebase_id, current_files, state)

    def _index_non_syncable(self, user_id: str, filebase_id: str,
                            current_files: Dict, state) -> None:
        """为非 syncable 文件建立文件名索引，使其可通过文件名/路径搜索到"""
        filename_updates = []

        for relative_path, file_info in current_files.items():
            if file_info['syncable']:
                continue

            existing = state.files.get(relative_path)
            source_mtime = file_info['mtime']

            needs_sync = (
                existing is None or
                existing.source_mtime < source_mtime or
                existing.status in ('failed', 'filename_only')
            )

            if not needs_sync:
                continue

            source_path = file_info['path']
            basename = os.path.basename(source_path)
            title = os.path.splitext(basename)[0]
            ext = os.path.splitext(basename)[1].lower()
            content = (
                f"[文件名]: {basename}\n"
                f"[路径]: {relative_path}\n"
                f"[类型]: {ext if ext else '无扩展名'}\n"
            )

            kb_relative_path = f"imported/{filebase_id}/{relative_path}"
            if not kb_relative_path.lower().endswith('.md'):
                kb_relative_path += '.md'

            try:
                from .routes import update_search_index
                update_search_index(user_id, kb_relative_path, title, content)
                filename_updates.append((relative_path, source_mtime, 'filename_only', None, time.time()))
            except Exception as e:
                logger.error(f"Failed to index filename for {relative_path}: {e}")
                filename_updates.append((relative_path, source_mtime, 'failed', str(e), None))

        if filename_updates:
            self._state_manager.batch_update_file_states(
                user_id, filebase_id, filename_updates
            )
            logger.info(f"Filebase {filebase_id}: indexed {len(filename_updates)} filenames")

    def _convert_single(self, user_id: str, filebase_id: str,
                          relative_path: str, file_info: Dict,
                          state) -> Optional[tuple]:
        """转换单个文件，返回 (relative_path, source_mtime, status, error, target_mtime)
        不直接写入 DB，由调用方批量持久化。返回 None 表示无需更新。"""
        try:
            source_path = file_info['path']
            source_mtime = file_info['mtime']

            logger.debug(f"Converting: {relative_path}")

            md_content = convert_file(source_path, relative_path, filebase_id)

            if md_content is None:
                logger.warning(f"Failed to convert: {relative_path}")
                return (relative_path, source_mtime, 'failed', 'conversion_failed', None)

            kb_relative_path = f"imported/{filebase_id}/{relative_path}"
            if not kb_relative_path.lower().endswith('.md'):
                kb_relative_path += '.md'

            from .routes import update_search_index, _extract_title_from_md
            title = _extract_title_from_md(md_content) or os.path.splitext(os.path.basename(source_path))[0]
            update_search_index(user_id, kb_relative_path, title, md_content)

            logger.debug(f"Synced: {relative_path}")
            return (relative_path, source_mtime, 'synced', None, time.time())

        except Exception as e:
            logger.error(f"Error syncing {relative_path}: {e}")
            return (relative_path, file_info['mtime'], 'failed', str(e), None)

    def _cleanup_deleted(self, user_id: str, filebase_id: str, current_files: Dict, state):
        """清理已删除的文件（使用已有扫描结果，避免重复目录遍历）"""
        current_paths = set(current_files.keys())

        synced_paths = set(state.files.keys())

        deleted_paths = synced_paths - current_paths

        for relative_path in deleted_paths:
            try:
                kb_relative_path = f"imported/{filebase_id}/{relative_path}"
                if not kb_relative_path.lower().endswith('.md'):
                    kb_relative_path += '.md'

                from .routes import remove_from_index
                remove_from_index(user_id, kb_relative_path)

                self._state_manager.remove_file(user_id, filebase_id, relative_path)

                logger.debug(f"Deleted synced file: {relative_path}")

            except Exception as e:
                logger.error(f"Failed to delete synced file {relative_path}: {e}")

    def get_sync_status(self, user_id: str, filebase_id: str) -> Dict:
        """获取同步状态"""
        state = self._state_manager.get_state(user_id, filebase_id)

        return {
            'enabled': self._is_sync_enabled(filebase_id),
            'status': state.get_display_stats(),
            'last_sync': state.last_sync,
            'is_syncing': filebase_id in self._processing_filebases
        }

    def get_filebase_stats(self, filebase_id: str) -> Optional[Dict]:
        """获取文件库扫描统计缓存（total_files, syncable_files），
        由 _scan_filebase 在同步时填充，供 API 层直接读取避免 os.walk"""
        return self._filebase_stats.get(filebase_id)

    def adjust_file_count(self, user_id: str, filebase_id: str, delta: int) -> None:
        """文件操作后增量调整文件数，避免等待完整同步扫描"""
        if filebase_id in self._filebase_stats:
            self._filebase_stats[filebase_id]['total_files'] = max(
                self._filebase_stats[filebase_id]['total_files'] + delta, 0
            )
        # 同时更新持久化状态
        try:
            from kb.sync_state import get_sync_state_manager
            state_mgr = get_sync_state_manager()
            state = state_mgr.load_state(user_id, filebase_id)
            state.total_files = max(state.total_files + delta, 0)
            state_mgr.save_state(user_id, filebase_id, state)
        except Exception:
            logger.exception("Failed to update sync_state total_files")

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
        """清理文件库的同步数据（同步状态、FTS5 索引、文件记录）"""
        try:
            self._state_manager.clear_all_state(user_id, filebase_id)

            from kb.database import get_db
            conn = get_db(user_id)
            # 清理 imported/ 和 _disabled/ 两种前缀（软删除后数据在 _disabled/ 下）
            for prefix in (f'imported/{filebase_id}/%', f'_disabled/{filebase_id}/%'):
                conn.execute(
                    "DELETE FROM wiki_fts WHERE usr_id = ? AND path LIKE ?",
                    (user_id, prefix)
                )
                conn.execute(
                    "DELETE FROM wiki_files WHERE usr_id = ? AND path LIKE ?",
                    (user_id, prefix)
                )
            conn.commit()

            logger.info(f"Cleaned up sync data for filebase {filebase_id}")

        except Exception as e:
            logger.error(f"Failed to cleanup filebase {filebase_id}: {e}")

    def _run_migration_once(self):
        """一次性迁移：确保启用了同步的文件库的 imported 文件在 wiki_files 表中有记录"""
        try:
            enabled_filebases = self._get_enabled_filebases()
            for fb in enabled_filebases:
                fb_key = fb['id']
                if fb_key in self._migrated_filebases:
                    continue
                self._migrate_single_filebase(fb['user_id'], fb['id'])
                self._migrated_filebases.add(fb_key)
            logger.info("Migration of wiki_files table completed")
        except Exception as e:
            logger.error(f"Failed to migrate wiki_files: {e}")

    def _migrate_single_filebase(self, user_id: str, filebase_id: str):
        """迁移单个文件库的 wiki_files 记录"""
        state = self._state_manager.get_state(user_id, filebase_id)

        for relative_path, file_state in state.files.items():
            if file_state.status != 'synced':
                continue
            kb_path = f"imported/{filebase_id}/{relative_path}"
            if not kb_path.lower().endswith('.md'):
                kb_path += '.md'

            from .database import get_db
            conn = get_db(user_id)
            row = conn.execute(
                "SELECT path FROM wiki_files WHERE usr_id = ? AND path = ?",
                (user_id, kb_path)
            ).fetchone()
            if not row and file_state.source:
                ft_row = conn.execute(
                    "SELECT content FROM wiki_fts WHERE usr_id = ? AND path = ?",
                    (user_id, kb_path)
                ).fetchone()
                if ft_row:
                    from .routes import update_search_index
                    update_search_index(user_id, kb_path, file_state.source, ft_row['content'])

    def _migrate_existing_wiki_files(self):
        """保留旧接口以兼容外部调用"""
        self._run_migration_once()


_sync_worker = None


def get_sync_worker() -> SyncWorker:
    """获取同步工作线程单例"""
    global _sync_worker
    if _sync_worker is None:
        _sync_worker = SyncWorker()
    return _sync_worker
