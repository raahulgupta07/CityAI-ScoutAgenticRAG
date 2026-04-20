"""
PostgreSQL + PgVector database for Document Agent.
Replaces SQLite. Single DB for app data + vector embeddings + Agno state.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import logging

logger = logging.getLogger(__name__)

from backend.core.config import PROJECT_ROOT, DATABASE_URL

# File storage paths (still on disk)
DATA_DIR = Path("/data") if Path("/data").exists() else PROJECT_ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
for d in [DATA_DIR, PDF_DIR, SCREENSHOT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def resolve_pdf_path(stored_path: str) -> Optional[str]:
    """Resolve a PDF path — handles host paths, Docker mounts, and uploads.
    Validates resolved path is within allowed directories (prevents path traversal)."""
    if not stored_path:
        return None
    ALLOWED_DIRS = [str(DATA_DIR), "/app/sop_data", "/data"]

    p = Path(stored_path)
    if p.exists():
        resolved = str(p.resolve())
        if any(resolved.startswith(d) for d in ALLOWED_DIRS):
            return resolved
    # Try Docker mount: /app/sop_data/{relative path after Data/}
    if "Data/" in stored_path:
        rel = stored_path.split("Data/", 1)[1]
        docker_path = Path(f"/app/sop_data/{rel}")
        if docker_path.exists():
            return str(docker_path)
    # Try uploads dir
    upload_path = DATA_DIR / "uploads" / p.name
    if upload_path.exists():
        resolved = str(upload_path.resolve())
        if any(resolved.startswith(d) for d in ALLOWED_DIRS):
            return resolved
    return None

# Parse DATABASE_URL for psycopg (needs postgresql:// not postgresql+psycopg://)
_pg_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")

# ── Connection Pool ──────────────────────────────────────────────────────────
# psycopg_pool.ConnectionPool: when conn.close() is called on a pooled
# connection it is returned to the pool, not destroyed.

_pool: ConnectionPool | None = None


def _reset_connection(conn):
    """Reset connection state when returned to pool.

    Clears search_path back to default so the next consumer
    doesn't inherit a tenant schema from the previous user.
    """
    conn.rollback()  # Clear any pending transaction
    conn.execute("RESET ALL")
    conn.commit()


def _get_pool() -> ConnectionPool:
    """Get or lazily create the connection pool (handles startup race)."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_pg_url,
            min_size=2,
            max_size=10,
            timeout=30,
            kwargs={"row_factory": dict_row, "autocommit": False},
            reset=_reset_connection,
            open=True,
        )
    return _pool


