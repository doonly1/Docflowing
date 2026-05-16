import os
import sqlite3
import threading
import shutil

from fb.models import ALL_TABLES, CREATE_INDEXES, MIGRATIONS, CREATE_INDEX_SYNC_STATES

_local = threading.local()


def _get_data_dir():
    """获取全局数据存储目录：workspaces/data/"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'workspaces', 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _migrate_old_db():
    """从旧路径 ~/.config/DocProc/fb/ 迁移数据库到新路径"""
    old_db_path = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'fb', 'fb.db')
    new_db_dir = os.path.join(_get_data_dir(), 'fb')
    os.makedirs(new_db_dir, exist_ok=True)
    new_db_path = os.path.join(new_db_dir, 'fb.db')

    if os.path.exists(old_db_path) and not os.path.exists(new_db_path):
        try:
            shutil.copy2(old_db_path, new_db_path)
        except Exception:
            pass


def get_db_path():
    _migrate_old_db()
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


def close_db():
    if hasattr(_local, 'conn') and _local.conn is not None:
        _local.conn.close()
        _local.conn = None


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
    try:
        import json
        # 从新的数据存储路径读取
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        users_path = os.path.join(project_root, 'workspaces', 'data', 'auth', 'users.json')
        if os.path.exists(users_path):
            with open(users_path, 'r', encoding='utf-8') as f:
                users = json.load(f)
            user_info = users.get(user_id, {})
            return user_info.get('role', 'viewer')
    except Exception:
        pass
    return 'viewer'
