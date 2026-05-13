"""用户活跃时间数据库

存储位置：workspaces/data/server.db
迁移：从旧路径 ~/.config/DocProc/server.db 自动迁移
"""

import os
import time
import shutil
import sqlite3
from threading import local

_db_local = local()

def _get_data_dir():
    """获取全局数据存储目录：workspaces/data/"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'workspaces', 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def _migrate_old_db():
    """从旧路径 ~/.config/DocProc/server.db 迁移数据库到新路径"""
    old_db_path = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'server.db')
    new_db_path = os.path.join(_get_data_dir(), 'server.db')

    if os.path.exists(old_db_path) and not os.path.exists(new_db_path):
        try:
            shutil.copy2(old_db_path, new_db_path)
        except Exception:
            pass

def _get_db_path():
    _migrate_old_db()
    return os.path.join(_get_data_dir(), 'server.db')


def get_db():
    """获取线程级单例数据库连接"""
    if not hasattr(_db_local, 'conn') or _db_local.conn is None:
        db_path = _get_db_path()
        _db_local.conn = sqlite3.connect(db_path)
        _db_local.conn.row_factory = sqlite3.Row
        _db_local.conn.execute("PRAGMA journal_mode=WAL")
        _init_db(_db_local.conn)
    return _db_local.conn


def _init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_activity (
            user_id TEXT PRIMARY KEY,
            last_active REAL NOT NULL
        )
    """)


def update_user_activity(user_id):
    """记录用户最后活跃时间（UPSERT）"""
    conn = get_db()
    conn.execute(
        "INSERT INTO user_activity (user_id, last_active) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET last_active = ?",
        (user_id, time.time(), time.time())
    )
    conn.commit()


def get_user_activity(user_id):
    """查询用户最后活跃时间，返回时间戳或 None"""
    conn = get_db()
    row = conn.execute(
        "SELECT last_active FROM user_activity WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    return row['last_active'] if row else None
