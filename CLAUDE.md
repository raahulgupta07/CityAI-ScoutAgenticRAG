# Scout Agentic RAG

## Overview
Multi-tenant document intelligence platform with AI-powered chat. Each tenant gets isolated documents, a configurable AI agent (12 tools), admin panel, and embeddable public chat. Schema-per-tenant PostgreSQL isolation. 6-layer learning system. Brutalist/Newspaper UI.

## Tech Stack
- **Backend:** FastAPI + Agno agent framework (Python 3.11)
- **Super Admin:** SvelteKit + Tailwind CSS
- **Tenant Admin:** Standalone HTML (Brutalist design, 6-tab panel)
- **Chat Widget:** Shared `chat-widget.js` — single source for admin + public chat (side-by-side PDF viewer)
- **Agent:** Agno with 12 tools + self-learning + feedback learning + visual PDF reading
- **Database:** PostgreSQL 18 + PgVector (schema-per-tenant) + connection pool (psycopg_pool)
- **LLM (pipeline):** Gemini 3.1 Flash Lite via OpenRouter — env-configurable
- **LLM (chat):** Gemini 3 Flash via OpenRouter — env-configurable
- **LLM (fallback):** Gemini 2.0 Flash — auto-switches if primary model fails
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
ROUTER_MODEL=google/gemini-3.1-flash-lite-preview  # Pipeline + standardize model
VISION_MODEL=google/gemini-3-flash-preview          # Chat + vision model
FALLBACK_MODEL=google/gemini-2.0-flash-001          # Auto-fallback if primary fails
EMBEDDING_MODEL=text-embedding-3-small               # Embedding model
LOG_LEVEL=INFO                                       # Logging level
```

## Architecture
```
SUPER ADMIN (SvelteKit)          TENANT ADMIN (HTML)           PUBLIC CHAT
/  /monitoring  /system          /t/{id}/admin (6 tabs)        /c/{token}
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

Visual step tracker: `[CAT] [VIS] [SCR] [ENH] [SAVE] [Q&A] [EMB] [CHK] [TRAIN] [WIKI]`
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
→ Auto-embeds standardized content (pages 900+) for chat search
→ 100+ page documents supported (chunked LLM calls, 5s gaps)
```

Both raw (pages 1-N) and standardized (pages 900+) content are searchable in chat.
Recommended workflow: Standardize first → then Train for best search quality.

## 5-Layer Error Defense
```
Layer 1: Smart Retries     — 7 retries, 10-90s backoff for 429s
Layer 2: Fallback Model    — auto-switch to gemini-2.0-flash if primary fails
Layer 3: JSON Repair       — fix truncated LLM output instead of crashing
Layer 4: Graceful Skip     — failed chunk/step skipped, pipeline continues
Layer 5: Honest Status     — errors show ERROR not fake "COMPLETE"
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
| read_page_visual | Render PDF page as image, send to Gemini vision |

## Follow-up Suggestions (Hybrid)
Instant DB Q&A pairs + LLM-generated (3s timeout). Always fast, never blocks.

## Chat Widget
Shared `chat-widget.js` powers both admin and public chat:
- SSE streaming with tool step visualization
- Starter question cards (2x2 grid from trained Q&A)
- Inline citations `[REF:doc:page]` → clickable, opens side-by-side PDF viewer
- Screenshots `[IMG:page:index]` → rendered inline
- PDF viewer opens on right, chat shrinks to left (no overlap)
- Feedback with reason popup
- Follow-up suggestions (hybrid: DB instant + LLM smart)
- Export as PDF
- Multi-turn conversation history
- localStorage persistence (1hr TTL)
- Mobile responsive

## Document Library Features
- **Pin/Star** — pinned docs sort to top (persisted in DB)
- **Bulk Delete** — checkbox select + "Delete Selected"
- **Tags** — add/remove custom tags, filter by tag
- **Train All** — one-click bulk training for all pending docs
- **Standardize All** — bulk standardization
- **Full-text Search** — search across all page content with highlights
- **Document Versioning** — upload v2 keeps v1 history

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
GET    /admin/sops/{id}/download/docx → Download standardized DOCX
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
- **Downloads:** `/download/` paths exempted from auth for browser access

## Production Infrastructure
- Connection pooling (psycopg_pool) with `_PooledConnection` wrapper
- `call_openrouter()` — 5-7 retries, exponential backoff (10s→90s), fallback model
- JSON repair for truncated LLM responses
- Structured JSON logging (timestamp, level, tenant_id, request_id)
- Deep health check endpoint
- Training continues on page refresh (background task)
- Rate limit delays between pipeline LLM calls (5s gaps)

## Docker
```bash
docker compose up -d --build     # Build + start
docker compose down              # Stop
docker compose down -v           # Stop + delete data
docker compose logs -f           # Watch logs
```
