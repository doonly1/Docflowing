CREATE_FILEBASES = """
CREATE TABLE IF NOT EXISTS filebases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    filebase_type TEXT NOT NULL DEFAULT 'upload',
    local_path TEXT DEFAULT '',
    is_synced_to_kb INTEGER NOT NULL DEFAULT 0,
    created_at REAL,
    updated_at REAL,
    status TEXT DEFAULT 'active',
    fb_agent_enabled INTEGER DEFAULT 1
)
"""

CREATE_FILEBASE_PERMISSIONS = """
CREATE TABLE IF NOT EXISTS filebase_permissions (
    filebase_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    permission_level TEXT NOT NULL,
    created_at REAL,
    PRIMARY KEY (filebase_id, user_id)
)
"""

CREATE_FILEBASE_SYNC_STATES = """
CREATE TABLE IF NOT EXISTS filebase_sync_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filebase_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(filebase_id, user_id)
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_filebase_permissions_user_id ON filebase_permissions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_filebase_permissions_filebase ON filebase_permissions(filebase_id)",
]

CREATE_INDEX_SYNC_STATES = [
    "CREATE INDEX IF NOT EXISTS idx_filebase_sync_states_filebase ON filebase_sync_states(filebase_id)",
]

CREATE_SHARED_NODES = """
CREATE TABLE IF NOT EXISTS shared_nodes (
    filebase_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    node_name TEXT DEFAULT '',
    node_addr TEXT DEFAULT '',
    permission_level TEXT NOT NULL DEFAULT 'view',
    created_at REAL,
    PRIMARY KEY (filebase_id, node_id)
)
"""


CREATE_FILEBASE_PERM_V2 = """CREATE TABLE IF NOT EXISTS filebase_perm_v2 (
    filebase_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    perm_mask INTEGER NOT NULL DEFAULT 1,
    created_at REAL,
    updated_at REAL,
    PRIMARY KEY (filebase_id, user_id)
)
"""

CREATE_FILE_LOCKS = """CREATE TABLE IF NOT EXISTS file_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filebase_id TEXT NOT NULL,
    path TEXT NOT NULL,
    locked_by TEXT NOT NULL,
    locked_at REAL NOT NULL,
    expires_at REAL,
    UNIQUE(filebase_id, path)
)
"""

CREATE_INDEX_FILE_LOCKS = [
    "CREATE INDEX IF NOT EXISTS idx_file_locks_filebase ON file_locks(filebase_id)",
]

ALL_TABLES = [
    CREATE_FILEBASES,
    CREATE_FILEBASE_PERMISSIONS,
    CREATE_FILEBASE_SYNC_STATES,
    CREATE_SHARED_NODES,
    CREATE_FILEBASE_PERM_V2,
    CREATE_FILE_LOCKS,
]

# 存储已应用的迁移版本号
MIGRATIONS_META = """
CREATE TABLE IF NOT EXISTS _migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
)
"""

# 旧迁移保留以支持现有部署
MIGRATIONS = [
    # v1: 新文件库默认不同步（旧数据库表默认值为 1）
    "ALTER TABLE filebases ALTER COLUMN is_synced_to_kb SET DEFAULT 0",
]

# 数据库迁移 SQL（按版本号递增）
DB_MIGRATIONS = {
    # 去掉 NOT NULL，兼容 3.31 以下版本的 SQLite；有 DEFAULT 新记录值仍是确定的
    1: "ALTER TABLE filebases ADD COLUMN status TEXT DEFAULT 'active'",
    2: "ALTER TABLE filebases ADD COLUMN fb_agent_enabled INTEGER DEFAULT 1",
}

CREATE_INDEX_SHARED = [
    "CREATE INDEX IF NOT EXISTS idx_shared_nodes_filebase ON shared_nodes(filebase_id)",
    "CREATE INDEX IF NOT EXISTS idx_shared_nodes_node ON shared_nodes(node_id)",
]
