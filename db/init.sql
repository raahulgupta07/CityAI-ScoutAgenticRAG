-- ============================================================================
-- Document Intelligence Agent — Database Schema
-- ============================================================================
-- Runs on first boot via docker-entrypoint-initdb.d
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Multi-Tenant: Tenants table (public schema)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    admin_user TEXT NOT NULL DEFAULT 'admin',
    admin_pass_hash TEXT NOT NULL DEFAULT '',
    agent_name TEXT DEFAULT 'Document Agent',
    agent_role TEXT DEFAULT 'document intelligence assistant',
    agent_focus TEXT DEFAULT 'organizational documents',
    agent_personality TEXT DEFAULT 'professional, precise, proactive',
    agent_languages JSONB DEFAULT '["English"]',
    branding JSONB DEFAULT '{}',
    max_documents INTEGER DEFAULT 100,
    embed_token TEXT UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Default schema tables (also used as template for tenant schemas)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sops (
    sop_id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    category_id TEXT DEFAULT '',
    department TEXT DEFAULT '',
    system TEXT DEFAULT '',
    type TEXT DEFAULT '',
    tags JSONB DEFAULT '[]',
    pdf_path TEXT DEFAULT '',
    page_count INTEGER DEFAULT 0,
    tree_path TEXT DEFAULT '',
    doc_description TEXT DEFAULT '',
    pageindex_doc_id TEXT DEFAULT '',
    total_screenshots INTEGER DEFAULT 0,
    qa_pairs JSONB DEFAULT '[]',
    search_keywords JSONB DEFAULT '[]',
    entities JSONB DEFAULT '{}',
    summary_short TEXT DEFAULT '',
    summary_detailed TEXT DEFAULT '',
    caveats JSONB DEFAULT '[]',
    search_text TEXT DEFAULT '',
    is_enhanced BOOLEAN DEFAULT FALSE,
    indexed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT DEFAULT '',
    icon TEXT DEFAULT 'folder',
    sop_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS relationships (
    id SERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    type TEXT DEFAULT 'related',
    reason TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_id, type)
);

CREATE TABLE IF NOT EXISTS compliance (
    sop_id TEXT PRIMARY KEY,
    has_version BOOLEAN DEFAULT FALSE,
    has_author BOOLEAN DEFAULT FALSE,
    has_date BOOLEAN DEFAULT FALSE,
    has_signatures BOOLEAN DEFAULT FALSE,
    is_expired BOOLEAN DEFAULT FALSE,
    missing_sections JSONB DEFAULT '[]',
    quality_score INTEGER DEFAULT 0,
    recommendations JSONB DEFAULT '[]',
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS page_content (
    id SERIAL PRIMARY KEY,
    sop_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    text_content TEXT DEFAULT '',
    vision_content TEXT DEFAULT '',
    enhanced_content TEXT DEFAULT '',
    missing_info JSONB DEFAULT '[]',
    faqs JSONB DEFAULT '[]',
    tables JSONB DEFAULT '[]',
    image_descriptions JSONB DEFAULT '[]',
    key_info TEXT DEFAULT '',
    has_images BOOLEAN DEFAULT FALSE,
    has_tables BOOLEAN DEFAULT FALSE,
    language TEXT DEFAULT 'english',
    extraction_method TEXT DEFAULT 'text',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sop_id, page)
);

CREATE TABLE IF NOT EXISTS screenshots (
    id SERIAL PRIMARY KEY,
    sop_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    img_index INTEGER NOT NULL,
    path TEXT NOT NULL,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    UNIQUE(sop_id, page, img_index)
);

CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    sop_id TEXT,
    page INTEGER,
    chunk_index INTEGER DEFAULT 0,
    content TEXT,
    metadata JSONB DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS intent_routes (
    id SERIAL PRIMARY KEY,
    intent TEXT NOT NULL,
    keywords JSONB DEFAULT '[]',
    sop_id TEXT NOT NULL,
    pages TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    source TEXT DEFAULT 'auto',
    hit_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    question TEXT,
    sop_ids JSONB DEFAULT '[]',
    model TEXT,
    duration_s REAL,
    answer TEXT DEFAULT '',
    feedback TEXT,
    feedback_comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runtime_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT DEFAULT '',
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT DEFAULT '',
    sources JSONB DEFAULT '[]',
    image_map JSONB DEFAULT '{}',
    suggestions JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id SERIAL PRIMARY KEY,
    category TEXT,
    total INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    score REAL DEFAULT 0,
    results JSONB DEFAULT '[]',
    run_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Chat Users (public schema — for login-required chat access)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_users (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    pass_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT DEFAULT '',
    created_by TEXT DEFAULT 'self',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    UNIQUE(tenant_id, email)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sops_search ON sops USING GIN (to_tsvector('english', search_text));
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_intent_keywords ON intent_routes USING GIN (keywords);
CREATE INDEX IF NOT EXISTS idx_chat_users_tenant ON chat_users (tenant_id, status);
