# Scout Agentic RAG

Multi-tenant document intelligence platform with AI-powered chat. Each company gets isolated AI agents, documents, admin panel, and embeddable public chat. Self-learning RAG with 6-layer learning system, wiki knowledge layer, feedback learning loop, and Brutalist/Newspaper UI.

## Quick Start

```bash
cp .env.example .env
# Edit: OPENROUTER_API_KEY (required), DB_PASS
docker compose up -d --build
open http://localhost:8080
```

**Default credentials:**
- Super Admin: `admin` / `admin123`
- Create tenants at the super admin dashboard

## How It Works

1. **Super admin** creates a tenant (company) at `/`
2. **Tenant admin** uploads documents at `/t/{id}/admin`
3. Click **TRAIN** → 11-step pipeline: categorize → vision extract → screenshots → enhance → knowledge (30-50 Q&A) → embed → compliance → auto-train → self-learn → wiki
4. Click **STANDARDIZE** (optional) → AI generates consulting-grade DOCX (McKinsey/Deloitte frameworks)
5. **Users chat** at `/c/{token}` — agent answers from documents only, with inline citations and screenshots
6. **Agent self-learns** — saves successful routes, learns from feedback, gets faster with every query

## Architecture

```
Super Admin (SvelteKit)     Tenant Admin (HTML)        Public Chat
/  /monitoring  /system     /t/{id}/admin (7 tabs)     /c/{token}
        │                           │                      │
        └───────────────────────────┼──────────────────────┘
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI Backend (:8080)                                      │
│  ├── /api/super/*          → Tenant CRUD + monitoring         │
│  ├── /api/t/{id}/admin/*   → Docs, train, standardize, wiki  │
│  ├── /api/t/{id}/chat      → SSE streaming + feedback         │
│  ├── /api/health           → Deep health check                │
│  └── /static/chat-widget.js → Shared chat (admin + public)   │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  PostgreSQL 18 + PgVector + Connection Pool                    │
│  ├── public schema  → tenants, auth_tokens, usage_log, audit │
│  ├── "{tenant}" schema → sops, embeddings, intent_routes,    │
│  │                       wiki_pages, query_log, conversations │
│  └── /data/tenants/{id}/ → pdfs, screenshots, standardized   │
└──────────────────────────────────────────────────────────────┘
```

## Training Pipeline (what happens when you click TRAIN)

```
[CAT] → [VIS] → [SCR] → [ENH] → [SAVE] → [Q&A] → [EMB] → [CHK] → [TRAIN] → [WIKI]

1. AI Categorize       → department, category, tags
2. Vision Extract      → text + tables from each page (Gemini vision)
3. Screenshots         → 300 DPI images from PDF
4. Enhance             → FAQs, step-by-step formatting
5. Save to DB          → metadata + page content
6. Knowledge Extract   → 30-50 Q&A pairs with answers + page refs
7. Embed in PgVector   → 400-token chunks with overlap
8. Compliance Check    → quality score 0-100
9. Auto-Training       → run Q&A through agent, create intent routes
10. Discovery          → generate 15 queries, save successful routes
11. Wiki Synthesis     → cross-document entity knowledge
```

Visual step tracker + progress bar + ETA countdown + browser notification when done.

## Features

- **12-tool Agno agent** — intent routing, wiki, hybrid vector+BM25 search, visual PDF reading, screenshots, discovery
- **Hybrid Retrieval** — BM25 full-text + PgVector vector with Reciprocal Rank Fusion
- **Chunk-level Embeddings** — 400-token chunks with overlap
- **Visual PDF Reading** — agent can render PDF pages and send to Gemini vision for charts/tables
- **Document Standardizer** — McKinsey/Deloitte/Accenture/PwC frameworks → DOCX (handles 100+ pages)
- **Document Versioning** — upload v2 keeps v1 history
- **Multi-file Upload** — drag & drop multiple files
- **Pin/Star Documents** — pinned sort to top
- **Bulk Delete** — checkbox select + delete
- **Document Tagging** — custom tags, filter by tag
- **Full-text Search** — search across all page content with highlighted snippets
- **Train All** — one-click bulk training with step tracker + progress bar
- **Training ETA** — countdown based on page count
- **Browser Notification** — beep + notification when training completes
- **Stop Training** — cancel in-progress training
- **Persistent Pipeline Terminal** — fixed bottom bar, visible across all tabs
- **Starter Question Cards** — ChatGPT-style cards from trained Q&A
- **Answer Quality Scoring** — auto-scored 0-100 per response
- **Export Chat as PDF** — print dialog with formatting
- **Follow-up Suggestions** — 3 contextual questions after each answer
- **Analytics Dashboard** — charts, top queries, failed queries
- **Scheduled Re-Training** — daily/weekly/monthly auto-retrain
- **Deep Health Check** — DB, disk, memory, OpenRouter, uptime
- **Structured JSON Logging** — tenant_id + request_id per log
- **Connection Pooling** — psycopg_pool (min=2, max=10)

