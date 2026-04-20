"""
Configuration for Document Intelligence Agent.
Loads instance.yaml for branding + persona, .env for secrets.
All LLM calls go through OpenRouter — models configurable via env vars.
"""
from __future__ import annotations

import os
import time
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# ── Instance Config (branding, persona, categories) ──────────────────────────
INSTANCE_PATH = PROJECT_ROOT / "instance.yaml"

def _load_instance() -> dict:
    if INSTANCE_PATH.exists():
        with open(INSTANCE_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}

INSTANCE = _load_instance()

# Shortcuts
APP_NAME = INSTANCE.get("app", {}).get("name", "Document Agent")
APP_TAGLINE = INSTANCE.get("app", {}).get("tagline", "Intelligent Curator")
AGENT_CONFIG = INSTANCE.get("agent", {})
WIDGET_CONFIG = INSTANCE.get("widget", {})

# ── Database ─────────────────────────────────────────────────────────────────
# Build DATABASE_URL from individual env vars (handles special chars in password)
# Falls back to DATABASE_URL env var if set directly
def _build_db_url():
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    from urllib.parse import quote_plus
    user = os.getenv("DB_USER", "scoutrag")
    password = quote_plus(os.getenv("DB_PASS", "scoutrag_secret"))
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_DATABASE", "scoutragdb")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"

DATABASE_URL = _build_db_url()

# ── OpenRouter (single LLM gateway) ─────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY is not set — all LLM calls will fail. Set it in .env or environment.")

# ── Models (all via OpenRouter — override via env vars without redeploying) ──
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "google/gemini-2.0-flash-001")      # Categorize + extract + pipeline (fast, stable)
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-3-flash-preview")    # Chat + vision (user-facing, best quality)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")     # OpenAI embeddings for PgVector

# ── Security ─────────────────────────────────────────────────────────────────
ADMIN_USER = os.getenv("ADMIN_USER", "")  # Empty = no login required (dev mode)
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

# ── Settings ─────────────────────────────────────────────────────────────────
MAX_VISION_PAGES = 8

# ── OpenRouter client (shared, with retry) ───────────────────────────────────

def get_openrouter_client():
    """Get OpenAI-compatible client pointing to OpenRouter."""
    from openai import OpenAI
    return OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL, timeout=120)


def call_openrouter(prompt: str, model: str = None, max_tokens: int = 8000,
                    temperature: float = 0.15, messages: list = None,
                    max_retries: int = 3) -> str:
    """Unified OpenRouter call with retry + exponential backoff.
    Use this instead of raw httpx.post or client.chat.completions.create.
    Returns the response text content.
    """
    import httpx
    _model = model or ROUTER_MODEL
    _messages = messages or [{"role": "user", "content": prompt}]

    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={"model": _model, "messages": _messages,
                      "max_tokens": max_tokens, "temperature": temperature},
                timeout=120,
            )
            # Rate limited — wait and retry (longer waits for OpenRouter)
            if resp.status_code == 429:
                wait = min(2 ** attempt * 5, 60)
                logger.warning(f"OpenRouter 429 rate limit, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            # Server error — retry
            if resp.status_code >= 500:
                wait = min(2 ** attempt * 2, 30)
                logger.warning(f"OpenRouter {resp.status_code}, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                wait = min(2 ** attempt * 3, 30)
                logger.warning(f"OpenRouter timeout, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise
        except httpx.HTTPStatusError:
            raise  # Non-retryable HTTP errors (400, 401, 403, etc.)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise
    # All retries exhausted
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ── Structured JSON Logging ──────────────────────────────────────────────────

import contextvars

# Context variables for per-request metadata
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
tenant_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="")


class JSONFormatter(logging.Formatter):
    """Custom JSON log formatter that includes request context."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "tenant_id": tenant_id_var.get(""),
            "request_id": request_id_var.get(""),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def setup_logging() -> None:
    """Configure structured JSON logging on the root logger.

    - Sets log level from LOG_LEVEL env var (default: INFO).
    - Replaces existing root handlers with a single JSON StreamHandler.
    - Suppresses noisy loggers (httpx, httpcore, uvicorn.access) to WARNING.
    """
    import sys

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove any existing handlers on the root logger
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Add JSON handler
    json_handler = logging.StreamHandler(sys.stderr)
    json_handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    root.addHandler(json_handler)

    # Suppress noisy loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
