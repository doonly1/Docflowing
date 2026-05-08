CREATE_WIKI_INFO = """
CREATE TABLE IF NOT EXISTS wiki_info (
    usr_id TEXT NOT NULL PRIMARY KEY,
    name TEXT DEFAULT '我的知识库',
    description TEXT DEFAULT '',
    created_at REAL,
    updated_at REAL
)
"""

CREATE_WIKI_PERMISSIONS = """
CREATE TABLE IF NOT EXISTS wiki_permissions (
    usr_id TEXT NOT NULL,
    shared_user_id TEXT NOT NULL,
    permission_level TEXT NOT NULL,
    PRIMARY KEY (usr_id, shared_user_id)
)
"""

CREATE_WIKI_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
    usr_id,
    title,
    content,
    path,
    tokenize='unicode61'
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_wiki_permissions_shared_user ON wiki_permissions(shared_user_id)",
]

ALL_TABLES = [
    CREATE_WIKI_INFO,
    CREATE_WIKI_PERMISSIONS,
    CREATE_WIKI_FTS,
]
