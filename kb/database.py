import logging
import os
import platform
import sqlite3
import threading

from server.workspace import _get_workspace_dir
from kb.session_db import _resolve_fts_extension_dir

logger = logging.getLogger(__name__)

_FTS_SYS = platform.system()
if _FTS_SYS == 'Windows':
    _FTS_NAME = 'simple.dll'
else:
    _FTS_NAME = 'simple.so'
_FTS_EXTENSION = os.path.join(_resolve_fts_extension_dir(), _FTS_NAME)

# 启用 SQLite 扩展加载
try:
    sqlite3.enable_load_extension(True)
except AttributeError:
    pass

def _load_simple_extension(conn):
    """加载 simple 扩展到当前连接（每个 SQLite 连接都需要单独加载）"""
    if not os.path.isfile(_FTS_EXTENSION):
        logger.warning("FTS5 simple 扩展未找到: %s", _FTS_EXTENSION)
        return False
    try:
        try:
            conn.enable_load_extension(True)
        except AttributeError:
            pass
        conn.load_extension(_FTS_EXTENSION)
        return True
    except Exception as e:
        logger.warning("加载 FTS5 simple 扩展失败: %s", e)
        return False


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

# 使用 simple 分词器（需 fts_ext/simple.dll 扩展），支持中文分词
_WIKI_FTS_TOKENIZER = 'simple'



def _get_user_kb_dir(user_id: str) -> str:
    from server.workspace import _get_workspace_dir
    base = _get_workspace_dir(user_id)
    kb_dir = os.path.join(base, 'data', 'kb')
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir


def get_db_path(user_id=None):
    if user_id is None:
        return None
    kb_dir = _get_user_kb_dir(user_id)
    return os.path.join(kb_dir, 'wiki.db')


def _create_wiki_fts(conn):
    """创建 wiki_fts FTS5 虚拟表"""
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
            usr_id, title, content, path,
            tokenize='{_WIKI_FTS_TOKENIZER}'
        )
    """)


def _migrate_fts_tokenizer(conn):
    """检查并迁移 wiki_fts 到目标分词器"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='wiki_fts'"
    ).fetchone()
    if not row:
        # 表不存在，直接以目标分词器创建
        _create_wiki_fts(conn)
        return

    # 检查当前表的分词器
    current_sql = row['sql'] or ''
    if _WIKI_FTS_TOKENIZER in current_sql:
        return  # 已是目标分词器，无需迁移

    # 旧表可能是 simple 或 trigram——需要先加载 simple 扩展才能读取
    # 然后转存数据到 unicode61 的新表
    _load_simple_extension(conn)

    try:
        old_data = conn.execute(
            "SELECT usr_id, title, content, path FROM wiki_fts"
        ).fetchall()
    except Exception as e:
        logger.warning("无法读取旧 wiki_fts 数据 (tokenizer=%r): %s，直接重建空表", current_sql, e)
        old_data = []

    conn.execute("DROP TABLE IF EXISTS wiki_fts")
    _create_wiki_fts(conn)  # 用 unicode61 创建
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
    logger.info("wiki_fts tokenizer migrated to %s (from %s)",
                _WIKI_FTS_TOKENIZER, current_sql)


def init_db(conn):
    for sql in ALL_TABLES:
        conn.execute(sql)
    for sql in CREATE_INDEXES:
        conn.execute(sql)
    # 先加载扩展，再处理 FTS 表——每个连接都必须加载
    _load_simple_extension(conn)
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
