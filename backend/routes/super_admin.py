"""Super Admin API routes: manage tenants, view usage, health checks."""
from __future__ import annotations

import os
import time
import shutil
import logging

logger = logging.getLogger(__name__)
from pathlib import Path
from fastapi import APIRouter, Query
from backend.core import database as db
from backend.core.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, INSTANCE, AGENT_CONFIG

router = APIRouter(prefix="/api/super")

_start_time = time.time()


# ── Instance Config (read-only, used by frontend) ───────────────────────────

@router.get("/instance")
async def get_instance_config():
    """Serve instance.yaml config for frontend branding."""
    return INSTANCE


@router.get("/agent-config")
async def get_agent_config():
    """Serve agent persona config for frontend."""
    return AGENT_CONFIG


# ── Platform Stats ───────────────────────────────────────────────────────────

@router.get("/stats")
async def platform_stats():
    """Aggregate stats across all tenants + platform health."""
    tenants = db.list_tenants()
    total_docs = 0
    total_queries = 0
    total_queries_24h = 0
    total_embeddings = 0

    # Batch: one query per tenant (unavoidable due to schema isolation)
    for t in tenants:
        try:
            conn = db.get_db(t["id"])
            try:
                row = conn.execute("""
                    SELECT
                        (SELECT COUNT(*) FROM sops) AS docs,
                        (SELECT COUNT(*) FROM embeddings) AS embeds,
                        (SELECT COUNT(*) FROM query_log) AS queries,
                        (SELECT COUNT(*) FROM query_log WHERE created_at > NOW() - INTERVAL '24 hours') AS queries_24h
                """).fetchone()
                if row:
                    total_docs += row["docs"]
                    total_embeddings += row["embeds"]
                    total_queries += row["queries"]
                    total_queries_24h += row["queries_24h"]
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"Stats for {t['id']}: {e}")

    # DB size
    db_size_mb = 0
    try:
        conn = db.get_db()
        try:
            row = conn.execute("SELECT pg_database_size(current_database()) AS s").fetchone()
            db_size_mb = round(row["s"] / (1024 * 1024), 1) if row else 0
        finally:
            conn.close()
    except Exception:
        pass

    # Storage
    storage_mb = 0
    tenant_dir = db.DATA_DIR / "tenants"
    if tenant_dir.exists():
        for f in tenant_dir.rglob("*"):
            if f.is_file():
                storage_mb += f.stat().st_size
    storage_mb = round(storage_mb / (1024 * 1024), 1)

    # Uptime
    uptime_s = int(time.time() - _start_time)
    days = uptime_s // 86400
    hours = (uptime_s % 86400) // 3600
    mins = (uptime_s % 3600) // 60
    uptime_str = f"{days}d {hours}h {mins}m" if days else f"{hours}h {mins}m"

    return {
        "total_tenants": len(tenants),
        "active_tenants": sum(1 for t in tenants if t.get("is_active")),
        "total_documents": total_docs,
        "total_queries": total_queries,
        "total_queries_24h": total_queries_24h,
        "total_embeddings": total_embeddings,
        "db_size_mb": db_size_mb,
        "storage_mb": storage_mb,
        "uptime": uptime_str,
    }


@router.get("/health")
async def health_checks():
    """System health checks."""
    checks = {}

    # DB
    try:
        conn = db.get_db()
        conn.execute("SELECT 1")
        conn.close()
        checks["database"] = {"status": "ok", "detail": "PostgreSQL connected"}
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)}

    # PgVector
    try:
        conn = db.get_db()
        row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        conn.close()
        checks["pgvector"] = {"status": "ok", "detail": f"v{row['extversion']}" if row else "not installed"}
    except Exception:
        checks["pgvector"] = {"status": "error", "detail": "Cannot check"}

    # LLM
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
        resp = client.chat.completions.create(model="google/gemini-2.0-flash-001", messages=[{"role": "user", "content": "ping"}], max_tokens=5)
        checks["llm"] = {"status": "ok", "detail": "OpenRouter reachable"}
    except Exception as e:
        checks["llm"] = {"status": "error", "detail": str(e)[:80]}

    # Disk
    try:
        total, used, free = shutil.disk_usage("/")
        pct = round(used / total * 100)
        checks["disk"] = {"status": "ok" if pct < 90 else "warning", "detail": f"{pct}% used ({round(free / (1024**3), 1)} GB free)"}
    except Exception:
        checks["disk"] = {"status": "unknown", "detail": "Cannot check"}

    return checks


