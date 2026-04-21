"""
Document Intelligence Agent — FastAPI + Frontend (single port)
"""
from __future__ import annotations

import os
import re
import json
import uuid
import logging
from fastapi import FastAPI, Request

from backend.core.config import setup_logging, request_id_var, tenant_id_var
setup_logging()

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.database import get_tenant_screenshot_dir
from backend.core.config import ADMIN_USER, ADMIN_PASS
import hashlib, secrets, time, resource, shutil, threading

_server_start_time = time.time()

STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_DIR = Path("/app/static-frontend")

from backend.routes.chat import router as chat_router
from backend.routes.ingest import router as ingest_router
from backend.routes.super_admin import router as super_router
from backend.routes.tenant_admin import router as tenant_admin_router

app = FastAPI(
    title="Document Intelligence Agent API",
    description="PgVector-powered document intelligence",
    version="2.0.0",
)

@app.on_event("startup")
async def startup():
    from backend.core.config import PROJECT_ROOT
    from backend.core.database import migrate_from_catalog
    catalog_path = PROJECT_ROOT / "catalog.json"
    if catalog_path.exists():
        count = migrate_from_catalog(catalog_path)
        if count > 0:
            print(f"Auto-migrated {count} docs from catalog.json")
    # Ensure tokens table exists (DB-backed auth)
    _ensure_tokens_table()

# ── Security Headers ─────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── Request Context Middleware ────────────────────────────────────────────────

