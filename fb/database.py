import os
import sqlite3
import threading

from fb.models import ALL_TABLES, CREATE_INDEXES, MIGRATIONS, CREATE_INDEX_SYNC_STATES

_local = threading.local()


def _get_data_dir():
    """获取全局数据存储目录：workspaces/data/"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'workspaces', 'data')
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
        rows = db.execute("SELECT id FROM filebases").fetchall()
        return [r['id'] for r in rows]
    db = get_db()
    ids = set()
    rows = db.execute("SELECT filebase_id FROM filebase_permissions WHERE user_id = ?", (user_id,)).fetchall()
    for r in rows:
        ids.add(r['filebase_id'])
    rows = db.execute("SELECT id FROM filebases WHERE owner_id = ?", (user_id,)).fetchall()
    for r in rows:
        ids.add(r['id'])
    return list(ids)


def get_user_role(user_id):
    return 'admin'
