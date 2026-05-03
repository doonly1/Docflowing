import os
import sqlite3
import threading
import yaml

from kb.models import ALL_TABLES, CREATE_INDEXES, MIGRATIONS

_local = threading.local()


def _load_kb_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'config', 'config.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return config.get('knowledge_base', {})
    except Exception:
        return {}


def get_db_path():
    kb_config = _load_kb_config()
    db_path = kb_config.get('db_path', '')
    if db_path and os.path.isabs(db_path):
        return db_path
    if db_path:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)
    data_dir = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'kb')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'knowledge.db')


def get_storage_path():
    kb_config = _load_kb_config()
    storage = kb_config.get('storage_path', '')
    if storage and os.path.isabs(storage):
        return storage
    if storage:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), storage)
    data_dir = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'kb')
    storage_dir = os.path.join(data_dir, 'storage')
    os.makedirs(storage_dir, exist_ok=True)
    return storage_dir


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


def get_visible_kb_ids(user_id, is_admin=False):
    if is_admin:
        db = get_db()
        rows = db.execute("SELECT id FROM knowledge_bases").fetchall()
        return [r['id'] for r in rows]
    db = get_db()
    ids = set()
    rows = db.execute("SELECT kb_id FROM kb_permissions WHERE user_id = ?", (user_id,)).fetchall()
    for r in rows:
        ids.add(r['kb_id'])
    rows = db.execute("SELECT id FROM knowledge_bases WHERE owner_id = ?", (user_id,)).fetchall()
    for r in rows:
        ids.add(r['id'])
    return list(ids)


def get_user_role(user_id):
    try:
        import json
        users_path = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'auth', 'users.json')
        if os.path.exists(users_path):
            with open(users_path, 'r', encoding='utf-8') as f:
                users = json.load(f)
            user_info = users.get(user_id, {})
            return user_info.get('role', 'viewer')
    except Exception:
        pass
    return 'viewer'
