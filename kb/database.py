import os
import sqlite3
import threading

from kb.models import ALL_TABLES, CREATE_INDEXES

_local = threading.local()


def get_db_path():
    kb_config_dir = os.path.join(os.path.expanduser('~'), '.config', 'docproc', 'kb')
    os.makedirs(kb_config_dir, exist_ok=True)
    return os.path.join(kb_config_dir, 'wiki.db')


def init_db(conn):
    for sql in ALL_TABLES:
        conn.execute(sql)
    for sql in CREATE_INDEXES:
        conn.execute(sql)
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


def close_db():
    if hasattr(_local, 'conn') and _local.conn is not None:
        _local.conn.close()
        _local.conn = None