# ── Tenant CRUD ──────────────────────────────────────────────────────────────

@router.get("/tenants")
async def list_tenants():
    """List all tenants with per-tenant stats."""
    tenants = db.list_tenants()
    result = []
    for t in tenants:
        tenant_id = t["id"]
        stats = {"documents": 0, "pages": 0, "queries_total": 0, "queries_24h": 0,
                 "embeddings": 0, "feedback_up": 0, "feedback_down": 0, "avg_duration": 0,
                 "storage_mb": 0, "last_query": None}
        try:
            s = db.get_stats(tenant_id=tenant_id)
            stats["documents"] = s.get("total_indexed", 0)
            stats["pages"] = s.get("total_pages", 0)
            stats["embeddings"] = s.get("total_embeddings", 0)
            stats["queries_total"] = s.get("total_queries", 0)

            conn = db.get_db(tenant_id)
            # 24h queries
            row = conn.execute("SELECT COUNT(*) AS c FROM query_log WHERE created_at > NOW() - INTERVAL '24 hours'").fetchone()
            stats["queries_24h"] = row["c"] if row else 0
            # Feedback
            row = conn.execute("SELECT COUNT(*) FILTER (WHERE feedback='up') AS up, COUNT(*) FILTER (WHERE feedback='down') AS down FROM query_log WHERE feedback IS NOT NULL").fetchone()
            stats["feedback_up"] = row["up"] if row else 0
            stats["feedback_down"] = row["down"] if row else 0
            # Avg duration
            row = conn.execute("SELECT AVG(duration_s) AS avg FROM query_log WHERE duration_s > 0").fetchone()
            stats["avg_duration"] = round(row["avg"], 1) if row and row["avg"] else 0
            # Last query
            row = conn.execute("SELECT created_at FROM query_log ORDER BY created_at DESC LIMIT 1").fetchone()
            stats["last_query"] = row["created_at"].isoformat() if row and row.get("created_at") else None
            conn.close()
        except Exception:
            pass

        # Storage
        tenant_dir = db.DATA_DIR / "tenants" / tenant_id
        if tenant_dir.exists():
            size = sum(f.stat().st_size for f in tenant_dir.rglob("*") if f.is_file())
            stats["storage_mb"] = round(size / (1024 * 1024), 1)

        result.append({**t, "stats": stats})
    return result


@router.post("/tenants")
async def create_tenant(request: dict):
    """Create a new tenant with auto-generated ID."""
    import re
    name = request.get("name", "").strip()
    if not name:
        return {"error": "Company/Department name is required"}

    # Auto-generate ID from name if not provided
    tenant_id = request.get("id", "").strip().lower()
    if not tenant_id:
        tenant_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40]
    tenant_id = re.sub(r'[^a-z0-9\-]', '', tenant_id)

    if len(tenant_id) < 2:
        return {"error": "Tenant ID too short (min 2 chars)"}

    admin_user = request.get("admin_user", "admin").strip() or "admin"
    admin_pass = request.get("admin_pass", "").strip()
    if not admin_pass:
        return {"error": "Admin password is required"}

    existing = db.get_tenant(tenant_id)
    if existing:
        return {"error": f"Tenant '{tenant_id}' already exists"}

    result = db.create_tenant(
        tenant_id, name, admin_user, admin_pass,
        agent_name=request.get("agent_name") or f"{name} Agent",
        agent_role=request.get("agent_role", "document intelligence assistant"),
        agent_focus=request.get("agent_focus", "organizational documents"),
        agent_personality=request.get("agent_personality", "professional, precise"),
        agent_languages=request.get("agent_languages", ["English"]),
        branding=request.get("branding", {}),
    )

    # Return with full URLs
    tenant = db.get_tenant(tenant_id)
    return {
        **result,
        "admin_url": f"/t/{tenant_id}/admin",
        "embed_token": tenant.get("embed_token", "") if tenant else "",
    }


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str):
    """Get tenant details + stats."""
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}
    # Get stats
    stats = {}
    try:
        stats = db.get_stats(tenant_id=tenant_id)
    except Exception:
        pass
    return {**tenant, "stats": stats}