## 6-Layer Learning System

| Layer | Speed | Cost | How |
|-------|-------|------|-----|
| Intent Routes | 0.2s | $0 | Keyword → document direct mapping |
| Wiki Knowledge | 0.1s | $0 | Cross-document entity synthesis |
| Vector Search | 1-3s | $0 | Hybrid BM25 + PgVector with RRF |
| Agno LearningMachine | - | $0 | Decision logs + conversation memory |
| Feedback Learning | 0.2s | $0 | Thumbs up creates routes, down creates negative |
| Agent Persona | - | $0.003 | Auto-generated system prompt |

## Chat Widget

Single `chat-widget.js` powers both admin and public chat:

- SSE streaming with tool step visualization
- **Starter question cards** — 2x2 grid from trained Q&A
- Inline citations `[REF:doc:page]` → clickable, opens PDF viewer
- Screenshots `[IMG:page:index]` → rendered inline (auto-injected for cited pages)
- PDF viewer with page images (click outside to close)
- Feedback with reason popup
- Follow-up suggestions
- **Export as PDF** — print dialog with formatting
- Multi-turn conversation history
- localStorage persistence (1hr TTL)
- Mobile responsive

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python 3.11) |
| Agent | Agno (12 tools + self-learning + visual PDF reading) |
| Super Admin | SvelteKit + Tailwind CSS |
| Tenant Admin | Standalone HTML (Brutalist design) |
| Chat Widget | Shared JS (admin + public) |
| Database | PostgreSQL 18 + PgVector |
| DB Pool | psycopg_pool (min=2, max=10, auto-reset) |
| LLM (pipeline) | Gemini 2.0 Flash via OpenRouter (env-configurable) |
| LLM (chat) | Gemini 3 Flash via OpenRouter (env-configurable) |
| Embeddings | text-embedding-3-small via OpenRouter |
| Retrieval | Hybrid BM25 + Vector with RRF fusion |
| Wiki | Karpathy LLM Wiki pattern |
| Auth | bcrypt + DB-backed tokens + cross-tenant validation |
| Logging | Structured JSON (contextvars for request_id) |
| Deploy | Docker Compose (2 containers) |
| Design | Brutalist/Newspaper (Space Grotesk) |

## Security

| Area | Protection |
|------|-----------|
| XSS | `esc()` in widget + tenant-admin, `json.dumps()` for JS injection |
| Auth | DB-backed tokens, 24h expiry, cross-tenant validation, constant-time comparison |
| SQL | Parameterized queries, `_sanitize_tenant_id()` |
| Connections | Pool (psycopg_pool) + try/finally on all 46 DB functions |
| Resources | PyMuPDF try/finally, agent pool locking, SSE disconnect cleanup |
| Uploads | Type whitelist, 50MB limit, disk space check |
| O/0 | LLM letter O vs digit 0 normalized everywhere |
| Passwords | Special chars in DB_PASS auto URL-encoded (no more broken connections) |

## Environment Variables

```bash
# Required
OPENROUTER_API_KEY=sk-or-v1-...    # All LLM calls via OpenRouter
DB_PASS=strong-password             # Special chars (@!#$) OK
DB_USER=scoutrag
DB_DATABASE=scoutragdb

# Optional
ADMIN_USER=admin
ADMIN_PASS=admin123
PORT=80
ROUTER_MODEL=google/gemini-2.0-flash-001
VISION_MODEL=google/gemini-3-flash-preview
EMBEDDING_MODEL=text-embedding-3-small
LOG_LEVEL=INFO
```

## Commands

```bash
docker compose up -d --build     # Build + start
docker compose down              # Stop
docker compose down -v           # Stop + delete all data
docker compose logs -f           # Watch logs
curl http://localhost:8080/api/health  # Health check
```

## Testing Checklist

1. **Super Admin** — login, create tenant, see dashboard
2. **Upload** — drag PDF, see TRAIN + DELETE buttons
3. **Train** — click TRAIN, watch step tracker + progress bar + ETA
4. **Standardize** — click STANDARDIZE, watch terminal, download DOCX
5. **Chat** — starter cards, ask question, see citations + screenshots
6. **Public Chat** — open embed URL, same features work
7. **Bulk Ops** — Train All, pin docs, bulk delete, tag filter
8. **Analytics** — Logs tab shows charts + top queries
9. **Health** — `/api/health` returns healthy

## License

Private — Scout AI
