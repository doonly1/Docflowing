import logging
import os
import sqlite3
import threading

from server.workspace import _get_workspace_dir

logger = logging.getLogger(__name__)

# 注：旧版本在模块导入时还会加载 kb/fts_ext/simple 外部扩展（simple.dll/.so）。
# 该扩展在当前 SQLite（>=3.49，随 Python 3.12+ 分发）下任何 FTS 写入都会触发
# 原生 access violation（进程级崩溃，无法 try/except），曾导致「同步到知识库」
# 首次写入即闪退、应用启动即崩。本模块已彻底移除扩展加载，FTS 一律使用
# SQLite 内建 trigram 分词器（见 _WIKI_FTS_TOKENIZER）。

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

# 使用内建 trigram 分词器（sqlite>=3.34）：支持中文子串检索且无需外部扩展。
# 背景：旧版依赖 fts_ext/simple.dll 自定义扩展，该扩展在当前 sqlite（3.49）
# 环境下任何 FTS 写入都会触发原生 access violation（段错误，无法 try/except），
# 曾导致「同步到知识库」首次写入即闪退、应用启动即崩。改为内建分词器后，
# 查询词长度 <3 字符时 trigram 无法命中（返回 0 行），由上层搜索的 LIKE 兜底处理。
_WIKI_FTS_TOKENIZER = 'trigram'



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
    """检查 wiki_fts 是否使用目标分词器，必要时重建表。

    旧版本依赖 kb/fts_ext/simple 自定义扩展（tokenize='simple'），该扩展在当前
    SQLite（3.49，随 Python 3.12+ 分发）下任何 FTS 写入都会触发原生 access
    violation（进程级崩溃，无法被 Python try/except 捕获），曾导致「同步到知识库」
    首次写入即闪退、应用启动即崩。

    迁移策略：**不再加载外部扩展**。读取 FTS 表原始列内容不需要分词器，是安全的；
    即使读取失败也按空表重建（写入路径从此只走内建 trigram，彻底绕开崩溃点）。
    """
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

    # 旧表（tokenize='simple'）：安全读取原始内容列后重建为 trigram
    old_data = []
    try:
        old_data = conn.execute(
            "SELECT usr_id, title, content, path FROM wiki_fts"
        ).fetchall()
    except Exception as e:
        logger.warning("无法读取旧 wiki_fts 数据 (tokenizer=%r): %s，按空表重建",
                       current_sql, e)

    conn.execute("DROP TABLE IF EXISTS wiki_fts")
    _create_wiki_fts(conn)  # 用内建 trigram 分词器重建
    reindexed = 0
    for old in old_data:
        try:
            conn.execute(
                "INSERT INTO wiki_fts (usr_id, title, content, path) "
                "VALUES (?, ?, ?, ?)",
                (old['usr_id'], old['title'], old['content'], old['path'])
            )
            reindexed += 1
        except Exception:
            pass
    conn.commit()
    logger.info("wiki_fts tokenizer migrated to %s (from %s), reindexed %d rows",
                _WIKI_FTS_TOKENIZER, current_sql, reindexed)


def init_db(conn):
    for sql in ALL_TABLES:
        conn.execute(sql)
    for sql in CREATE_INDEXES:
        conn.execute(sql)
    # FTS 统一使用内建 trigram 分词器，无需加载任何外部扩展
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
