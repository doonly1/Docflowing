import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import List

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
    kb_dir = os.path.join(base, 'kb')
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir


def get_db_path(user_id=None):
    kb_dir = _get_user_kb_dir(user_id or 'default')
    return os.path.join(kb_dir, 'wiki.db')


def init_db(conn):
    for sql in ALL_TABLES:
        conn.execute(sql)
    for sql in CREATE_INDEXES:
        conn.execute(sql)
    conn.commit()


def get_db(user_id=None):
    if not hasattr(_local, 'conn') or _local.conn is None:
        db_path = get_db_path(user_id)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        init_db(conn)
        _local.conn = conn
    return _local.conn
