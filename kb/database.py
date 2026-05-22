import os
import sqlite3
import threading

from server.workspace import _get_workspace_dir

ALL_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS wiki_info (
        usr_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (usr_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wiki_permissions (
        usr_id TEXT NOT NULL,
        shared_user_id TEXT NOT NULL,
        permission_level TEXT NOT NULL DEFAULT 'view',
        created_at REAL NOT NULL,
        PRIMARY KEY (usr_id, shared_user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wiki_files (
        usr_id TEXT NOT NULL,
        path TEXT NOT NULL,
        title TEXT DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        file_size INTEGER DEFAULT 0,
        PRIMARY KEY (usr_id, path)
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
        usr_id,
        title,
        content,
        path,
        tokenize='trigram'
    )
    """,
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_wiki_info_usr ON wiki_info(usr_id)",
    "CREATE INDEX IF NOT EXISTS idx_wiki_files_usr ON wiki_files(usr_id)",
    "CREATE INDEX IF NOT EXISTS idx_wiki_files_title ON wiki_files(title)",
    "CREATE INDEX IF NOT EXISTS idx_wiki_permissions_usr ON wiki_permissions(usr_id)",
]

_local = threading.local()


def _get_user_kb_dir(user_id: str) -> str:
    base = _get_workspace_dir(user_id)
    kb_dir = os.path.join(base, 'data', 'kb')
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir


def get_db_path(user_id=None):
    if user_id is None:
        return None
    kb_dir = _get_user_kb_dir(user_id)
    return os.path.join(kb_dir, 'wiki.db')


def _migrate_fts_tokenizer(conn):
    """检查现有 wiki_fts 的 tokenizer，非 trigram 则迁移"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='wiki_fts'"
    ).fetchone()
    if row and 'trigram' not in (row['sql'] or ''):
        old_data = conn.execute(
            "SELECT usr_id, title, content, path FROM wiki_fts"
        ).fetchall()
        conn.execute("DROP TABLE IF EXISTS wiki_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE wiki_fts USING fts5(
                usr_id, title, content, path,
                tokenize='trigram'
            )
        """)
        for old in old_data:
            try:
                conn.execute(
                    "INSERT INTO wiki_fts (usr_id, title, content, path) "
                    "VALUES (?, ?, ?, ?)",
                    (old['usr_id'], old['title'], old['content'], old['path'])
                )
            except Exception:
                pass
        conn.commit()


def init_db(conn):
    for sql in ALL_TABLES:
        conn.execute(sql)
    for sql in CREATE_INDEXES:
        conn.execute(sql)
    _migrate_fts_tokenizer(conn)
    conn.commit()


def get_db(user_id=None):
    if not user_id:
        raise ValueError("user_id is required to open database")
    if not hasattr(_local, 'conn') or _local.conn is None:
        db_path = get_db_path(user_id)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        init_db(conn)
        _local.conn = conn
    return _local.conn
