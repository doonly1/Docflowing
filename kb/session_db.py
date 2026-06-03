import json
import logging
import os
import platform
import random
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from server.workspace import _get_workspace_dir

logger = logging.getLogger(__name__)

# FTS5 simple 分词器扩展路径（平台相关）
_EXTENSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools')
_SYS = platform.system()
_MACH = platform.machine()

if _SYS == 'Windows':
    _FTS_NAME = 'simple.dll'
elif _SYS == 'Linux':
    _FTS_NAME = 'simple.so'
elif _SYS == 'Darwin':
    # macOS: Intel (x86_64) / Apple Silicon (arm64)
    _FTS_NAME = 'simple_arm64.dylib' if _MACH == 'arm64' else 'simple_x64.dylib'
else:
    _FTS_NAME = ''
_FTS_EXTENSION = os.path.join(_EXTENSION_DIR, _FTS_NAME)

SCHEMA_VERSION = 3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    model TEXT,
    title TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    end_reason TEXT,
    message_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER,
    sources TEXT
);

CREATE TABLE IF NOT EXISTS state_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, timestamp);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    tokenize='{tokenizer}'
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (
        new.id,
        COALESCE(new.content, '')
    );
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
    INSERT INTO messages_fts(rowid, content) VALUES (
        new.id,
        COALESCE(new.content, '')
    );