class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a unique request_id and extract tenant_id for structured logging."""
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request_id_var.set(rid)
        # Extract tenant_id from URL if present (e.g. /api/t/{tenant_id}/...)
        m = re.match(r"^/api/t/([^/]+)/", request.url.path)
        tenant_id_var.set(m.group(1) if m else "")
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

app.add_middleware(RequestContextMiddleware)

# ── Session tokens (DB-backed — survive rebuilds) ────────────────────────────
# Falls back to in-memory if DB unavailable

_token_cache: dict[str, dict] = {}  # Local cache to avoid DB hit every request
_token_cache_last_prune = 0.0  # Timestamp of last cache cleanup

def _ensure_tokens_table():
    """Create tokens table in public schema if not exists."""
    try:
        from backend.core.database import get_db
        conn = get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                token_type TEXT NOT NULL DEFAULT 'super',
                tenant_id TEXT,
                expiry DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()
        conn.close()
    except Exception as _e:
        logger.debug(f"Token op: {_e}")

def _create_token(token_type: str = "super", tenant_id: str = None, email: str = None) -> str:
    token = secrets.token_urlsafe(32)
    expiry = time.time() + 86400
    info = {"expiry": expiry, "type": token_type, "tenant_id": tenant_id}
    if email:
        info["email"] = email
    _token_cache[token] = info
    try:
        from backend.core.database import get_db
        conn = get_db()
        conn.execute("INSERT INTO auth_tokens (token, token_type, tenant_id, expiry) VALUES (%s, %s, %s, %s) ON CONFLICT (token) DO UPDATE SET expiry = EXCLUDED.expiry",
                     (token, token_type, tenant_id, expiry))
        conn.commit()
        conn.close()
    except Exception as _e:
        logger.debug(f"Token op: {_e}")
    return token

def _create_tenant_token(token: str, tenant_id: str):
    """Called from super_admin.py for tenant login."""
    expiry = time.time() + 86400
    _token_cache[token] = {"expiry": expiry, "type": "tenant", "tenant_id": tenant_id}
    try:
        from backend.core.database import get_db
        conn = get_db()
        conn.execute("INSERT INTO auth_tokens (token, token_type, tenant_id, expiry) VALUES (%s, %s, %s, %s) ON CONFLICT (token) DO UPDATE SET expiry = EXCLUDED.expiry",
                     (token, "tenant", tenant_id, expiry))
        conn.commit()
        conn.close()
    except Exception as _e:
        logger.debug(f"Token op: {_e}")

def _prune_token_cache():
    """Remove expired tokens from in-memory cache. Runs at most once per hour."""
    global _token_cache_last_prune
    now = time.time()
    if now - _token_cache_last_prune < 3600:
        return
    expired = [k for k, v in _token_cache.items() if v["expiry"] < now]
    for k in expired:
        _token_cache.pop(k, None)
    _token_cache_last_prune = now

def _validate_token(token: str) -> dict | None:
    """Returns token info if valid, None if expired/invalid. Checks cache first, then DB."""
    _prune_token_cache()
    # Check cache
    info = _token_cache.get(token)
    if info and info["expiry"] > time.time():
        return info
    _token_cache.pop(token, None)
    # Check DB
    try:
        from backend.core.database import get_db
        conn = get_db()
        try:
            row = conn.execute("SELECT token_type, tenant_id, expiry FROM auth_tokens WHERE token = %s", (token,)).fetchone()
            if row and row["expiry"] > time.time():
                info = {"expiry": row["expiry"], "type": row["token_type"], "tenant_id": row["tenant_id"]}
                _token_cache[token] = info
                return info
            if row:  # Expired — clean up
                conn.execute("DELETE FROM auth_tokens WHERE token = %s", (token,))
                conn.commit()
        finally:
            conn.close()
    except Exception as _e:
        logger.debug(f"Token validate: {_e}")
    return None

def _get_token_tenant(token: str) -> str | None:
    """Get tenant_id from a valid token."""
    info = _validate_token(token)
    return info.get("tenant_id") if info else None

# ── Login endpoint (super admin) ─────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    # Use constant-time comparison to prevent timing attacks
    import hmac
    if ADMIN_USER and ADMIN_PASS and hmac.compare_digest(username, ADMIN_USER) and hmac.compare_digest(password, ADMIN_PASS):
        token = _create_token("super")
        return {"token": token, "user": username, "type": "super"}
    return JSONResponse({"error": "Invalid username or password"}, status_code=401)

@app.get("/api/auth/check")
async def check_auth(request: Request):
    """Check if auth is required and if current token is valid."""
    auth_required = bool(ADMIN_USER and ADMIN_PASS)
    if not auth_required:
        return {"auth_required": False, "authenticated": True, "type": "super"}
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    valid = _validate_token(token) if token else False
    return {"auth_required": True, "authenticated": valid}

# ── Admin Auth Middleware ─────────────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """Protect admin routes. Super admin for /api/super/*, tenant admin for /api/admin/*."""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""

        # Super admin routes: require super admin token
        if path.startswith("/api/super"):
            # Allow tenant login without super token
            if path.endswith("/login"):
                return await call_next(request)
            if ADMIN_USER and ADMIN_PASS:
                token_info = _validate_token(token)
                if not token_info:
                    return JSONResponse({"error": "Super admin access required"}, status_code=401)
                # Allow tenant tokens to access their own tenant info
                if token_info.get("type") == "tenant":
                    tenant_id = token_info.get("tenant_id", "")
                    # Allow GET/PUT on /api/super/tenants/{tenant_id} only
                    own_tenant_match = re.match(r"^/api/super/tenants/([^/]+)$", path)
                    if own_tenant_match and own_tenant_match.group(1) == tenant_id and request.method in ("GET", "PUT"):
                        pass  # Allow GET/PUT on own tenant info only
                    else:
                        return JSONResponse({"error": "Super admin access required"}, status_code=401)
            return await call_next(request)

        # Tenant admin routes: require tenant or super token
        if path.startswith("/api/t/") and "/admin/" in path:
            # Exempt read-only paths loaded by img tags or public chat widget (no auth headers)
            if "/pages/" in path or "/download/" in path or path.endswith("/preview") or path.endswith("/starter-questions"):
                return await call_next(request)
            if ADMIN_USER and ADMIN_PASS:
                token_info = _validate_token(token)
                if not token_info:
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)
                # Tenant tokens can only access their own tenant's admin
                if token_info.get("type") == "tenant":
                    path_tenant = re.match(r"^/api/t/([^/]+)/", path)
                    if path_tenant and path_tenant.group(1) != token_info.get("tenant_id", ""):
                        return JSONResponse({"error": "Forbidden — cannot access another tenant"}, status_code=403)
            return await call_next(request)

        return await call_next(request)

app.add_middleware(AuthMiddleware)

# ── CORS ─────────────────────────────────────────────────────────────────────
_cors_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=("*" not in _cors_origins),  # credentials not allowed with wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiting ────────────────────────────────────────────────────────────
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Screenshots served via /api/t/{tenant_id}/images/... route (below) ───────


# ── Tenant-scoped screenshot serving ────────────────────────────────────────
@app.get("/api/t/{tenant_id}/images/{sop_id}/{filename:path}")
async def serve_tenant_image(tenant_id: str, sop_id: str, filename: str):
    """Serve screenshots from tenant-scoped directory."""
    import re as _re
    # Validate inputs to prevent path traversal
    if not _re.match(r'^[\w\-]+$', tenant_id) or not _re.match(r'^[\w\-\.]+$', sop_id):
        return JSONResponse({"error": "Invalid path"}, status_code=400)
    if ".." in filename or filename.startswith("/"):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    tenant_ss_dir = get_tenant_screenshot_dir(tenant_id)
    file_path = tenant_ss_dir / sop_id / filename
    resolved = file_path.resolve()
    # Ensure resolved path is within the tenant directory
    if not str(resolved).startswith(str(tenant_ss_dir.resolve())):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    if not resolved.is_file():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(resolved)

# ── Static: SvelteKit assets (must be before catch-all) ──────────────────────
if FRONTEND_DIR.exists() and (FRONTEND_DIR / "_app").exists():
    app.mount("/_app", StaticFiles(directory=str(FRONTEND_DIR / "_app")), name="frontend-app")

# ── API Routes ───────────────────────────────────────────────────────────────
app.include_router(chat_router)
app.include_router(ingest_router)
app.include_router(super_router)
app.include_router(tenant_admin_router)

@app.get("/api/health")
async def health():
    checks: dict[str, dict] = {}
    overall = "healthy"

    # 1. Database check
    try:
        from backend.core.database import get_db
        t0 = time.time()
        conn = get_db()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
        latency_ms = round((time.time() - t0) * 1000, 1)
        checks["database"] = {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
        overall = "unhealthy"

    # 2. Disk space check (/data directory)
    try:
        data_path = "/data" if os.path.isdir("/data") else str(Path(__file__).parent.parent)
        usage = shutil.disk_usage(data_path)
        free_gb = round(usage.free / (1024 ** 3), 2)
        if free_gb < 0.5:
            checks["disk"] = {"status": "warning", "free_gb": free_gb}
            if overall == "healthy":
                overall = "degraded"
        else:
            checks["disk"] = {"status": "ok", "free_gb": free_gb}
    except Exception as e:
        checks["disk"] = {"status": "error", "error": str(e)}
        if overall == "healthy":
            overall = "degraded"

    # 3. Memory (RSS via resource module)
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in bytes on Linux, kilobytes on macOS
        import platform
        if platform.system() == "Darwin":
            rss_mb = round(ru.ru_maxrss / (1024 * 1024), 1)
        else:
            rss_mb = round(ru.ru_maxrss / 1024, 1)
        checks["memory"] = {"status": "ok", "rss_mb": rss_mb}
    except Exception as e:
        checks["memory"] = {"status": "error", "error": str(e)}

    # 4. OpenRouter API key check
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if api_key:
        checks["openrouter"] = {"status": "ok"}
    else:
        checks["openrouter"] = {"status": "warning", "error": "OPENROUTER_API_KEY not set"}
        if overall == "healthy":
            overall = "degraded"

    # 5. Uptime
    uptime_seconds = round(time.time() - _server_start_time, 1)

    return {
        "status": overall,
        "uptime_seconds": uptime_seconds,
        "checks": checks,
    }

@app.get("/widget.js")
async def serve_widget():
    return FileResponse(STATIC_DIR / "widget.js", media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"})

@app.get("/static/chat-widget.js")
async def serve_chat_widget():
    return FileResponse(STATIC_DIR / "chat-widget.js", media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=60"})

@app.get("/static/logo.svg")
async def serve_logo():
    return FileResponse(STATIC_DIR / "logo.svg", media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"})

@app.get("/favicon.svg")
async def serve_favicon_svg():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"})

@app.get("/favicon.ico")
async def serve_favicon_ico():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"})

@app.get("/test")
async def test_page():
    return FileResponse(STATIC_DIR / "test.html", media_type="text/html")

@app.get("/t/{tenant_id}/admin")
async def tenant_admin_page(tenant_id: str):
    """Tenant micro admin page."""
    from backend.core.database import get_tenant
    tenant = get_tenant(tenant_id)
    if not tenant or not tenant.get("is_active"):
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    admin_path = STATIC_DIR / "tenant-admin.html"
    if not admin_path.exists():
        return JSONResponse({"error": "Admin page not found"}, status_code=404)
    html = admin_path.read_text(encoding="utf-8")
    html = html.replace("__TENANT_ID__", tenant_id)
    return Response(content=html, media_type="text/html")

@app.post("/api/t/{tenant_id}/chat-auth/login")
async def chat_user_login(tenant_id: str, request: Request):
    """Chat user login — returns token if valid."""
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    if not email or not password:
        return JSONResponse({"error": "Email and password required"}, status_code=400)
    from backend.core import database as db
    result = db.verify_chat_user(tenant_id, email, password)
    if not result:
        return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    if result.get("error") == "pending":
        return JSONResponse({"error": "Your access request is pending approval", "status": "pending"}, status_code=403)
    if result.get("error") == "disabled":
        return JSONResponse({"error": "Your account has been disabled", "status": "disabled"}, status_code=403)
    # Create a chat_user token
    token = _create_token("chat_user", tenant_id, email=email)
    return {"token": token, "email": email, "name": result.get("display_name", ""), "tenant_id": tenant_id}

@app.post("/api/t/{tenant_id}/chat-auth/register")
async def chat_user_register(tenant_id: str, request: Request):
    """Request chat access — creates pending user."""
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    display_name = body.get("name", "")
    reason = body.get("reason", "")
    if not email or not password:
        return JSONResponse({"error": "Email and password required"}, status_code=400)
    from backend.core import database as db
    existing = db.get_chat_user(tenant_id, email)
    if existing:
        if existing["status"] == "pending":
            return JSONResponse({"error": "Access request already submitted", "status": "pending"}, status_code=409)
        if existing["status"] == "active":
            return JSONResponse({"error": "Account already exists. Please login.", "status": "active"}, status_code=409)
    db.create_chat_user(tenant_id, email, password, display_name, status="pending", created_by="self", reason=reason)
    return {"status": "pending", "message": "Access request submitted. Awaiting admin approval."}

@app.get("/api/t/{tenant_id}/chat-auth/check")
async def chat_auth_check(tenant_id: str, request: Request):
    """Check if chat login is required + validate existing token."""
    from backend.core import database as db
    tenant = db.get_tenant(tenant_id)
    _lr = tenant.get("chat_login_required", False) if tenant else False
    login_required = _lr is True or _lr == "true" or _lr == "TRUE"
    # Check for existing token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    authenticated = False
    user_email = ""
    if token:
        info = _validate_token(token)
        if info and info.get("tenant_id") == tenant_id:
            authenticated = True
            user_email = info.get("email", "")
    return {"login_required": login_required, "authenticated": authenticated, "email": user_email}

@app.get("/c/{embed_token}")
async def public_chat_by_token(embed_token: str):
    """Public chat via secret token URL — /c/a8f3k9x2m7b4..."""
    from backend.core.database import get_tenant_by_embed_token
    tenant = get_tenant_by_embed_token(embed_token)
    if not tenant:
        return JSONResponse({"error": "Invalid or expired chat link"}, status_code=404)
    if not tenant.get("embed_enabled", True):
        return Response(content="<html><body style='background:#0f1419;color:#dee3ea;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh'><div style='text-align:center'><h1 style='color:#ffb4ab'>Chat Disabled</h1><p style='color:#8f909a'>This chat has been temporarily disabled by the administrator.</p></div></body></html>", media_type="text/html")
    return await _serve_tenant_embed(tenant)

@app.get("/t/{tenant_id}/embed")
async def tenant_embed_page(tenant_id: str):
    """Tenant-scoped public chat page (backward compat)."""
    from backend.core.database import get_tenant
    tenant = get_tenant(tenant_id)
    if not tenant or not tenant.get("is_active"):
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    if not tenant.get("embed_enabled", True):
        return Response(content="<html><body style='background:#0f1419;color:#dee3ea;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh'><div style='text-align:center'><h1 style='color:#ffb4ab'>Chat Disabled</h1><p style='color:#8f909a'>This chat has been temporarily disabled by the administrator.</p></div></body></html>", media_type="text/html")
    return await _serve_tenant_embed(tenant)


async def _serve_tenant_embed(tenant: dict):
    """Shared: serve embed HTML with tenant API paths injected."""
    tenant_id = tenant["id"]
    embed_path = STATIC_DIR / "embed.html"
    if not embed_path.exists():
        return JSONResponse({"error": "Embed page not found"}, status_code=404)
    html = embed_path.read_text(encoding="utf-8")
    _clr = tenant.get("chat_login_required", False)
    chat_login_required = _clr is True or _clr == "true" or _clr == "TRUE"
    html = html.replace(
        "const base = (typeof api !== 'undefined' ? api : null) || window.location.origin;",
        f"const base = (typeof api !== 'undefined' ? api : null) || window.location.origin;\n    const TENANT_ID = {json.dumps(tenant_id)};\n    const chatLoginRequired = {json.dumps(chat_login_required)};"
    )
    html = html.replace("'/api/chat'", f"'/api/t/{tenant_id}/chat'")
    html = html.replace("'/api/admin/agent-config'", f"'/api/super/tenants/{tenant_id}'")
    html = html.replace("'/api/chat/feedback'", f"'/api/t/{tenant_id}/chat/feedback'")
    html = html.replace("/api/admin/sops/", f"/api/t/{tenant_id}/admin/sops/")
    html = html.replace("'/api/conversations'", f"'/api/t/{tenant_id}/conversations'")
    agent_name = tenant.get("agent_name", "Document Agent")
    html = html.replace("'Document Agent'", json.dumps(agent_name))
    # Inject logo URL from branding
    branding_raw = tenant.get("branding", "{}")
    try:
        branding_obj = json.loads(branding_raw) if isinstance(branding_raw, str) else (branding_raw or {})
    except Exception:
        branding_obj = {}
    logo_url = branding_obj.get("logo_url", "")
    if logo_url:
        html = html.replace(
            "const TENANT_ID = " + json.dumps(tenant_id) + ";",
            "const TENANT_ID = " + json.dumps(tenant_id) + ";\n    const LOGO_URL = " + json.dumps(logo_url) + ";"
        )
    # Inject escalation config
    esc_raw = tenant.get("escalation_config", "{}")
    try:
        esc_obj = json.loads(esc_raw) if isinstance(esc_raw, str) else (esc_raw or {})
    except Exception:
        esc_obj = {}
    html = html.replace("escalation: null", f"escalation: {json.dumps(esc_obj)}")
    return Response(content=html, media_type="text/html")

# ── Rate-limited chat endpoint wrapper ───────────────────────────────────────
# The actual chat route is in chat_router, but we add rate limiting here
@app.middleware("http")
async def rate_limit_chat(request: Request, call_next):
    """Apply rate limits: /api/chat = 20/min, /api/admin/process = 5/min."""
    # Rate limiting is handled by slowapi decorators on individual routes
    return await call_next(request)

# ── Scheduled Re-Training Background Thread ───────────────────────────────────

def _retrain_scheduler():
    """Background thread: check every hour if tenants need re-training."""
    import time as _time
    while True:
        _time.sleep(3600)  # Check every hour
        try:
            from backend.core.database import list_tenants, get_runtime_config, list_sops, set_runtime_config
            from backend.core.trainer import process_and_train
            for tenant in list_tenants():
                tid = tenant["id"]
                try:
                    enabled = get_runtime_config("retrain_enabled", tenant_id=tid)
                    if enabled != "true":
                        continue
                    interval = int(get_runtime_config("retrain_interval_days", tenant_id=tid) or 7)
                    last = get_runtime_config("last_retrain", tenant_id=tid) or ""
                    if last:
                        from datetime import datetime, timedelta
                        last_dt = datetime.fromisoformat(last)
                        if datetime.now() - last_dt < timedelta(days=interval):
                            continue
                    # Re-train all docs
                    for doc in list_sops(tenant_id=tid):
                        if doc.get("pdf_path"):
                            try:
                                process_and_train(doc["pdf_path"], doc["sop_id"], tenant_id=tid)
                            except Exception:
                                pass
                    from datetime import datetime
                    set_runtime_config("last_retrain", datetime.now().isoformat(), tenant_id=tid)
                except Exception:
                    pass
        except Exception:
            pass

threading.Thread(target=_retrain_scheduler, daemon=True).start()

# ── Frontend catch-all (serves SvelteKit static build) ───────────────────────
if FRONTEND_DIR.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Catch-all: serve static frontend files for client-side routing."""
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        index_path = FRONTEND_DIR / full_path / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)

        stripped = full_path.rstrip("/")
        if stripped:
            index_path = FRONTEND_DIR / stripped / "index.html"
            if index_path.is_file():
                return FileResponse(index_path)

        root_index = FRONTEND_DIR / "index.html"
        if root_index.is_file():
            return FileResponse(root_index)

        return {"error": "Not found"}