@router.put("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, request: dict):
    """Update tenant config."""
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}

    import json
    import hashlib
    conn = db.get_db()
    updates = []
    params = []

    for field in ["name", "agent_name", "agent_role", "agent_focus", "agent_personality", "max_documents", "is_active", "embed_enabled", "agent_tone", "agent_style", "agent_temperature", "agent_system_prompt", "sop_template"]:
        if field in request:
            updates.append(f"{field} = %s")
            params.append(request[field])
    if "agent_languages" in request:
        updates.append("agent_languages = %s")
        params.append(json.dumps(request["agent_languages"]))
    if "branding" in request:
        updates.append("branding = %s")
        params.append(json.dumps(request["branding"]))
    if "document_mode" in request:
        updates.append("document_mode = %s")
        params.append(request["document_mode"])
    # Reset password
    if "admin_pass" in request and request["admin_pass"]:
        updates.append("admin_pass_hash = %s")
        params.append(db._hash_password(request["admin_pass"]))
    if "admin_user" in request:
        updates.append("admin_user = %s")
        params.append(request["admin_user"])
    # Regenerate embed token
    if request.get("regenerate_token"):
        import secrets
        new_token = secrets.token_urlsafe(24)
        updates.append("embed_token = %s")
        params.append(new_token)

    if updates:
        params.append(tenant_id)
        conn.execute(f"UPDATE tenants SET {', '.join(updates)} WHERE id = %s", params)
        conn.commit()
    conn.close()

    from backend.core.agent import reload_agent
    reload_agent(tenant_id)

    return {"status": "updated", "tenant_id": tenant_id}


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str):
    """Delete tenant."""
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}
    db.delete_tenant(tenant_id)
    from backend.core.agent import reload_agent
    reload_agent(tenant_id)
    return {"status": "deleted", "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/login")
async def tenant_login(tenant_id: str, request: dict):
    """Login to a specific tenant's admin."""
    import hashlib
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Tenant not found"}, status_code=404)

    username = request.get("username", "")
    password = request.get("password", "")

    if username == tenant["admin_user"] and db._verify_password(password, tenant.get("admin_pass_hash", "")):
        import secrets
        token = secrets.token_urlsafe(32)
        from backend.main import _create_tenant_token
        _create_tenant_token(token, tenant_id)
        return {"token": token, "tenant_id": tenant_id, "user": username}

    from fastapi.responses import JSONResponse
    return JSONResponse({"error": "Invalid credentials"}, status_code=401)


# ── Monitoring & Analytics ───────────────────────────────────────────────────

@router.get("/monitoring/usage")
async def get_usage(days: int = Query(30), tenant_id: str = Query(None)):
    """Get LLM usage stats, optionally per tenant."""
    return db.get_usage_stats(tenant_id=tenant_id, days=days)


@router.get("/monitoring/audit")
async def get_audit(limit: int = Query(100), tenant_id: str = Query(None)):
    """Get audit log entries."""
    return db.get_audit_log(tenant_id=tenant_id, limit=limit)


@router.get("/monitoring/alerts")
async def get_alerts_list(unread: bool = Query(False)):
    """Get system alerts."""
    return db.get_alerts(unread_only=unread)


