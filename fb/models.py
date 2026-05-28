CREATE_FILEBASES = """
CREATE TABLE IF NOT EXISTS filebases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    filebase_type TEXT NOT NULL DEFAULT 'upload',
    local_path TEXT DEFAULT '',
    is_synced_to_kb INTEGER NOT NULL DEFAULT 1,
    created_at REAL,
    updated_at REAL
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

ALL_TABLES = [
    CREATE_FILEBASES,
    CREATE_FILEBASE_PERMISSIONS,
    CREATE_FILEBASE_SYNC_STATES,
    CREATE_SHARED_NODES,
]

# 旧迁移保留以支持现有部署
MIGRATIONS = []

CREATE_INDEX_SHARED = [
    "CREATE INDEX IF NOT EXISTS idx_shared_nodes_filebase ON shared_nodes(filebase_id)",
    "CREATE INDEX IF NOT EXISTS idx_shared_nodes_node ON shared_nodes(node_id)",
]
