# Scout Agentic RAG

## Overview
Multi-tenant document intelligence platform with AI-powered chat. Each tenant gets isolated documents, a configurable AI agent (12 tools), admin panel, and embeddable public chat. Schema-per-tenant PostgreSQL isolation. 6-layer learning system. Brutalist/Newspaper UI.

## Tech Stack
- **Backend:** FastAPI + Agno agent framework (Python 3.11)
- **Super Admin:** SvelteKit + Tailwind CSS
- **Tenant Admin:** Standalone HTML (Brutalist design, 7-tab panel)
- **Chat Widget:** Shared `chat-widget.js` — single source for admin + public chat
- **Agent:** Agno with 12 tools + self-learning + feedback learning + visual PDF reading
- **Database:** PostgreSQL 18 + PgVector (schema-per-tenant) + connection pool (psycopg_pool)
- **LLM (pipeline):** Gemini 2.0 Flash via OpenRouter — env-configurable
- **LLM (chat):** Gemini 3 Flash via OpenRouter — env-configurable
- **Embeddings:** text-embedding-3-small via OpenRouter
- **Retrieval:** Hybrid BM25 + Vector with RRF fusion + chunk-level embeddings (400 tokens)
- **Deploy:** Docker Compose (2 containers: scoutrag-db + scoutrag-api)
- **Design:** Brutalist/Newspaper — Space Grotesk, #feffd6 surface, #383832 ink, #00fc40 CTA

## Quick Start
```bash
cp .env.example .env
# Edit: OPENROUTER_API_KEY (required)
docker compose up -d --build
open http://localhost:8080
# Login: admin / admin123
```

## Environment Variables
```bash
# Required
OPENROUTER_API_KEY=sk-or-v1-...    # All LLM calls go through OpenRouter
DB_PASS=strong-password             # Database password (special chars OK — auto URL-encoded)
DB_USER=scoutrag
DB_DATABASE=scoutragdb

# Optional
ADMIN_USER=admin                    # Super admin login (empty = no login required)
ADMIN_PASS=admin123
PORT=80                             # Server port
ROUTER_MODEL=google/gemini-2.0-flash-001     # Pipeline model
VISION_MODEL=google/gemini-3-flash-preview    # Chat + vision model
EMBEDDING_MODEL=text-embedding-3-small        # Embedding model
LOG_LEVEL=INFO                                # Logging level
```

## Architecture
```
SUPER ADMIN (SvelteKit)          TENANT ADMIN (HTML)           PUBLIC CHAT
/  /monitoring  /system          /t/{id}/admin (7 tabs)        /c/{token}
        │                                │                         │
        └────────────────────────────────┼─────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (:8080)                                             │
│  ├── /api/auth/*               → Login (super + tenant)              │
│  ├── /api/super/*              → Tenant CRUD + monitoring            │
│  ├── /api/t/{id}/admin/*       → Docs, train, standardize, wiki      │
│  ├── /api/t/{id}/chat          → SSE streaming chat                  │
│  ├── /api/health               → Deep health check                   │
│  └── /static/chat-widget.js    → Shared chat component               │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PostgreSQL 18 + PgVector + Connection Pool (min=2, max=10)          │
│  ├── public schema   → tenants, auth_tokens, usage_log, audit_log    │
│  ├── "{tenant}" schema → sops, page_content, embeddings, screenshots,│
│  │                       intent_routes, wiki_pages, query_log, etc.  │
│  └── /data/tenants/{id}/ → uploads, pdfs, screenshots, standardized  │
└──────────────────────────────────────────────────────────────────────┘
```

## What Happens When You Upload a PDF
1. File saved to `/data/tenants/{id}/uploads/` (~1 second)
2. DB record created with status=Pending
3. TRAIN button appears — user clicks when ready

## What Happens When You Click TRAIN
```
Step 1:  AI Categorize          (~3s)   → department, category, tags
Step 2:  Vision Page Extraction  (~20-60s) → text + tables per page
Step 3:  Screenshot Extraction   (~3s)   → 300 DPI images
Step 4:  Enhance Documentation   (~10-20s) → FAQs, missing info
Step 5:  Save to Database        (~1s)   → metadata + page content
Step 6:  Knowledge Extraction    (~10s)  → 30-50 Q&A pairs
Step 7:  Embed in PgVector       (~5s)   → 400-token chunks
Step 8:  Compliance Check        (~3s)   → quality score 0-100
Step 9:  Auto-Training           (~30-60s) → run Q&A through agent
Step 10: Self-Learning Discovery (~15s)  → 15 diverse queries
Step 11: Wiki Synthesis          (~5s)   → cross-document knowledge

Total: ~2-3 minutes per document
```