@router.post("/monitoring/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: int):
    """Mark alert as read."""
    try:
        conn = db.get_db()
        try:
            conn.execute("UPDATE alerts SET is_read = TRUE WHERE id = %s", (alert_id,))
            conn.commit()
        finally:
            conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/monitoring/tenant/{tenant_id}")
async def tenant_deep_dive(tenant_id: str):
    """Full analytics for a single tenant: agent performance, document health, top questions."""
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}

    stats = db.get_stats(tenant_id=tenant_id)
    usage = db.get_usage_stats(tenant_id=tenant_id, days=30)
    docs = db.list_sops(tenant_id=tenant_id)

    # Agent performance from query_log
    conn = db.get_db(tenant_id)
    try:
        total_queries = conn.execute("SELECT COUNT(*) as c FROM query_log").fetchone()["c"]
        avg_duration = conn.execute("SELECT COALESCE(AVG(duration_s), 0) as a FROM query_log WHERE duration_s > 0").fetchone()["a"]
        feedback_up = conn.execute("SELECT COUNT(*) as c FROM query_log WHERE feedback = 'up'").fetchone()["c"]
        feedback_down = conn.execute("SELECT COUNT(*) as c FROM query_log WHERE feedback = 'down'").fetchone()["c"]
        recent_queries = conn.execute("SELECT question, duration_s, feedback, model, created_at FROM query_log ORDER BY created_at DESC LIMIT 20").fetchall()

        # Top unanswered (queries with thumbs down or no feedback + high frequency)
        unanswered = conn.execute("""
            SELECT question, COUNT(*) as ask_count,
                   SUM(CASE WHEN feedback = 'down' THEN 1 ELSE 0 END) as down_count
            FROM query_log
            GROUP BY question
            HAVING COUNT(*) > 1 OR SUM(CASE WHEN feedback = 'down' THEN 1 ELSE 0 END) > 0
            ORDER BY down_count DESC, ask_count DESC
            LIMIT 10
        """).fetchall()

        # Self-learning count (discoveries + negatives from agent tools)
        learnings = 0
        try:
            row = conn.execute("SELECT COUNT(*) as c FROM intent_routes WHERE source IN ('discovered', 'negative')").fetchone()
            learnings = row["c"] if row else 0
        except Exception:
            pass
    finally:
        conn.close()

    # Document health
    scored_docs = [d for d in docs if d.get("sop_score", 0) > 0]
    avg_sop_score = round(sum(d["sop_score"] for d in scored_docs) / len(scored_docs)) if scored_docs else 0
    stale_docs = []
    from datetime import datetime, timedelta
    for d in docs:
        created = d.get("created_at")
        if created:
            try:
                if isinstance(created, str):
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if (datetime.now(created.tzinfo) - created).days > 180:
                    stale_docs.append(d.get("sop_id"))
            except Exception:
                pass

    satisfaction = round(feedback_up / max(feedback_up + feedback_down, 1) * 5, 1)

    return {
        "tenant": {
            "id": tenant_id, "name": tenant.get("name"),
            "agent_name": tenant.get("agent_name"), "agent_role": tenant.get("agent_role"),
            "agent_focus": tenant.get("agent_focus"), "agent_personality": tenant.get("agent_personality"),
            "agent_tone": tenant.get("agent_tone"), "agent_style": tenant.get("agent_style"),
            "agent_languages": tenant.get("agent_languages"),
            "document_mode": tenant.get("document_mode"), "sop_template": tenant.get("sop_template"),
            "admin_user": tenant.get("admin_user"), "created_at": str(tenant.get("created_at", "")),
            "embed_token": tenant.get("embed_token"),
        },
        "documents": [{"sop_id": d.get("sop_id"), "title": d.get("title"), "department": d.get("department"),
                        "page_count": d.get("page_count", 0), "sop_score": d.get("sop_score", 0),
                        "created_at": str(d.get("created_at", ""))} for d in docs],
        "stats": stats,
        "agent_performance": {
            "total_queries": total_queries,
            "avg_response_sec": round(float(avg_duration), 2),
            "feedback_up": feedback_up,
            "feedback_down": feedback_down,
            "satisfaction_score": satisfaction,
            "self_learned_mappings": learnings,
        },
        "top_unanswered": [{"question": r["question"][:100], "ask_count": r["ask_count"], "down_count": r["down_count"]} for r in unanswered],
        "recent_queries": [{"question": r["question"][:80], "duration": round(float(r["duration_s"] or 0), 2), "feedback": r["feedback"]} for r in recent_queries],
        "document_health": {
            "total_docs": len(docs),
            "standardized": len(scored_docs),
            "avg_sop_score": avg_sop_score,
            "excellent": len([d for d in scored_docs if d["sop_score"] >= 80]),
            "good": len([d for d in scored_docs if 60 <= d["sop_score"] < 80]),
            "needs_work": len([d for d in scored_docs if d["sop_score"] < 60]),
            "stale_docs": stale_docs,
        },
        "cost": usage,
    }


