import os
import sqlite3
import threading
import time

from fb.models import ALL_TABLES, CREATE_INDEXES, MIGRATIONS, CREATE_INDEX_SYNC_STATES, CREATE_INDEX_SHARED, CREATE_INDEX_FILE_LOCKS
from fb.models import MIGRATIONS_META, DB_MIGRATIONS

_local = threading.local()


def _get_data_dir():
    """获取全局数据存储目录：workspaces/data/"""
    from server.workspace import _get_workspace_dir
    data_dir = os.path.join(_get_workspace_dir(), 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_db_path():
    db_dir = os.path.join(_get_data_dir(), 'fb')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, 'fb.db')


def init_db(conn):
    for sql in ALL_TABLES:
        conn.execute(sql)
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
        except Exception:
            pass
    for sql in CREATE_INDEXES:
        conn.execute(sql)
    for sql in CREATE_INDEX_SYNC_STATES:
        try:
            conn.execute(sql)
        except Exception:
            pass
    for sql in CREATE_INDEX_SHARED:
        try:
            conn.execute(sql)
        except Exception:
            pass
    for sql in CREATE_INDEX_FILE_LOCKS:
        try:
            conn.execute(sql)
        except Exception:
            pass
    # 运行版本化迁移
    conn.execute(MIGRATIONS_META)
    applied = set()
    for r in conn.execute("SELECT version FROM _migrations").fetchall():
        applied.add(r['version'])
    for version, sql in sorted(DB_MIGRATIONS.items()):
        if version not in applied:
            try:
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
                    (version, time.time())
                )
            except Exception:
                pass
    conn.commit()


def get_db():
    if not hasattr(_local, 'conn') or _local.conn is None:
        db_path = get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        init_db(conn)
        _local.conn = conn
    return _local.conn


def get_visible_fb_ids(user_id, is_admin=False):
    if is_admin:
        db = get_db()
        rows = db.execute("SELECT id FROM filebases WHERE COALESCE(status, 'active') != 'trashed'").fetchall()
        return [r['id'] for r in rows]
    db = get_db()
    ids = set()
    rows = db.execute("SELECT filebase_id FROM filebase_permissions WHERE user_id = ?", (user_id,)).fetchall()
    for r in rows:
        ids.add(r['filebase_id'])
    rows = db.execute("SELECT id FROM filebases WHERE owner_id = ? AND COALESCE(status, 'active') != 'trashed'", (user_id,)).fetchall()
    for r in rows:
        ids.add(r['id'])
    return list(ids)


def get_user_role(user_id):
    return 'admin'