Visual step tracker on document row: `[CAT] [VIS] [SCR] [ENH] [SAVE] [Q&A] [EMB] [CHK] [TRAIN] [WIKI]`
Each badge turns green as it completes. Progress bar + percentage + ETA countdown.
Browser notification + beep when training completes.

## What Happens When You Click STANDARDIZE (manual, separate from training)
```
Reads all page_content → sends to AI in 3-page chunks:
  Chunk 1 (p1-3): Full analysis (metadata + procedures)
  Chunk 2 (p4-6): More procedures + definitions
  ...
  Final: Executive summary + Mermaid diagrams
→ Generates DOCX (McKinsey/Deloitte/Accenture/PwC frameworks)
→ Score: original vs standardized (gap analysis)
→ 100+ page documents supported (34 small LLM calls, 3s gaps)
```

## Agent Tools (12)
| Tool | Purpose |
|------|---------|
| search_intents | Instant keyword → document mapping (0.2s) |
| search_wiki | Cross-document synthesized knowledge |
| vector_search_tool | Hybrid BM25 + vector with RRF fusion |
| search_documents | Keyword fallback |
| list_all_documents | Show all docs |
| get_document_summary | Pre-built summary + Q&A |
| get_page_content | Read specific pages |
| get_screenshots | Get [IMG:page:index] tags |
| get_source_overview | Library overview |
| save_discovery | Learn new patterns |
| read_page_visual | **NEW** — render PDF page as image, send to Gemini vision |

## Starter Question Cards
ChatGPT-style 2×2 grid on welcome screen. Sources:
- `sops.qa_pairs` — Q&A pairs from knowledge extraction
- `intent_routes` — queries from auto-training discovery
Shuffled randomly per load. Click sends question immediately.

## Document Library Features
- **Pin/Star** — pinned docs sort to top (persisted in DB)
- **Bulk Delete** — checkbox select + "Delete Selected"
- **Tags** — add/remove custom tags, filter by tag
- **Train All** — one-click bulk training for all pending docs
- **Standardize All** — bulk standardization
- **Full-text Search** — search across all page content with highlights
- **Document Versioning** — upload v2 keeps v1 history

## Analytics Dashboard (Logs tab)
- Stats cards: Total Queries, Avg Response Time, Satisfaction Rate, Low Quality
- Daily query volume chart (pure CSS, last 7 days)
- Top 10 popular queries
- Failed/low quality queries list

## Scheduled Re-Training (Config tab)
Toggle + interval (Daily/Weekly/Monthly). Background thread checks hourly.

## API Routes
```
# Tenant Admin
GET    /admin/stats                → Tenant stats
GET    /admin/sops                 → List documents
POST   /admin/upload               → Upload PDF/DOCX/XLSX
POST   /admin/upload-multiple      → Multi-file upload
POST   /admin/process/{id}/stream  → Train with SSE progress
POST   /admin/process/{id}/stop    → Stop training
POST   /admin/sops/{id}/standardize → Standardize with SSE progress
GET    /admin/sops/{id}/pages/{n}  → Render page as PNG
GET    /admin/sops/{id}/versions   → Version history
PUT    /admin/sops/{id}/pin        → Toggle pin
GET    /admin/search?q=term        → Full-text search
GET    /admin/starter-questions    → Random starter cards
GET    /admin/analytics            → Dashboard data
GET    /admin/schedule             → Re-training schedule
PUT    /admin/schedule             → Set re-training schedule
GET    /admin/training/logs        → Poll training status

# Chat
POST   /chat                       → SSE streaming chat
PUT    /chat/feedback              → Feedback with learning

# Health
GET    /api/health                 → DB, disk, memory, OpenRouter, uptime
```

## Security
- **Auth:** DB-backed tokens, 24h expiry, cross-tenant validation, constant-time comparison
- **XSS:** `esc()` everywhere, `json.dumps()` for JS injection
- **SQL:** Parameterized queries, `_sanitize_tenant_id()` regex
- **Connections:** Pool (min=2, max=10) + try/finally on all 46 DB functions
- **Resources:** PyMuPDF try/finally, agent pool locking, SSE cleanup
- **O/0:** LLM letter O vs digit 0 normalized everywhere
- **Uploads:** Type whitelist, 50MB limit, disk space check
- **Passwords:** Special chars in DB_PASS auto URL-encoded

## Production Infrastructure
- Connection pooling (psycopg_pool) with `_PooledConnection` wrapper
- `call_openrouter()` — 5 retries, exponential backoff (5s→60s)
- Structured JSON logging (timestamp, level, tenant_id, request_id)
- Deep health check endpoint
- Training continues on page refresh (background task)
- Rate limit delays between pipeline LLM calls (3s gaps)

## Docker
```bash
docker compose up -d --build     # Build + start
docker compose down              # Stop
docker compose down -v           # Stop + delete data
docker compose logs -f           # Watch logs
```
