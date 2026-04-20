# Scout Agentic RAG

Multi-tenant document intelligence platform with AI-powered chat. Each company gets isolated AI agents, documents, admin panel, and embeddable public chat. Self-learning RAG with 6-layer learning system, wiki knowledge layer, feedback learning loop, and Brutalist/Newspaper UI.

## Quick Start

```bash
cp .env.example .env
# Edit: OPENROUTER_API_KEY, DB_PASS, ADMIN_USER, ADMIN_PASS
docker compose up -d --build
open http://localhost:8080
```

**Default credentials:**
- Super Admin: `admin` / `admin123`
- Create tenants at the super admin dashboard

## How It Works

1. **Super admin** creates a tenant (company) at `/`
2. **Tenant admin** uploads documents at `/t/{id}/admin`
3. **18-step pipeline** processes: categorize → vision extract → screenshots → enhance → knowledge (30-50 Q&A) → embed → compliance → auto-train → self-learn → standardize → wiki synthesis
4. **Users chat** at `/c/{token}` — agent answers from documents only, with inline citations and page screenshots
5. **Agent self-learns** — saves successful routes, learns from user feedback, gets faster with every query

## Architecture

```
Super Admin (SvelteKit)     Tenant Admin (HTML)        Public Chat
/  /monitoring  /system     /t/{id}/admin (6 tabs)     /c/{token}
        │                           │                      │
        └───────────────────────────┼──────────────────────┘
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI Backend (:8080)                                      │
│  ├── /api/super/*          → Tenant CRUD + monitoring         │
│  ├── /api/t/{id}/admin/*   → Docs, wiki, feedback, knowledge │
│  ├── /api/t/{id}/chat      → SSE streaming + feedback learning│
│  └── /static/chat-widget.js → Shared chat (admin + public)   │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  PostgreSQL 18 + PgVector                                     │
│  ├── public schema  → tenants, auth_tokens, usage_log, audit │
│  ├── "{tenant}" schema → sops, embeddings, intent_routes,    │
│  │                       wiki_pages, query_log, conversations │
│  └── /data/tenants/{id}/ → pdfs, screenshots, standardized   │
└──────────────────────────────────────────────────────────────┘
```

## 6-Layer Learning System

| Layer | Speed | Cost | How |
|-------|-------|------|-----|
| Intent Routes | 0.2s | $0 | Keyword → document direct mapping |
| Wiki Knowledge | 0.1s | $0 | Cross-document entity synthesis (Karpathy pattern) |
| Vector Search | 1-3s | $0 | PgVector semantic similarity |
| Agno LearningMachine | - | $0 | Decision logs + conversation memory |
| Feedback Learning | 0.2s | $0 | 👍 creates routes, 👎 creates negative routes |
| Agent Persona | - | $0.003 | Auto-generated system prompt from all documents |

## Feedback Learning

- **👍 Thumbs Up** — instant. Creates intent route (`source="feedback"`), bumps wiki hits. Future similar queries skip vector search.
- **👎 Thumbs Down** — popup with 4 reasons + free text. Creates negative route. Shows in dashboard "Needs Attention".

## Chat Widget

Single `chat-widget.js` (45KB) powers both admin and public chat:

- SSE streaming with tool step visualization
- Inline citations `[REF:doc:page]` → clickable, opens PDF viewer
- Screenshots `[IMG:page:index]` → rendered inline
- Referenced page thumbnails at end of each answer
- PDF viewer with page images (slide-in panel)
- Feedback with reason popup
- Multi-turn conversation history
- Export chat as text
- localStorage persistence (1hr TTL)
- Mobile responsive
- Source badges, copy button, suggestions

## Features