END;
"""


def _get_user_kb_dir(user_id: str) -> str:
    base = _get_workspace_dir(user_id)
    kb_dir = os.path.join(base, 'data', 'kb')
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir


class SessionDB:
    _WRITE_MAX_RETRIES = 15
    _WRITE_RETRY_MIN_S = 0.020
    _WRITE_RETRY_MAX_S = 0.150
    _CHECKPOINT_EVERY_N_WRITES = 50

    def __init__(self, user_id: str, db_path: Path = None):
        self.user_id = user_id
        kb_dir = _get_user_kb_dir(user_id)
        data_dir = kb_dir
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = Path(db_path) if db_path else Path(data_dir) / 'state.db'
        self._lock = threading.Lock()
        self._write_count = 0
        self._simple_loaded = False

        # 启用扩展加载（Python < 3.12 需在 connect 前全局启用）
        self._enable_sqlite_extensions()

        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=1.0,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # 加载 simple 分词器扩展
        self._simple_loaded = self._load_fts_extension()
        self._fts_tokenizer = 'simple' if self._simple_loaded else 'unicode61'

        self._init_schema()

    @staticmethod
    def _enable_sqlite_extensions() -> None:
        """启用 SQLite 扩展加载能力。
        Python < 3.12 需在 connect 前全局启用，>= 3.12 支持 per-connection 启用。"""
        try:
            sqlite3.enable_load_extension(True)
        except AttributeError:
            # Python >= 3.12：conn.enable_load_extension() 已足够
            pass

    def _load_fts_extension(self) -> bool:
        """加载 FTS5 simple 分词器扩展。返回 True 表示加载成功。"""
        if not os.path.isfile(_FTS_EXTENSION):
            logger.warning("FTS5 simple 扩展未找到: %s，将使用 unicode61 作为备选", _FTS_EXTENSION)
            return False
        try:
            conn = self._conn
            # Python >= 3.12 per-connection 启用
            try:
                conn.enable_load_extension(True)
            except AttributeError:
                pass  # 已在全局启用
            conn.load_extension(_FTS_EXTENSION)
            logger.info("FTS5 simple 分词器扩展加载成功")
            return True
        except Exception as e:
            logger.warning("加载 FTS5 simple 扩展失败 (%s): %s，将使用 unicode61 备选", _FTS_EXTENSION, e)
            return False

    def _execute_write(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        last_err: Optional[Exception] = None
        for attempt in range(self._WRITE_MAX_RETRIES):
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        result = fn(self._conn)
                        self._conn.commit()
                    except BaseException:
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        raise
                self._write_count += 1
                if self._write_count % self._CHECKPOINT_EVERY_N_WRITES == 0:
                    self._try_wal_checkpoint()
                return result
            except sqlite3.OperationalError as exc:
                err_msg = str(exc).lower()
                if "locked" in err_msg or "busy" in err_msg:
                    last_err = exc
                    if attempt < self._WRITE_MAX_RETRIES - 1:
                        jitter = random.uniform(
                            self._WRITE_RETRY_MIN_S,
                            self._WRITE_RETRY_MAX_S,
                        )
                        time.sleep(jitter)
                        continue
                raise
        raise last_err or sqlite3.OperationalError("database is locked after max retries")

    def _try_wal_checkpoint(self) -> None:
        try:
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:
            pass

    def _migrate_fts_v2_to_v3(self, cursor) -> None:
        """迁移 FTS 表：删除旧 unicode61 表，用 simple 分词器重建并重新索引。"""
        try:
            cursor.execute("DROP TABLE IF EXISTS messages_fts")
            cursor.executescript(FTS_SQL.format(tokenizer=self._fts_tokenizer))
            cursor.execute(
                "INSERT INTO messages_fts(rowid, content) "
                "SELECT id, COALESCE(content, '') FROM messages"
            )
            logger.info("FTS 表已重建为 simple 分词器")
        except Exception as e:
            logger.error("FTS 迁移失败: %s", e)
            raise

    def close(self):
        with self._lock:
            if self._conn:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except Exception:
                    pass
                self._conn.close()
                self._conn = None

    def _init_schema(self):
        cursor = self._conn.cursor()
        cursor.executescript(SCHEMA_SQL)

        cursor.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            # 全新数据库
            cursor.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            cursor.executescript(FTS_SQL.format(tokenizer=self._fts_tokenizer))
        else:
            db_version = row["version"]
            if db_version < 2:
                # v1 → v2: add sources column
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN sources TEXT")
                except sqlite3.OperationalError:
                    pass
                cursor.execute("UPDATE schema_version SET version = 2")
                db_version = 2

            if db_version < 3:
                # v2 → v3: migrate FTS to simple tokenizer
                self._migrate_fts_v2_to_v3(cursor)
                cursor.execute("UPDATE schema_version SET version = 3")
            else:
                # 确保 FTS 表存在
                try:
                    cursor.execute("SELECT * FROM messages_fts LIMIT 0")
                except sqlite3.OperationalError:
                    cursor.executescript(FTS_SQL.format(tokenizer=self._fts_tokenizer))

        self._conn.commit()

    def create_session(self, session_id: str, user_id: str = None, model: str = None) -> str:
        def _do(conn):
            conn.execute(
                """INSERT OR IGNORE INTO sessions (id, user_id, model, started_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, user_id, model, time.time()),
            )
        self._execute_write(_do)
        return session_id

    def end_session(self, session_id: str, end_reason: str = None) -> None:
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? "
                "WHERE id = ? AND ended_at IS NULL",
                (time.time(), end_reason, session_id),
            )
        self._execute_write(_do)

    def set_session_title(self, session_id: str, title: str) -> bool:
        if not title or not title.strip():
            title = None
        def _do(conn):
            cursor = conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
            return cursor.rowcount
        return self._execute_write(_do) > 0

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str = None,
        tool_name: str = None,
        token_count: int = None,
        sources: str = None,
    ) -> int:
        def _do(conn):
            cursor = conn.execute(
                """INSERT INTO messages (session_id, role, content, tool_name, timestamp, token_count, sources)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, tool_name, time.time(), token_count, sources),
            )
            msg_id = cursor.lastrowid
            conn.execute(
                "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
                (session_id,),
            )
            return msg_id
        return self._execute_write(_do)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_messages(self, session_id: str, limit: int = None) -> List[Dict[str, Any]]:
        with self._lock:
            if limit:
                cursor = self._conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp, id LIMIT ?",
                    (session_id, limit),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp, id",
                    (session_id,),
                )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def list_sessions(
        self,
        user_id: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        where_clauses = []
        params = []
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(user_id)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        params.extend([limit, offset])
        with self._lock:
            cursor = self._conn.execute(
                f"""SELECT s.*,
                    COALESCE(
                        (SELECT SUBSTR(m.content, 1, 80)
                         FROM messages m
                         WHERE m.session_id = s.id AND m.role = 'user' AND m.content IS NOT NULL
                         ORDER BY m.timestamp, m.id LIMIT 1),
                        ''
                    ) AS preview,
                    COALESCE(
                        (SELECT MAX(m2.timestamp) FROM messages m2 WHERE m2.session_id = s.id),
                        s.started_at
                    ) AS last_active
                FROM sessions s
                {where_sql}
                ORDER BY last_active DESC, s.started_at DESC
                LIMIT ? OFFSET ?""",
                params,
            )
            rows = cursor.fetchall()
        sessions = []
        for row in rows:
            s = dict(row)
            raw = (s.pop("preview") or "").strip()
            s["preview"] = raw[:80] + ("..." if len(raw) > 80 else "") if raw else ""
            sessions.append(s)
        return sessions

    # ── 搜索辅助方法 ─────────────────────────────────────────────

    @staticmethod
    def _escape_fts_term(term: str) -> str:
        """转义 FTS5 查询中的特殊字符，用双引号包裹。"""
        escaped = term.replace('"', '""')
        return f'"{escaped}"'

    def _fts_search(
        self,
        keywords: List[str],
        user_id: Optional[str],
        limit: int,
        mode: str = 'AND',
    ) -> List[Dict[str, Any]]:
        """FTS5 搜索，支持 AND/OR 模式。"""
        if mode == 'AND':
            fts_clause = ' '.join(self._escape_fts_term(k) for k in keywords)
        else:
            fts_clause = ' OR '.join(self._escape_fts_term(k) for k in keywords)

        where_clauses = ["messages_fts MATCH ?"]
        params: list = [fts_clause]
        if user_id:
            where_clauses.append("s.user_id = ?")
            params.append(user_id)
        params.append(limit)

        sql = f"""
            SELECT
                m.id,
                m.session_id,
                m.role,
                snippet(messages_fts, 0, '>>>', '<<<', '...', 120) AS snippet,
                m.timestamp,
                s.title AS session_title
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN sessions s ON s.id = m.session_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY rank
            LIMIT ?
        """
        try:
            with self._lock:
                cursor = self._conn.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            logger.debug("FTS5 %s 搜索失败: %s", mode, e)
            return []

    @staticmethod
    def _generate_like_snippet(content: Optional[str], keywords: List[str], max_len: int = 120) -> str:
        """为 LIKE 搜索结果手动生成 snippet。"""
        if not content:
            return ''
        # 找第一个关键词出现位置
        content_lower = content.lower()
        best_pos = -1
        for kw in keywords:
            pos = content_lower.find(kw.lower())
            if pos != -1 and (best_pos == -1 or pos < best_pos):
                best_pos = pos
        if best_pos == -1:
            return content[:max_len]
        half = max_len // 2
        start = max(0, best_pos - half)
        end = min(len(content), start + max_len)
        if end - start < max_len:
            start = max(0, end - max_len)
        prefix = '...' if start > 0 else ''
        suffix = '...' if end < len(content) else ''
        return f'{prefix}{content[start:end]}{suffix}'

    def _like_search(
        self,
        keywords: List[str],
        user_id: Optional[str],
        limit: int,
        mode: str = 'AND',
    ) -> List[Dict[str, Any]]:
        """LIKE 模糊搜索，支持 AND/OR 模式，手动生成 snippet。"""
        connector = ' AND ' if mode == 'AND' else ' OR '
        like_parts = []
        params: list = []
        for kw in keywords:
            like_parts.append("m.content LIKE ?")
            params.append(f'%{kw}%')

        where_clauses = [f"({connector.join(like_parts)})"]
        if user_id:
            where_clauses.append("s.user_id = ?")
            params.append(user_id)
        params.append(limit)

        sql = f"""
            SELECT
                m.id,
                m.session_id,
                m.role,
                m.content,
                m.timestamp,
                s.title AS session_title
            FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY m.timestamp DESC
            LIMIT ?
        """
        try:
            with self._lock:
                cursor = self._conn.execute(sql, params)
                matches = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            logger.debug("LIKE %s 搜索失败: %s", mode, e)
            return []

        # 手动生成 snippet
        for match in matches:
            content = match.pop("content", None)
            match["snippet"] = self._generate_like_snippet(content, keywords)
        return matches

    def search_messages(
        self,
        query: str,
        user_id: str = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        多阶段搜索降级：FTS5 AND → FTS5 OR → LIKE AND → LIKE OR。
        返回结果包含 id, session_id, role, snippet, timestamp, session_title。
        """
        if not query or not query.strip():
            return []
        limit = min(max(limit, 1), 50)
        keywords = query.strip().split()
        if not keywords:
            return []

        # 第一阶段：FTS5 AND（最精准）
        result = self._fts_search(keywords, user_id, limit, mode='AND')
        if result:
            return result

        # 第二阶段：FTS5 OR（宽松召回）
        result = self._fts_search(keywords, user_id, limit, mode='OR')
        if result:
            return result

        # 第三阶段：LIKE AND（兜底精准）
        result = self._like_search(keywords, user_id, limit, mode='AND')
        if result:
            return result

        # 第四阶段：LIKE OR（兜底召回）
        result = self._like_search(keywords, user_id, limit, mode='OR')
        return result

    def delete_messages(self, session_id: str, message_ids: List[int]) -> int:
        def _do(conn):
            placeholders = ",".join("?" * len(message_ids))
            conn.execute(
                f"DELETE FROM messages WHERE session_id = ? AND id IN ({placeholders})",
                [session_id] + message_ids,
            )
            deleted = conn.rowcount
            conn.execute(
                "UPDATE sessions SET message_count = MAX(0, message_count - ?) WHERE id = ?",
                (deleted, session_id),
            )
            return deleted
        return self._execute_write(_do)

    def delete_session(self, session_id: str) -> bool:
        def _do(conn):
            cursor = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)
            )
            if cursor.fetchone()[0] == 0:
                return False
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return True
        return self._execute_write(_do)

    def clear_all_sessions(self) -> int:
        def _do(conn):
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM sessions")
            return count
        return self._execute_write(_do)

    def prune_sessions(self, older_than_days: int = 90) -> int:
        cutoff = time.time() - (older_than_days * 86400)
        def _do(conn):
            cursor = conn.execute(
                "SELECT id FROM sessions WHERE started_at < ? AND ended_at IS NOT NULL",
                (cutoff,),
            )
            session_ids = [row["id"] for row in cursor.fetchall()]
            if not session_ids:
                return 0
            placeholders = ",".join("?" * len(session_ids))
            conn.execute(
                f"DELETE FROM messages WHERE session_id IN ({placeholders})",
                session_ids,
            )
            conn.execute(
                f"DELETE FROM sessions WHERE id IN ({placeholders})",
                session_ids,
            )
            return len(session_ids)
        return self._execute_write(_do) or 0

    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM state_meta WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return row["value"] if isinstance(row, sqlite3.Row) else row[0]

    def set_meta(self, key: str, value: str) -> None:
        def _do(conn):
            conn.execute(
                "INSERT INTO state_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        self._execute_write(_do)

    def auto_prune(self, retention_days: int = 90, min_interval_hours: int = 24) -> Dict[str, Any]:
        result: Dict[str, Any] = {"skipped": False, "pruned": 0}
        try:
            last_raw = self.get_meta("last_auto_prune")
            now = time.time()
            if last_raw:
                try:
                    last_ts = float(last_raw)
                    if now - last_ts < min_interval_hours * 3600:
                        result["skipped"] = True
                        return result
                except (TypeError, ValueError):
                    pass
            pruned = self.prune_sessions(older_than_days=retention_days)
            result["pruned"] = pruned
            self.set_meta("last_auto_prune", str(now))
            if pruned > 0:
                logger.info("state.db auto-prune: deleted %d session(s) older than %d days", pruned, retention_days)
        except Exception as exc:
            logger.warning("state.db auto-prune failed: %s", exc)
            result["error"] = str(exc)
        return result


_session_db_instances: Dict[str, SessionDB] = {}
_session_db_lock = threading.Lock()


def get_session_db(user_id: str) -> SessionDB:
    global _session_db_instances
    if user_id not in _session_db_instances:
        with _session_db_lock:
            if user_id not in _session_db_instances:
                _session_db_instances[user_id] = SessionDB(user_id)
    return _session_db_instances[user_id]