@router.get("/monitoring/tenant/{tenant_id}/chats")
async def tenant_chat_history(tenant_id: str, limit: int = Query(20)):
    """Get conversation sessions with messages for a tenant."""
    try:
        conn = db.get_db(tenant_id)
        try:
            convs = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT %s", (limit,)).fetchall()
            result = []
            for c in convs:
                msgs = conn.execute("SELECT role, content, created_at FROM conversation_messages WHERE conversation_id = %s ORDER BY created_at", (c["id"],)).fetchall()
                result.append({
                    "id": c["id"], "title": c["title"], "message_count": c["message_count"],
                    "created_at": str(c["created_at"]), "updated_at": str(c.get("updated_at", "")),
                    "messages": [{"role": m["role"], "content": m["content"][:200], "created_at": str(m["created_at"])} for m in msgs]
                })
            return result
        finally:
            conn.close()
    except Exception as e:
        return []


@router.get("/monitoring/live-queries")
async def live_queries(limit: int = Query(20)):
    """Get recent queries across ALL tenants for live stream."""
    tenants = db.list_tenants()
    all_queries = []
    for t in tenants[:20]:
        try:
            conn = db.get_db(t["id"])
            try:
                rows = conn.execute(
                    "SELECT question, duration_s, feedback, model, created_at FROM query_log ORDER BY created_at DESC LIMIT %s",
                    (limit,)
                ).fetchall()
                for r in rows:
                    all_queries.append({
                        "tenant": t.get("name", t["id"]),
                        "tenant_id": t["id"],
                        "question": r["question"][:100] if r["question"] else "",
                        "duration": round(float(r["duration_s"] or 0), 2),
                        "feedback": r["feedback"],
                        "model": r["model"],
                        "created_at": str(r["created_at"]) if r["created_at"] else "",
                    })
            finally:
                conn.close()
        except Exception:
            pass
    all_queries.sort(key=lambda x: x["created_at"], reverse=True)
    return all_queries[:limit]


# ── Per-Tenant Schema Info (for System page) ─────────────────────────────────

@router.get("/schemas")
async def list_schemas():
    """Get all tenant schemas with table row counts."""
    tenants = db.list_tenants()
    schemas = []

    for t in tenants:
        tid = t["id"]
        tables = []
        try:
            conn = db.get_db(tid)
            for table in ["sops", "page_content", "embeddings", "conversations", "conversation_messages",
                          "query_log", "intent_routes", "screenshots", "compliance", "categories",
                          "relationships", "runtime_config", "eval_runs"]:
                try:
                    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                    tables.append({"name": table, "rows": row["c"] if row else 0})
                except Exception:
                    tables.append({"name": table, "rows": 0})
            conn.close()
        except Exception:
            pass

        schemas.append({
            "tenant_id": tid,
            "tenant_name": t.get("name", tid),
            "tables": tables,
            "total_rows": sum(t["rows"] for t in tables),
        })

    return schemas
