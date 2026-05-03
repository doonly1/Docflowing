CREATE_KNOWLEDGE_BASES = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    kb_type TEXT NOT NULL DEFAULT 'upload',
    local_path TEXT DEFAULT '',
    created_at REAL
)
"""

CREATE_CATEGORIES = """
CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    parent_id TEXT,
    name TEXT NOT NULL,
    created_at REAL
)
"""

CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    category_id TEXT,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_size INTEGER,
    file_type TEXT,
    created_at REAL,
    updated_at REAL
)
"""

CREATE_KB_PERMISSIONS = """
CREATE TABLE IF NOT EXISTS kb_permissions (
    kb_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    permission_level TEXT NOT NULL,
    PRIMARY KEY (kb_id, user_id)
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_documents_kb_id ON documents(kb_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_category_id ON documents(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_categories_kb_id ON categories(kb_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_permissions_user_id ON kb_permissions(user_id)",
]

ALL_TABLES = [
    CREATE_KNOWLEDGE_BASES,
    CREATE_CATEGORIES,
    CREATE_DOCUMENTS,
    CREATE_KB_PERMISSIONS,
]

MIGRATIONS = [
    "ALTER TABLE knowledge_bases ADD COLUMN kb_type TEXT NOT NULL DEFAULT 'upload'",
    "ALTER TABLE knowledge_bases ADD COLUMN local_path TEXT DEFAULT ''",
]