def pool_health_check() -> dict:
    """Check pool health — suitable for /health endpoint."""
    try:
        pool = _get_pool()
        stats = pool.get_stats()
        # Quick connectivity test
        conn = pool.getconn()
        try:
            conn.execute("SELECT 1")
            conn.rollback()  # Clear the implicit transaction
        finally:
            conn.close()  # Returns to pool
        return {
            "status": "healthy",
            "pool_size": stats.get("pool_size", 0),
            "pool_available": stats.get("pool_available", 0),
            "requests_waiting": stats.get("requests_waiting", 0),
            "pool_min": 2,
            "pool_max": 10,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def _sanitize_tenant_id(tenant_id: str) -> str:
    """Sanitize tenant_id for use in SQL identifiers and file paths."""
    import re
    safe = tenant_id.replace('"', '').replace("'", '').replace(';', '')
    safe = safe.replace('..', '').replace('/', '').replace('\\', '')
    if not re.match(r'^[\w\-]+$', safe):
        raise ValueError(f"Invalid tenant_id: {tenant_id}")
    return safe


class _PooledConnection:
    """Wrapper that returns connection to pool on close() instead of destroying it."""
    __slots__ = ('_conn', '_pool')

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def fetchone(self):
        return self._conn.fetchone()

    def fetchall(self):
        return self._conn.fetchall()

    def close(self):
        """Return connection to pool instead of destroying it."""
        if self._conn is not None:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
            self._conn = None

    @property
    def closed(self):
        return self._conn is None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_db(tenant_id: str = None):
    """Get a PostgreSQL connection from the pool.

    If tenant_id is provided, sets search_path to tenant schema.
    When conn.close() is called the connection returns to the pool.
    """
    pool = _get_pool()
    conn = pool.getconn()
    if tenant_id:
        safe_id = _sanitize_tenant_id(tenant_id)
        conn.execute(f'SET search_path TO "{safe_id}", public')
    return _PooledConnection(conn, pool)


# ── Tenant Management ────────────────────────────────────────────────────────

# SQL template for creating all tables in a tenant schema
_TENANT_TABLES_SQL = None

def _get_tenant_tables_sql() -> str:
    """Read the table creation SQL from init.sql (after the tenants table)."""
    global _TENANT_TABLES_SQL
    if _TENANT_TABLES_SQL is None:
        # Extract CREATE TABLE statements from init_db (reuse existing code)
        # We'll call init_db_for_schema instead
        _TENANT_TABLES_SQL = "loaded"
    return _TENANT_TABLES_SQL


def create_tenant_schema(tenant_id: str):
    """Create a new PostgreSQL schema with all required tables for a tenant."""
    safe_id = _sanitize_tenant_id(tenant_id)
    conn = get_db()  # start in public, then switch
    try:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{safe_id}"')
        conn.commit()

        # Set search path to new schema and create all tables
        conn.execute(f'SET search_path TO "{safe_id}", public')
        _create_tables_in_current_schema(conn)
        conn.commit()
    finally:
        conn.close()

    # Create data directories
    tenant_data = DATA_DIR / "tenants" / tenant_id
    for subdir in ["uploads", "pdfs", "screenshots", "previews"]:
        (tenant_data / subdir).mkdir(parents=True, exist_ok=True)

    logger.info(f"Created tenant schema: {tenant_id}")


def _create_tables_in_current_schema(conn):
    """Create all document tables in the current schema (used by both init_db and create_tenant_schema)."""
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sops (
            sop_id TEXT PRIMARY KEY, title TEXT, description TEXT,
            category_id TEXT DEFAULT '', department TEXT DEFAULT '', system TEXT DEFAULT '',
            type TEXT DEFAULT '', tags JSONB DEFAULT '[]', pdf_path TEXT DEFAULT '',
            page_count INTEGER DEFAULT 0, tree_path TEXT DEFAULT '',
            doc_description TEXT DEFAULT '', pageindex_doc_id TEXT DEFAULT '',
            total_screenshots INTEGER DEFAULT 0, qa_pairs JSONB DEFAULT '[]',
            search_keywords JSONB DEFAULT '[]', entities JSONB DEFAULT '{}',
            summary_short TEXT DEFAULT '', summary_detailed TEXT DEFAULT '',
            caveats JSONB DEFAULT '[]', search_text TEXT DEFAULT '',
            is_enhanced BOOLEAN DEFAULT FALSE, indexed_at TIMESTAMPTZ,
            standardized_json JSONB, sop_score INTEGER DEFAULT 0, sop_gaps JSONB,
            standardized_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY, name TEXT, parent_id TEXT DEFAULT '',
            icon TEXT DEFAULT 'folder', sop_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id SERIAL PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
            type TEXT DEFAULT 'related', reason TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(source_id, target_id, type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compliance (
            sop_id TEXT PRIMARY KEY, has_version BOOLEAN DEFAULT FALSE,
            has_author BOOLEAN DEFAULT FALSE, has_date BOOLEAN DEFAULT FALSE,
            has_signatures BOOLEAN DEFAULT FALSE, is_expired BOOLEAN DEFAULT FALSE,
            missing_sections JSONB DEFAULT '[]', quality_score INTEGER DEFAULT 0,
            recommendations JSONB DEFAULT '[]', checked_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS page_content (
            id SERIAL PRIMARY KEY, sop_id TEXT NOT NULL, page INTEGER NOT NULL,
            text_content TEXT DEFAULT '', vision_content TEXT DEFAULT '',
            enhanced_content TEXT DEFAULT '', tables JSONB DEFAULT '[]',
            image_descriptions JSONB DEFAULT '[]', key_info TEXT DEFAULT '',
            missing_info JSONB DEFAULT '[]', faqs JSONB DEFAULT '[]',
            has_images BOOLEAN DEFAULT FALSE, has_tables BOOLEAN DEFAULT FALSE,
            language TEXT DEFAULT 'en', extraction_method TEXT DEFAULT 'text',
            is_enhanced BOOLEAN DEFAULT FALSE, UNIQUE(sop_id, page)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id SERIAL PRIMARY KEY, sop_id TEXT NOT NULL, page INTEGER NOT NULL,
            img_index INTEGER NOT NULL, path TEXT NOT NULL,
            width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
            UNIQUE(sop_id, page, img_index)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id SERIAL PRIMARY KEY, sop_id TEXT, page INTEGER,
            chunk_index INTEGER DEFAULT 0, content TEXT DEFAULT '',
            metadata JSONB DEFAULT '{}', embedding vector(1536)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intent_routes (
            id SERIAL PRIMARY KEY, intent TEXT NOT NULL, keywords JSONB DEFAULT '[]',
            sop_id TEXT NOT NULL, pages TEXT DEFAULT '', reason TEXT DEFAULT '',
            source TEXT DEFAULT 'manual', hit_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id SERIAL PRIMARY KEY, question TEXT, sop_ids JSONB DEFAULT '[]',
            model TEXT, duration_s REAL, answer TEXT DEFAULT '',
            feedback TEXT, feedback_comment TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runtime_config (
            key TEXT PRIMARY KEY, value JSONB NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, title TEXT DEFAULT '',
            message_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT DEFAULT '',
            sources JSONB DEFAULT '[]', image_map JSONB DEFAULT '{}',
            suggestions JSONB DEFAULT '[]', created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_runs (
            id SERIAL PRIMARY KEY, category TEXT, total INTEGER DEFAULT 0,
            passed INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
            score REAL DEFAULT 0, results JSONB DEFAULT '[]',
            run_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wiki_pages (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT DEFAULT '',
            content TEXT DEFAULT '',
            sources JSONB DEFAULT '[]',
            related JSONB DEFAULT '[]',
            contradictions JSONB DEFAULT '[]',
            hit_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    # Migrate: add quality_score column to query_log if missing
    try:
        conn.execute("ALTER TABLE query_log ADD COLUMN IF NOT EXISTS quality_score INTEGER DEFAULT NULL")
    except Exception:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sops_search ON sops USING GIN (to_tsvector('english', search_text))")
    except Exception:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops)")
    except Exception:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wiki_search ON wiki_pages USING GIN (to_tsvector('english', content))")
    except Exception:
        pass
    # Migrate: add versioning columns to sops
    try:
        conn.execute("ALTER TABLE sops ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE sops ADD COLUMN IF NOT EXISTS previous_version_id TEXT DEFAULT NULL")
    except Exception:
        pass
    # Migrate: add pinned column to sops
    try:
        conn.execute("ALTER TABLE sops ADD COLUMN IF NOT EXISTS pinned BOOLEAN DEFAULT FALSE")
    except Exception:
        pass


def _ensure_monitoring_tables(conn):
    """Create monitoring tables in public schema (cost tracking + audit trail)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            model TEXT DEFAULT '',
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT,
            user_id TEXT DEFAULT 'system',
            action TEXT NOT NULL,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            details TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            category TEXT DEFAULT '',
            title TEXT NOT NULL,
            message TEXT DEFAULT '',
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_log (tenant_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log (tenant_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_unread ON alerts (is_read, created_at DESC)")
    except Exception:
        pass
    conn.commit()


def log_usage(tenant_id: str, operation: str, model: str = "", input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0, duration_ms: int = 0, metadata: dict = None):
    """Log LLM/API usage for cost tracking."""
    try:
        conn = get_db()  # public schema
        try:
            conn.execute(
                "INSERT INTO usage_log (tenant_id, operation, model, input_tokens, output_tokens, cost_usd, duration_ms, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (tenant_id, operation, model, input_tokens, output_tokens, cost_usd, duration_ms, json.dumps(metadata or {}))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def log_audit(tenant_id: str, action: str, user_id: str = "system", resource_type: str = "", resource_id: str = "", details: str = "", ip_address: str = ""):
    """Log an audit event."""
    try:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO audit_log (tenant_id, user_id, action, resource_type, resource_id, details, ip_address) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (tenant_id, user_id, action, resource_type, resource_id, details, ip_address)
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def create_alert(title: str, message: str = "", severity: str = "info", category: str = "", tenant_id: str = None):
    """Create a system alert."""
    try:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO alerts (tenant_id, severity, category, title, message) VALUES (%s,%s,%s,%s,%s)",
                (tenant_id, severity, category, title, message)
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_usage_stats(tenant_id: str = None, days: int = 30) -> dict:
    """Get usage statistics, optionally filtered by tenant."""
    conn = get_db()
    try:
        where = f"WHERE created_at > NOW() - INTERVAL '{int(days)} days'"
        params = []
        if tenant_id:
            where += " AND tenant_id = %s"
            params.append(tenant_id)

        totals = conn.execute(f"""
            SELECT
                COUNT(*) as total_ops,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(cost_usd), 0) as total_cost,
                COALESCE(AVG(duration_ms), 0) as avg_duration
            FROM usage_log {where}
        """, params).fetchone()

        by_operation = conn.execute(f"""
            SELECT operation, COUNT(*) as count, COALESCE(SUM(cost_usd), 0) as cost,
                   COALESCE(AVG(duration_ms), 0) as avg_ms
            FROM usage_log {where}
            GROUP BY operation ORDER BY cost DESC
        """, params).fetchall()

        by_tenant = conn.execute(f"""
            SELECT tenant_id, COUNT(*) as ops, COALESCE(SUM(cost_usd), 0) as cost
            FROM usage_log {where.replace('AND tenant_id = %s', '') if tenant_id else where}
            GROUP BY tenant_id ORDER BY cost DESC LIMIT 20
        """, [] if tenant_id else []).fetchall()

        daily = conn.execute(f"""
            SELECT DATE(created_at) as day, COUNT(*) as ops, COALESCE(SUM(cost_usd), 0) as cost
            FROM usage_log {where}
            GROUP BY DATE(created_at) ORDER BY day DESC LIMIT 30
        """, params).fetchall()

        return {
            "total_operations": totals["total_ops"],
            "total_input_tokens": totals["total_input_tokens"],
            "total_output_tokens": totals["total_output_tokens"],
            "total_cost_usd": round(float(totals["total_cost"]), 4),
            "avg_duration_ms": round(float(totals["avg_duration"])),
            "by_operation": [dict(r) for r in by_operation],
            "by_tenant": [dict(r) for r in by_tenant],
            "daily": [{"day": str(r["day"]), "ops": r["ops"], "cost": round(float(r["cost"]), 4)} for r in daily],
        }
    finally:
        conn.close()


def get_audit_log(tenant_id: str = None, limit: int = 100) -> list:
    """Get audit log entries."""
    conn = get_db()
    try:
        if tenant_id:
            rows = conn.execute("SELECT * FROM audit_log WHERE tenant_id = %s ORDER BY created_at DESC LIMIT %s", (tenant_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_alerts(unread_only: bool = False, limit: int = 50) -> list:
    """Get system alerts."""
    conn = get_db()
    try:
        where = "WHERE is_read = FALSE" if unread_only else ""
        rows = conn.execute(f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_tenant(tenant_id: str) -> dict | None:
    """Get tenant info from public.tenants table."""
    conn = get_db()  # always public schema
    try:
        row = conn.execute("SELECT * FROM tenants WHERE id = %s AND is_active = TRUE", (tenant_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_tenants() -> list:
    """List all tenants."""
    conn = get_db()  # always public schema
    try:
        rows = conn.execute("SELECT * FROM tenants ORDER BY created_at DESC").fetchall()
        return [_parse_row(dict(r)) for r in rows]
    finally:
        conn.close()


def _hash_password(password: str) -> str:
    """Hash password with bcrypt (salted). Falls back to SHA256 if bcrypt unavailable."""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash (supports both bcrypt and SHA256)."""
    try:
        import bcrypt
        if stored_hash.startswith("$2"):  # bcrypt hash
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except ImportError:
        pass
    # Fallback: SHA256 comparison (constant-time for old hashes)
    import hashlib, hmac
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored_hash)

def create_tenant(tenant_id: str, name: str, admin_user: str, admin_pass: str, **kwargs) -> dict:
    """Create a new tenant: row in tenants table + schema + data dirs."""
    import secrets
    pass_hash = _hash_password(admin_pass)
    embed_token = secrets.token_urlsafe(24)  # Random URL-safe token for public chat

    conn = get_db()  # always public schema
    try:
        # Add embed_token column if not exists (migration for existing DBs)
        try:
            conn.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS embed_token TEXT UNIQUE")
        except Exception:
            pass
        conn.execute("""
            INSERT INTO tenants (id, slug, name, admin_user, admin_pass_hash,
                agent_name, agent_role, agent_focus, agent_personality, agent_languages, branding, embed_token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            tenant_id, tenant_id, name, admin_user, pass_hash,
            kwargs.get("agent_name", "Document Agent"),
            kwargs.get("agent_role", "document intelligence assistant"),
            kwargs.get("agent_focus", "organizational documents"),
            kwargs.get("agent_personality", "professional, precise"),
            json.dumps(kwargs.get("agent_languages", ["English"])),
            json.dumps(kwargs.get("branding", {})),
            embed_token,
        ))
        conn.commit()
    finally:
        conn.close()

    create_tenant_schema(tenant_id)
    return {"id": tenant_id, "name": name, "embed_token": embed_token, "status": "created"}


def get_tenant_by_embed_token(token: str) -> dict | None:
    """Find tenant by their embed token (for public chat URL validation)."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM tenants WHERE embed_token = %s AND is_active = TRUE", (token,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_tenant(tenant_id: str):
    """Delete tenant: drop schema + delete row + remove files."""
    import shutil
    safe_id = _sanitize_tenant_id(tenant_id)
    conn = get_db()  # always public schema
    try:
        conn.execute(f'DROP SCHEMA IF EXISTS "{safe_id}" CASCADE')
        conn.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
        conn.commit()
    finally:
        conn.close()

    tenant_data = DATA_DIR / "tenants" / tenant_id
    if tenant_data.exists():
        shutil.rmtree(tenant_data)

    logger.info(f"Deleted tenant: {tenant_id}")


def get_tenant_data_dir(tenant_id: str) -> Path:
    """Get the data directory for a tenant."""
    return DATA_DIR / "tenants" / tenant_id


def get_tenant_screenshot_dir(tenant_id: str) -> Path:
    """Get tenant-scoped screenshot directory."""
    d = DATA_DIR / "tenants" / tenant_id / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_tenant_pdf_dir(tenant_id: str) -> Path:
    """Get tenant-scoped PDF directory."""
    d = DATA_DIR / "tenants" / tenant_id / "pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def init_db():
    """Create tables in public schema + tenants table + ensure all tenant schemas are up to date."""
    conn = get_db()  # public schema
    try:
        # Create tenants table in public schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                admin_user TEXT NOT NULL DEFAULT 'admin', admin_pass_hash TEXT NOT NULL DEFAULT '',
                agent_name TEXT DEFAULT 'Document Agent',
                agent_role TEXT DEFAULT 'document intelligence assistant',
                agent_focus TEXT DEFAULT 'organizational documents',
                agent_personality TEXT DEFAULT 'professional, precise, proactive',
                agent_languages JSONB DEFAULT '["English"]',
                branding JSONB DEFAULT '{}', max_documents INTEGER DEFAULT 100,
                document_mode TEXT DEFAULT 'general',
                agent_tone TEXT DEFAULT 'professional',
                agent_style TEXT DEFAULT 'step-by-step',
                agent_temperature REAL DEFAULT 0.3,
                agent_system_prompt TEXT DEFAULT '',
                sop_template TEXT DEFAULT 'auto',
                embed_enabled BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Migrate: add columns that may not exist on older DBs
        for col, default in [
            ("document_mode", "'general'"), ("agent_tone", "'professional'"),
            ("agent_style", "'step-by-step'"), ("agent_temperature", "0.3"),
            ("agent_system_prompt", "''"), ("sop_template", "'auto'"),
            ("embed_enabled", "FALSE"),
            ("escalation_config", "'{}'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE tenants ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT {default}")
            except Exception:
                pass
        conn.commit()
        # Create all document tables in public schema (backward compatible)
        _create_tables_in_current_schema(conn)
        conn.commit()
        # Create monitoring tables (public schema)
        _ensure_monitoring_tables(conn)
    finally:
        conn.close()

    # Ensure all existing tenant schemas have up-to-date tables
    try:
        tenants = list_tenants()
        for t in tenants:
            try:
                create_tenant_schema(t["id"])  # idempotent — uses IF NOT EXISTS
            except Exception as e:
                logger.debug(f"Tenant schema migration for {t['id']}: {e}")
    except Exception:
        pass  # tenants table may not exist yet on first run



# ── Runtime Config ───────────────────────────────────────────────────────────

def get_runtime_config(key: str, tenant_id: str = None) -> dict | None:
    conn = get_db(tenant_id)
    try:
        row = conn.execute("SELECT value FROM runtime_config WHERE key = %s", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_runtime_config(key: str, value: dict, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO runtime_config (key, value, updated_at) VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(value)))
        conn.commit()
    finally:
        conn.close()


# ── SOP CRUD ─────────────────────────────────────────────────────────────────

def upsert_sop(sop: dict, tenant_id: str = None):
    # Build search_text
    search_text = " ".join(filter(None, [
        sop.get("sop_id", ""), sop.get("title", ""), sop.get("description", ""),
        sop.get("doc_description", ""), sop.get("department", ""), sop.get("system", ""),
        sop.get("summary_short", ""),
        " ".join(sop.get("tags", []) if isinstance(sop.get("tags"), list) else []),
        " ".join(sop.get("search_keywords", []) if isinstance(sop.get("search_keywords"), list) else []),
        " ".join(q if isinstance(q, str) else (q.get("q","")+" "+q.get("a","")) if isinstance(q, dict) else str(q) for q in (sop.get("qa_pairs", []) if isinstance(sop.get("qa_pairs"), list) else [])),
        json.dumps(sop.get("entities", {}) if isinstance(sop.get("entities"), dict) else {}),
    ]))

    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO sops (sop_id, title, description, category_id, department, system, type, tags,
                pdf_path, page_count, doc_description, total_screenshots, is_enhanced,
                qa_pairs, search_keywords, entities, summary_short, summary_detailed, caveats, search_text, indexed_at)
            VALUES (%(sop_id)s, %(title)s, %(description)s, %(category_id)s, %(department)s, %(system)s,
                %(type)s, %(tags)s, %(pdf_path)s, %(page_count)s, %(doc_description)s,
                %(total_screenshots)s, %(is_enhanced)s, %(qa_pairs)s, %(search_keywords)s,
                %(entities)s, %(summary_short)s, %(summary_detailed)s, %(caveats)s, %(search_text)s, %(indexed_at)s)
            ON CONFLICT (sop_id) DO UPDATE SET
                title=EXCLUDED.title, description=EXCLUDED.description, category_id=EXCLUDED.category_id,
                department=EXCLUDED.department, system=EXCLUDED.system, type=EXCLUDED.type, tags=EXCLUDED.tags,
                pdf_path=EXCLUDED.pdf_path, page_count=EXCLUDED.page_count,
                doc_description=EXCLUDED.doc_description,
                total_screenshots=EXCLUDED.total_screenshots, is_enhanced=EXCLUDED.is_enhanced,
                qa_pairs=EXCLUDED.qa_pairs, search_keywords=EXCLUDED.search_keywords, entities=EXCLUDED.entities,
                summary_short=EXCLUDED.summary_short, summary_detailed=EXCLUDED.summary_detailed,
                caveats=EXCLUDED.caveats,
                search_text=EXCLUDED.search_text, indexed_at=EXCLUDED.indexed_at
        """, {
            "sop_id": sop.get("sop_id", ""),
            "title": sop.get("title", ""),
            "description": sop.get("description", ""),
            "category_id": sop.get("category_id", ""),
            "department": sop.get("department", ""),
            "system": sop.get("system", ""),
            "type": sop.get("type", ""),
            "tags": json.dumps(sop.get("tags", []) if isinstance(sop.get("tags"), list) else []),
            "pdf_path": sop.get("pdf_path", ""),
            "page_count": sop.get("page_count", 0),
            "doc_description": sop.get("doc_description", ""),
            "total_screenshots": sop.get("total_screenshots", 0),
            "is_enhanced": sop.get("is_enhanced", False),
            "qa_pairs": json.dumps(sop.get("qa_pairs", []) if isinstance(sop.get("qa_pairs"), list) else []),
            "search_keywords": json.dumps(sop.get("search_keywords", []) if isinstance(sop.get("search_keywords"), list) else []),
            "entities": json.dumps(sop.get("entities", {}) if isinstance(sop.get("entities"), dict) else {}),
            "summary_short": sop.get("summary_short", ""),
            "summary_detailed": sop.get("summary_detailed", ""),
            "caveats": json.dumps(sop.get("caveats", []) if isinstance(sop.get("caveats"), list) else []),
            "search_text": search_text,
            "indexed_at": sop.get("indexed_at"),
        })
        conn.commit()
    finally:
        conn.close()


def _parse_row(d: dict) -> dict:
    """Parse JSONB fields from Postgres."""
    for field in ["tags", "qa_pairs", "search_keywords", "caveats"]:
        val = d.get(field)
        if isinstance(val, str):
            try:
                d[field] = json.loads(val)
            except Exception:
                d[field] = []
    for field in ["entities"]:
        val = d.get(field)
        if isinstance(val, str):
            try:
                d[field] = json.loads(val)
            except Exception:
                d[field] = {}
    return d


def get_sop(sop_id: str, tenant_id: str = None) -> Optional[dict]:
    conn = get_db(tenant_id)
    try:
        # Try exact match first (fastest)
        row = conn.execute("SELECT * FROM sops WHERE sop_id = %s", (sop_id,)).fetchone()
        if not row:
            # Case-insensitive fallback
            row = conn.execute("SELECT * FROM sops WHERE LOWER(sop_id) = LOWER(%s)", (sop_id,)).fetchone()
        if not row:
            # O/0 normalization (LLM often confuses letter O and digit 0)
            normalized = sop_id.lower().replace('o', '0')
            row = conn.execute(
                "SELECT * FROM sops WHERE TRANSLATE(LOWER(sop_id), 'o', '0') = %s LIMIT 1",
                (normalized,)
            ).fetchone()
    finally:
        conn.close()
    return _parse_row(dict(row)) if row else None


def list_sops(department: Optional[str] = None, category: Optional[str] = None, search: Optional[str] = None, tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        query = "SELECT * FROM sops WHERE 1=1"
        params: list = []

        if department:
            query += " AND department ILIKE %s"
            params.append(f"%{department}%")
        if category:
            query += " AND category_id ILIKE %s"
            params.append(f"%{category}%")
        if search:
            query += " AND (search_text ILIKE %s OR sop_id ILIKE %s OR title ILIKE %s)"
            params.extend([f"%{search}%"] * 3)

        query += " ORDER BY sop_id"
        rows = conn.execute(query, params).fetchall()
        return [_parse_row(dict(r)) for r in rows]
    finally:
        conn.close()


def delete_sop(sop_id: str, tenant_id: str = None):
    """Delete document and ALL related data: pages, embeddings, screenshots, intents, compliance."""
    conn = get_db(tenant_id)
    try:
        conn.execute("DELETE FROM page_content WHERE sop_id = %s", (sop_id,))
        conn.execute("DELETE FROM screenshots WHERE sop_id = %s", (sop_id,))
        conn.execute("DELETE FROM embeddings WHERE sop_id = %s", (sop_id,))
        conn.execute("DELETE FROM intent_routes WHERE sop_id = %s", (sop_id,))
        conn.execute("DELETE FROM compliance WHERE sop_id = %s", (sop_id,))
        conn.execute("DELETE FROM relationships WHERE source_id = %s OR target_id = %s", (sop_id, sop_id))
        conn.execute("DELETE FROM sops WHERE sop_id = %s", (sop_id,))
        conn.commit()
    finally:
        conn.close()


def get_stats(tenant_id: str = None) -> dict:
    conn = get_db(tenant_id)
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM sops").fetchone()["c"]
        pages = conn.execute("SELECT COALESCE(SUM(page_count), 0) AS c FROM sops").fetchone()["c"]
        screenshots = conn.execute("SELECT COUNT(*) AS c FROM screenshots").fetchone()["c"]
        depts = conn.execute("SELECT COUNT(DISTINCT department) AS c FROM sops").fetchone()["c"]
        categories = conn.execute("SELECT COUNT(DISTINCT category_id) AS c FROM sops WHERE category_id != ''").fetchone()["c"]
        queries = conn.execute("SELECT COUNT(*) AS c FROM query_log").fetchone()["c"]
        embeddings = conn.execute("SELECT COUNT(*) AS c FROM embeddings").fetchone()["c"]
        thumbs_up = conn.execute("SELECT COUNT(*) AS c FROM query_log WHERE feedback = 'up'").fetchone()["c"]
        thumbs_down = conn.execute("SELECT COUNT(*) AS c FROM query_log WHERE feedback = 'down'").fetchone()["c"]
    finally:
        conn.close()
    return {
        "total_indexed": total,
        "total_pages": pages,
        "pages_with_images": screenshots,
        "departments": depts,
        "categories": categories,
        "total_queries": queries,
        "total_embeddings": embeddings,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "errors": 0,
    }


def get_departments(tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("SELECT DISTINCT department FROM sops WHERE department != '' ORDER BY department").fetchall()
        return [r["department"] for r in rows]
    finally:
        conn.close()


def get_categories(tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Screenshots ──────────────────────────────────────────────────────────────

def upsert_screenshot(sop_id: str, page: int, img_index: int, path: str, width: int, height: int, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO screenshots (sop_id, page, img_index, path, width, height)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (sop_id, page, img_index) DO UPDATE SET path=EXCLUDED.path, width=EXCLUDED.width, height=EXCLUDED.height
        """, (sop_id, page, img_index, path, width, height))
        conn.commit()
    finally:
        conn.close()


def get_screenshots(sop_id: str, tenant_id: str = None) -> dict:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("SELECT * FROM screenshots WHERE sop_id = %s ORDER BY page, img_index", (sop_id,)).fetchall()
    finally:
        conn.close()
    result: dict = {}
    for r in rows:
        page_str = str(r["page"])
        if page_str not in result:
            result[page_str] = []
        url = f"/api/t/{tenant_id}/images/{sop_id}/{r['path']}"
        result[page_str].append({
            "index": r["img_index"],
            "path": r["path"],
            "url": url,
            "width": r["width"],
            "height": r["height"],
        })
    return result


# ── Query Log ────────────────────────────────────────────────────────────────

def log_query(question: str, sop_ids: list, model: str, duration: float, answer: str = "", tenant_id: str = None, quality_score: int = None) -> int:
    conn = get_db(tenant_id)
    try:
        row = conn.execute(
            "INSERT INTO query_log (question, sop_ids, model, duration_s, answer, quality_score) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (question, json.dumps(sop_ids), model, round(duration, 2), answer[:2000] if answer else "", quality_score)
        ).fetchone()
        conn.commit()
        return row["id"] if row else 0
    finally:
        conn.close()


def update_query_feedback(query_id: int, feedback: str, comment: str = "", tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute(
            "UPDATE query_log SET feedback = %s, feedback_comment = %s WHERE id = %s",
            (feedback, comment, query_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_query_by_id(query_id: int, tenant_id: str = None) -> Optional[dict]:
    """Fetch a single query_log row by ID."""
    conn = get_db(tenant_id)
    try:
        row = conn.execute("SELECT * FROM query_log WHERE id = %s", (query_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    d = dict(row)
    d["sources"] = d.pop("sop_ids", [])
    if isinstance(d["sources"], str):
        try: d["sources"] = json.loads(d["sources"])
        except: d["sources"] = []
    return d


def get_query_logs(limit: int = 50, tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("SELECT * FROM query_log ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["sources"] = d.pop("sop_ids", [])
        if isinstance(d["sources"], str):
            d["sources"] = json.loads(d["sources"])
        # Convert datetime to string
        if d.get("created_at"):
            d["timestamp"] = d["created_at"].isoformat()
        result.append(d)
    return result


# ── Conversations ────────────────────────────────────────────────────────────

def create_conversation(conv_id: str, title: str = "", tenant_id: str = None) -> dict:
    conn = get_db(tenant_id)
    try:
        conn.execute(
            "INSERT INTO conversations (id, title) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (conv_id, title)
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": conv_id, "title": title}


def list_conversations(limit: int = 50, tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT %s", (limit,)
        ).fetchall()
        return [_parse_row(dict(r)) for r in rows]
    finally:
        conn.close()


def get_conversation_messages(conv_id: str, tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = %s ORDER BY created_at ASC", (conv_id,)
        ).fetchall()
        return [_parse_row(dict(r)) for r in rows]
    finally:
        conn.close()


def add_conversation_message(conv_id: str, role: str, content: str, sources: list = None, image_map: dict = None, suggestions: list = None, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute(
            """INSERT INTO conversation_messages (conversation_id, role, content, sources, image_map, suggestions)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (conv_id, role, content, json.dumps(sources or []), json.dumps(image_map or {}), json.dumps(suggestions or []))
        )
        conn.execute(
            "UPDATE conversations SET message_count = message_count + 1, updated_at = NOW() WHERE id = %s", (conv_id,)
        )
        conn.commit()
    finally:
        conn.close()


def delete_conversation(conv_id: str, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
        conn.commit()
    finally:
        conn.close()


def update_conversation_title(conv_id: str, title: str, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("UPDATE conversations SET title = %s WHERE id = %s", (title, conv_id))
        conn.commit()
    finally:
        conn.close()


# ── Eval Runs ────────────────────────────────────────────────────────────────

def save_eval_run(category: str, total: int, passed: int, failed: int, score: float, results: list, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute(
            "INSERT INTO eval_runs (category, total, passed, failed, score, results) VALUES (%s, %s, %s, %s, %s, %s)",
            (category or "all", total, passed, failed, round(score, 2), json.dumps(results))
        )
        conn.commit()
    finally:
        conn.close()


def get_eval_history(limit: int = 20, tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("SELECT * FROM eval_runs ORDER BY run_at DESC LIMIT %s", (limit,)).fetchall()
        return [_parse_row(dict(r)) for r in rows]
    finally:
        conn.close()


# ── Categories ───────────────────────────────────────────────────────────────

def upsert_category(cat_id: str, name: str, parent_id: str = "", icon: str = "folder", tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO categories (id, name, parent_id, icon)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, parent_id=EXCLUDED.parent_id, icon=EXCLUDED.icon
        """, (cat_id, name, parent_id, icon))
        conn.commit()
    finally:
        conn.close()


def update_category_counts(tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            UPDATE categories SET sop_count = (
                SELECT COUNT(*) FROM sops WHERE sops.category_id = categories.id
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── Relationships ─────────────────────────────────────────────────────────────

def upsert_relationship(source_id: str, target_id: str, rel_type: str = "related", reason: str = "", tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO relationships (source_id, target_id, type, reason)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_id, target_id, type) DO UPDATE SET reason=EXCLUDED.reason
        """, (source_id, target_id, rel_type, reason))
        conn.commit()
    finally:
        conn.close()


def get_relationships(sop_id: str, tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("""
            SELECT * FROM relationships
            WHERE source_id = %s OR target_id = %s
            ORDER BY created_at DESC
        """, (sop_id, sop_id)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_related_documents(sop_id: str, tenant_id: str = None) -> list:
    """Find documents related by shared keywords/entities."""
    sop = get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return []

    keywords = sop.get("search_keywords", [])
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except Exception:
            keywords = []

    if not keywords:
        return []

    # Find other SOPs that share keywords
    conn = get_db(tenant_id)
    try:
        related = []
        for kw in keywords[:5]:
            rows = conn.execute("""
                SELECT sop_id, title, summary_short FROM sops
                WHERE sop_id != %s AND search_text ILIKE %s
                LIMIT 3
            """, (sop_id, f"%{kw}%")).fetchall()
            for r in rows:
                if r["sop_id"] not in [x["sop_id"] for x in related]:
                    related.append(dict(r))
        return related[:5]
    finally:
        conn.close()


# ── Compliance ────────────────────────────────────────────────────────────────

def upsert_compliance(sop_id: str, data: dict, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO compliance (sop_id, has_version, has_author, has_date, has_signatures,
                is_expired, missing_sections, quality_score, recommendations)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sop_id) DO UPDATE SET
                has_version=EXCLUDED.has_version, has_author=EXCLUDED.has_author,
                has_date=EXCLUDED.has_date, has_signatures=EXCLUDED.has_signatures,
                is_expired=EXCLUDED.is_expired, missing_sections=EXCLUDED.missing_sections,
                quality_score=EXCLUDED.quality_score, recommendations=EXCLUDED.recommendations,
                checked_at=NOW()
        """, (sop_id, data.get("has_version", False), data.get("has_author", False),
              data.get("has_date", False), data.get("has_signatures", False),
              data.get("is_expired", False),
              json.dumps(data.get("missing_sections", [])),
              data.get("quality_score", 0),
              json.dumps(data.get("recommendations", []))))
        conn.commit()
    finally:
        conn.close()


def get_compliance(sop_id: str, tenant_id: str = None) -> Optional[dict]:
    conn = get_db(tenant_id)
    try:
        row = conn.execute("SELECT * FROM compliance WHERE sop_id = %s", (sop_id,)).fetchone()
    finally:
        conn.close()
    if row:
        d = dict(row)
        for f in ["missing_sections", "recommendations"]:
            if isinstance(d.get(f), str):
                try:
                    d[f] = json.loads(d[f])
                except Exception:
                    d[f] = []
        return d
    return None


def get_all_compliance(tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("SELECT * FROM compliance ORDER BY quality_score ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Page Content (vision extraction) ─────────────────────────────────────────

def upsert_page_content(sop_id: str, page: int, text_content: str = "", vision_content: str = "",
                        enhanced_content: str = "", missing_info: list = None, faqs: list = None,
                        tables: list = None, image_descriptions: list = None, key_info: str = "",
                        has_images: bool = False, has_tables: bool = False,
                        language: str = "english", extraction_method: str = "text",
                        tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO page_content (sop_id, page, text_content, vision_content, enhanced_content,
                missing_info, faqs, tables, image_descriptions, key_info, has_images, has_tables,
                language, extraction_method)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sop_id, page) DO UPDATE SET
                text_content=COALESCE(NULLIF(EXCLUDED.text_content, ''), page_content.text_content),
                vision_content=COALESCE(NULLIF(EXCLUDED.vision_content, ''), page_content.vision_content),
                enhanced_content=COALESCE(NULLIF(EXCLUDED.enhanced_content, ''), page_content.enhanced_content),
                missing_info=COALESCE(EXCLUDED.missing_info, page_content.missing_info),
                faqs=COALESCE(EXCLUDED.faqs, page_content.faqs),
                tables=COALESCE(EXCLUDED.tables, page_content.tables),
                image_descriptions=COALESCE(EXCLUDED.image_descriptions, page_content.image_descriptions),
                key_info=COALESCE(NULLIF(EXCLUDED.key_info, ''), page_content.key_info),
                has_images=EXCLUDED.has_images OR page_content.has_images,
                has_tables=EXCLUDED.has_tables OR page_content.has_tables,
                language=EXCLUDED.language, extraction_method=EXCLUDED.extraction_method
        """, (sop_id, page, text_content, vision_content, enhanced_content,
              json.dumps(missing_info or []), json.dumps(faqs or []),
              json.dumps(tables or []), json.dumps(image_descriptions or []),
              key_info, has_images, has_tables, language, extraction_method))
        conn.commit()
    finally:
        conn.close()


def get_page_contents(sop_id: str, pages: list = None, tenant_id: str = None) -> list:
    """Get extracted page content. If pages is None, return all pages."""
    conn = get_db(tenant_id)
    try:
        if pages:
            placeholders = ",".join(["%s"] * len(pages))
            rows = conn.execute(f"""
                SELECT * FROM page_content WHERE sop_id = %s AND page IN ({placeholders})
                ORDER BY page
            """, [sop_id] + pages).fetchall()
        else:
            rows = conn.execute("SELECT * FROM page_content WHERE sop_id = %s ORDER BY page", (sop_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_page_text(sop_id: str, tenant_id: str = None) -> str:
    """Get combined text from all pages. Priority: enhanced > vision > text."""
    pages = get_page_contents(sop_id, tenant_id=tenant_id)
    parts = []
    for p in pages:
        text = p.get("enhanced_content") or p.get("vision_content") or p.get("text_content") or ""
        if text:
            parts.append(f"--- Page {p['page']} ---\n{text}")
    return "\n\n".join(parts)


# ── Embeddings (PgVector) ────────────────────────────────────────────────────

def upsert_embedding(sop_id: str, page: int, chunk_index: int, content: str, embedding: list, metadata: dict = None, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO embeddings (sop_id, page, chunk_index, content, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT DO NOTHING
        """, (sop_id, page, chunk_index, content, json.dumps(metadata or {}), str(embedding)))
        conn.commit()
    finally:
        conn.close()


def _chunk_text(text: str, chunk_size: int = 1600, overlap: int = 200) -> list[str]:
    """Split text into chunks of ~400 tokens (~1600 chars) with overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start = end - overlap
        if start + overlap >= len(text):
            break
    return chunks if chunks else [text]


def embed_document_pages(sop_id: str, tenant_id: str = None) -> int:
    """Embed all page_content for a document into PgVector using chunk-level embeddings.
    Returns count of embedded chunks."""
    from backend.core.config import EMBEDDING_MODEL

    pages = get_page_contents(sop_id, tenant_id=tenant_id)
    if not pages:
        return 0

    # Delete old embeddings for this document
    conn = get_db(tenant_id)
    try:
        conn.execute("DELETE FROM embeddings WHERE sop_id = %s", (sop_id,))
        conn.commit()
    finally:
        conn.close()

    # Prepare chunks for embedding
    all_chunks = []  # list of (page_num, chunk_index, chunk_text)
    for p in pages:
        text = p.get("enhanced_content") or p.get("vision_content") or p.get("text_content") or ""
        # Add extra context for richer embeddings (if not already in enhanced)
        if not p.get("enhanced_content"):
            if p.get("key_info"):
                text += f"\n{p['key_info']}"
            img_desc = p.get("image_descriptions", [])
            if img_desc and isinstance(img_desc, list):
                text += f"\n{'; '.join(str(d) for d in img_desc)}"
        text = text.strip()
        if not text:
            continue
        chunks = _chunk_text(text)
        for ci, chunk in enumerate(chunks):
            all_chunks.append((p["page"], ci, chunk))

    if not all_chunks:
        return 0

    # All LLM calls go through OpenRouter — batch up to 20 texts per API call
    BATCH_SIZE = 20
    try:
        from backend.core.config import get_openrouter_client
        client = get_openrouter_client()

        for batch_start in range(0, len(all_chunks), BATCH_SIZE):
            batch = all_chunks[batch_start:batch_start + BATCH_SIZE]
            batch_texts = [c[2][:2000] for c in batch]  # Truncate chunks for embedding API

            response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch_texts)
            for i, emb_data in enumerate(response.data):
                page_num, chunk_index, chunk_text = batch[i]
                upsert_embedding(
                    sop_id=sop_id,
                    page=page_num,
                    chunk_index=chunk_index,
                    content=chunk_text[:500],  # Store truncated content for display
                    embedding=emb_data.embedding,
                    metadata={"sop_id": sop_id, "page": page_num, "chunk_index": chunk_index},
                    tenant_id=tenant_id,
                )
        return len(all_chunks)
    except Exception as e:
        print(f"Embedding error for {sop_id}: {e}")
        return 0


def vector_search(query_embedding: list, limit: int = 5, tenant_id: str = None) -> list:
    """Semantic search using PgVector cosine similarity.
    Deduplicates by sop_id+page, keeping the best-scoring chunk per page."""
    conn = get_db(tenant_id)
    try:
        # Fetch more rows than needed to allow deduplication across chunks
        fetch_limit = limit * 4
        rows = conn.execute("""
            SELECT sop_id, page, chunk_index, content, metadata,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM embeddings
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (str(query_embedding), str(query_embedding), fetch_limit)).fetchall()

        # Deduplicate: keep the best-scoring chunk per (sop_id, page)
        seen = {}
        for r in rows:
            key = (r["sop_id"], r["page"])
            if key not in seen or r["similarity"] > seen[key]["similarity"]:
                seen[key] = dict(r)

        # Sort by similarity descending and return top `limit`
        results = sorted(seen.values(), key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    finally:
        conn.close()


# ── Intent Routes ────────────────────────────────────────────────────────────

def upsert_intent_route(intent: str, keywords: list, sop_id: str, pages: str = "", reason: str = "", source: str = "auto", tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO intent_routes (intent, keywords, sop_id, pages, reason, source)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (intent, json.dumps(keywords), sop_id, pages, reason, source))
        conn.commit()
    finally:
        conn.close()


def search_intent_routes(query: str, limit: int = 3, tenant_id: str = None) -> list:
    """Search intent routes by matching query words against keywords JSONB array."""
    conn = get_db(tenant_id)
    try:
        words = [w.lower() for w in query.split() if len(w) > 2]
        if not words:
            return []

        # Match any keyword that contains any query word
        conditions = []
        params = []
        for word in words:
            conditions.append("keywords::text ILIKE %s")
            params.append(f"%{word}%")
        # Also match intent text
        for word in words:
            conditions.append("intent ILIKE %s")
            params.append(f"%{word}%")

        where = " OR ".join(conditions)
        params.append(limit)

        rows = conn.execute(f"""
            SELECT sop_id, intent, keywords, pages, reason, source, hit_count
            FROM intent_routes
            WHERE {where}
            ORDER BY hit_count DESC
            LIMIT %s
        """, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def bump_intent_hit_count(intent_id: int, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("UPDATE intent_routes SET hit_count = hit_count + 1 WHERE id = %s", (intent_id,))
        conn.commit()
    finally:
        conn.close()


def get_intent_routes(sop_id: Optional[str] = None, tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        if sop_id:
            rows = conn.execute("SELECT * FROM intent_routes WHERE sop_id = %s ORDER BY hit_count DESC", (sop_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM intent_routes ORDER BY hit_count DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_intent_routes(sop_id: str, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("DELETE FROM intent_routes WHERE sop_id = %s", (sop_id,))
        conn.commit()
    finally:
        conn.close()


def generate_intent_routes_from_sop(sop_id: str, tenant_id: str = None) -> int:
    """Auto-generate intent routes from a SOP's Q&A pairs and search keywords."""
    sop = get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return 0

    # Clear old auto-generated routes for this SOP
    conn = get_db(tenant_id)
    try:
        conn.execute("DELETE FROM intent_routes WHERE sop_id = %s AND source = 'auto'", (sop_id,))
        conn.commit()
    finally:
        conn.close()

    count = 0
    title = sop.get("title", sop_id)

    # Create route from each Q&A pair
    qa_pairs = sop.get("qa_pairs", [])
    if isinstance(qa_pairs, str):
        try:
            qa_pairs = json.loads(qa_pairs)
        except Exception:
            qa_pairs = []

    for q in qa_pairs:
        # Support both old format (string) and new format ({q, a, page})
        q_text = q if isinstance(q, str) else q.get("q", "") if isinstance(q, dict) else str(q)
        q_page = str(q.get("page", "")) if isinstance(q, dict) else ""
        if isinstance(q_text, str) and len(q_text) > 5:
            words = [w.lower() for w in q_text.split() if len(w) > 2]
            upsert_intent_route(
                intent=q_text,
                keywords=words,
                sop_id=sop_id,
                pages=q_page,
                reason=f"Extracted Q&A from {title}",
                source="auto",
                tenant_id=tenant_id,
            )
            count += 1

    # Create route from search keywords
    keywords = sop.get("search_keywords", [])
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except Exception:
            keywords = []

    if keywords:
        upsert_intent_route(
            intent=f"Find information about {title}",
            keywords=[k.lower() for k in keywords if isinstance(k, str)],
            sop_id=sop_id,
            pages="",
            reason=f"Search keywords from {title}",
            source="auto",
            tenant_id=tenant_id,
        )
        count += 1

    return count


# ── Wiki Pages ────────────────────────────────────────────────────────────────

def upsert_wiki_page(page_id: str, title: str, category: str, content: str,
                     sources: list = None, related: list = None,
                     contradictions: list = None, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("""
            INSERT INTO wiki_pages (id, title, category, content, sources, related, contradictions, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                title=EXCLUDED.title, category=EXCLUDED.category, content=EXCLUDED.content,
                sources=EXCLUDED.sources, related=EXCLUDED.related,
                contradictions=EXCLUDED.contradictions, updated_at=NOW()
        """, (page_id, title, category, content,
              json.dumps(sources or []), json.dumps(related or []),
              json.dumps(contradictions or [])))
        conn.commit()
    finally:
        conn.close()


def get_wiki_page(page_id: str, tenant_id: str = None) -> Optional[dict]:
    conn = get_db(tenant_id)
    try:
        row = conn.execute("SELECT * FROM wiki_pages WHERE id = %s", (page_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def search_wiki_pages(query: str, limit: int = 3, tenant_id: str = None) -> list:
    """Search wiki pages by keyword matching on title and content."""
    conn = get_db(tenant_id)
    try:
        words = [w.lower() for w in query.split() if len(w) > 2]
        if not words:
            return []
        conditions = []
        params = []
        for word in words:
            conditions.append("(title ILIKE %s OR content ILIKE %s)")
            params.extend([f"%{word}%", f"%{word}%"])
        where = " OR ".join(conditions)
        params.append(limit)
        rows = conn.execute(f"""
            SELECT * FROM wiki_pages WHERE {where}
            ORDER BY hit_count DESC LIMIT %s
        """, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_wiki_pages(tenant_id: str = None) -> list:
    conn = get_db(tenant_id)
    try:
        rows = conn.execute("SELECT id, title, category, hit_count, sources, contradictions, updated_at FROM wiki_pages ORDER BY hit_count DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_wiki_page(page_id: str, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("DELETE FROM wiki_pages WHERE id = %s", (page_id,))
        conn.commit()
    finally:
        conn.close()


def bump_wiki_hit(page_id: str, tenant_id: str = None):
    conn = get_db(tenant_id)
    try:
        conn.execute("UPDATE wiki_pages SET hit_count = hit_count + 1 WHERE id = %s", (page_id,))
        conn.commit()
    finally:
        conn.close()


# ── Migration from old catalog.json ──────────────────────────────────────────

def migrate_from_catalog(catalog_path: Path) -> int:
    if not catalog_path.exists():
        return 0
    catalog = json.loads(catalog_path.read_text())
    count = 0
    for sop_id, info in catalog.items():
        if not info.get("doc_id"):
            continue
        upsert_sop({
            "sop_id": sop_id,
            "title": info.get("doc_name", ""),
            "description": info.get("doc_description", ""),
            "department": info.get("department", ""),
            "pdf_path": info.get("file_path", ""),
            "page_count": info.get("page_count", 0),
            "doc_description": info.get("doc_description", ""),
            "pageindex_doc_id": info.get("doc_id", ""),
            "total_screenshots": info.get("total_extracted_images", 0),
        })
        for page_str, imgs in info.get("extracted_images", {}).items():
            for img in imgs:
                upsert_screenshot(sop_id, int(page_str), img["index"],
                    img.get("path", ""), img.get("width", 0), img.get("height", 0))
        count += 1
    return count


# Initialize on import
try:
    init_db()
except Exception as e:
    print(f"DB init warning (will retry on first use): {e}")