- **11-tool Agno agent** — intent routing, wiki search, hybrid vector+BM25 search, page reading, screenshots, discovery, negative learning
- **Hybrid Retrieval** — BM25 full-text + PgVector vector search merged with Reciprocal Rank Fusion (RRF)
- **Chunk-level Embeddings** — pages split into 400-token chunks with overlap for precise retrieval
- **Wiki Knowledge Layer** — cross-document entity synthesis, contradiction detection, hit tracking
- **Document Standardizer** — McKinsey/Deloitte/Accenture/PwC frameworks → DOCX (chunked for 50+ page docs)
- **Document Versioning** — upload v2 keeps v1 history, version chain with UI
- **Multi-file Upload** — drag & drop multiple files, per-file progress status
- **Full-text Search** — search across all page content with highlighted snippets
- **Train All** — one-click bulk training for all untrained documents with SSE progress bars
- **Answer Quality Scoring** — auto-scored 0-100 per response (citations, sources, formatting, confidence)
- **Auto Persona Generation** — analyzes all documents to generate agent system prompt
- **30-50 Q&A pairs** per document with answers and page references
- **Configurable per tenant** — name, role, focus, tone, style, languages, custom prompt
- **18-step pipeline** — vision extract, enhance, knowledge, embed, compliance, train, discover, wiki
- **Real-time Pipeline Progress** — SSE streaming of all 18 steps to admin UI
- **Command Center** — live queries, costs, health, alerts, audit trail
- **Deep Health Check** — DB latency, disk space, memory, OpenRouter status, uptime
- **Structured JSON Logging** — timestamp, level, tenant_id, request_id per log entry
- **Connection Pooling** — psycopg_pool (min=2, max=10) with auto-reset
- **Brutalist/Newspaper UI** — Space Grotesk, zero radius, ink borders, stamp shadows

## Tenant Isolation

| Layer | How |
|-------|-----|
| Database | Schema-per-tenant (`SET search_path`) |
| Files | `/data/tenants/{id}/` per company |
| Agent | Per-tenant instance, tools, learning, persona |
| Config | Tone/style/role/focus per tenant |
| Auth | DB-backed tokens, tenant-scoped, 24h expiry |
| Images | Path traversal protection |
| SSE | Thread-local queues (no cross-tenant leaks) |

## URLs

| URL | Who | What |
|-----|-----|------|
| `/` | Super admin | Tenant management |
| `/monitoring` | Super admin | Command Center |
| `/monitoring/{id}` | Super admin | Tenant deep dive |
| `/t/{id}/admin` | Tenant admin | 6-tab admin panel |
| `/c/{token}` | Public | Chat (if enabled) |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python 3.11) |
| Agent | Agno (11 tools + self-learning + feedback) |
| Super Admin | SvelteKit + Tailwind CSS |
| Tenant Admin | Standalone HTML (Brutalist design) |
| Chat Widget | Shared JS (admin + public) |
| Database | PostgreSQL 18 + PgVector |
| LLM (pipeline) | Gemini 2.0 Flash via OpenRouter (env-configurable) |
| LLM (chat) | Gemini 3 Flash via OpenRouter (env-configurable) |
| Embeddings | text-embedding-3-small via OpenRouter |
| Retrieval | Hybrid BM25 + Vector with RRF fusion |
| Wiki | Karpathy LLM Wiki pattern |
| Auth | bcrypt + DB-backed tokens + cross-tenant validation |
| DB Pool | psycopg_pool (min=2, max=10, auto-reset) |
| Logging | Structured JSON (contextvars for request_id) |
| Deploy | Docker Compose (2 containers) |
| Design | Brutalist/Newspaper (Space Grotesk) |

## Security

| Area | Protection |
|------|-----------|
| XSS | `esc()` in widget + tenant-admin, `json.dumps()` for JS injection |
| Auth | DB-backed tokens, 24h expiry, cross-tenant validation, constant-time comparison |
| CORS | Credentials disabled with wildcard origins |
| SQL | Parameterized queries, `_sanitize_tenant_id()` |
| Connections | Connection pool (psycopg_pool) + try/finally on all 46 DB functions |
| Resources | PyMuPDF try/finally, agent pool locking, SSE disconnect cleanup |
| Uploads | Type whitelist, 50MB limit, disk space check |
| O/0 | LLM letter O vs digit 0 normalized everywhere (agent, trainer, tools, widget, DB) |

## Environment Variables

```bash
OPENROUTER_API_KEY=sk-or-v1-...    # Required (all LLM calls via OpenRouter)
DB_PASS=strong-password             # Required
ADMIN_USER=admin                    # Super admin login
ADMIN_PASS=change-me
DB_USER=scoutrag
DB_DATABASE=scoutragdb
PORT=80

# Optional — Override models without redeploying
ROUTER_MODEL=google/gemini-2.0-flash-001
VISION_MODEL=google/gemini-3-flash-preview
EMBEDDING_MODEL=text-embedding-3-small
LOG_LEVEL=INFO
```

## Commands

```bash
docker compose up -d          # Start (port 8080)
docker compose down           # Stop
docker compose up -d --build  # Rebuild + restart
docker compose logs -f        # Watch logs
```

## License

Private — Scout AI
