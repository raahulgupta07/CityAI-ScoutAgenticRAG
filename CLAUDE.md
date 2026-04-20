# Scout Agentic RAG

## Overview
Multi-tenant document intelligence platform with AI-powered chat. Each tenant gets isolated documents, a configurable AI agent, admin panel, and embeddable public chat. Brutalist/Newspaper UI design system. Schema-per-tenant PostgreSQL isolation. 6-layer learning system (intent routes, wiki, vector search, Agno LearningMachine, feedback learning, agent persona).

## Tech Stack
- **Backend:** FastAPI + Agno agent framework (Python 3.11)
- **Super Admin Frontend:** SvelteKit + Tailwind CSS
- **Tenant Admin:** Standalone HTML (Brutalist/Newspaper design, 6-tab panel)
- **Chat Widget:** Shared `chat-widget.js` (45KB) — single source of truth for admin + public chat
- **Agent:** Agno with 11 tools + self-learning discovery + feedback learning + configurable per tenant
- **Database:** PostgreSQL 18 + PgVector (schema-per-tenant) + DB-backed auth
- **Vision:** Gemini 3 Flash (multimodal) via OpenRouter
- **LLM:** Gemini 2.0 Flash (pipeline), Gemini 3 Flash (chat) via OpenRouter — env-configurable
- **Embeddings:** text-embedding-3-small via OpenRouter
- **Document Engine:** AI structuring + Mermaid diagrams + python-docx
- **Wiki Layer:** Karpathy LLM Wiki pattern — cross-document knowledge synthesis
- **Monitoring:** Command center + cost tracking + audit trail + tenant deep dive
- **Deploy:** Docker Compose (2 containers: scoutrag-db + scoutrag-api)
- **Design:** Brutalist/Newspaper — Space Grotesk, #feffd6 surface, #383832 ink, #00fc40 CTA, zero border-radius

## Architecture

```
SUPER ADMIN (SvelteKit)
├── /              → Tenant management (create, edit, delete)
├── /monitoring    → Command Center (live queries, costs, alerts)
├── /monitoring/X  → Tenant Deep Dive (full analytics)
├── /system        → DB Infrastructure (schemas, row counts)
└── /settings      → Platform Config

TENANT ADMIN (standalone HTML + chat-widget.js)
├── /t/{id}/admin  → 6-tab admin panel
├── /t/{id}/embed  → Public chat (if enabled)
└── /c/{token}     → Secret chat URL (if enabled)

FASTAPI BACKEND (:8080)
├── /api/auth/*                    → Login (super + tenant)
├── /api/super/*                   → Super admin (tenant CRUD, monitoring, config)
├── /api/t/{tenant_id}/chat        → Tenant chat (SSE streaming)
├── /api/t/{tenant_id}/admin/*     → Tenant admin (docs, process, wiki, feedback)
├── /api/t/{tenant_id}/images/*    → Tenant-scoped screenshots
├── /api/t/{tenant_id}/conversations/* → Tenant chat history
└── /static/chat-widget.js         → Shared chat component

POSTGRESQL 18 + PGVECTOR
├── public schema   → tenants, auth_tokens, usage_log, audit_log, alerts
├── "{tenant}" schema → sops, page_content, embeddings, screenshots,
│                       intent_routes, wiki_pages, categories, compliance,
│                       query_log, conversations, runtime_config
└── /data/tenants/{id}/ → uploads, pdfs, screenshots, standardized, previews
```

## Chat Widget (chat-widget.js) — Single Source of Truth

Both admin and public chat use the same shared widget. Change once, both update.

```js
ChatWidget.init({
    mode: 'admin' | 'public',
    container: element,
    chatApi: '/api/t/TENANT/chat',
    tenantId: 'my-tenant',
    adminApi: '/api/t/TENANT/admin',  // admin only
    allDocs: [],                       // admin only
    agentName: 'ITSM Agent',
});
```

Features: SSE streaming, inline citations [REF:doc:page], screenshot rendering [IMG:page:idx] (max 400px), PDF viewer with page images (eager-load near target, X-Total-Pages header), source badges, feedback (thumbs up/down with reason popup), copy, export chat, starter question cards (from trained Q&A), follow-up suggestions, multi-turn history, localStorage persistence, scroll-to-bottom, mobile responsive.

## 6-Layer Learning System

```
QUERY ARRIVES
    │
    ▼
Layer 1: Intent Routes (0.2s) — keyword→document direct mapping
    │     Sources: auto, discovered, feedback, negative
    ▼
Layer 2: Wiki Pages (0.1s) — cross-document synthesized knowledge
    │     hit_count ranking, contradiction detection
    ▼
Layer 3: Vector Search (1-3s) — PgVector semantic similarity
    │
    ▼
Layer 4: Agno LearningMachine — decision logs, conversation memory
    │
    ▼
Layer 5: Feedback Learning — 👍 creates intent routes, 👎 creates negative routes
    │
    ▼
Layer 6: Agent Persona — auto-generated from document analysis
```

## Feedback Learning Loop

- **👍 Thumbs Up:** Creates intent route (`source="feedback"`) per source doc, bumps wiki hit_count, audit logged. Future similar queries skip vector search (0.2s vs 3.5s).
- **👎 Thumbs Down:** Shows reason popup (Wrong answer, Missing info, Wrong document, Too vague + free text). Creates negative route (`source="negative"`). Shows in admin dashboard "Needs Attention".
- **Dashboard:** Thumbs Up count, Thumbs Down count, Satisfaction %, Needs Attention (clickable → shows downvoted queries with reasons).

## Tenant Admin Panel (6 tabs)
1. **Dashboard** — Bento metrics, feedback stats (thumbs up/down, satisfaction %), document quality, needs attention
2. **Documents** — Multi-file upload, document library with Train/Re-Train/Standardize actions, Train All button, full-text search across page content, document versioning (v1→v2 chain), document detail (7 tabs: Overview, PDF, Standardized, Screenshots, Knowledge, Wiki, Compliance)
3. **Chat** — Shared chat widget + context panel, starter question cards (ChatGPT-style, from trained Q&A pairs), inline screenshots
4. **Logs** — Query metrics, live stream, feedback tracking, answer quality scores
5. **Config** — Agent persona, tone/style/role, auto-generate from documents
6. **Embed** — Enable/disable, public URL, widget code, iframe code, preview
7. **Pipeline Terminal** — Persistent bottom bar visible across all tabs, SSE streaming of training progress, auto-resumes on page refresh

## Starter Question Cards
ChatGPT-style 2×2 card grid on welcome screen. Questions sourced from:
- `sops.qa_pairs` — 30-50 Q&A pairs generated during knowledge extraction (pipeline step 5)
- `intent_routes` — queries discovered during auto-training (pipeline steps 9-11)
Cards are filtered (15-120 chars), deduplicated, shuffled randomly on each load. More docs = more diverse cards. Clicking a card sends the question immediately.

## Document Processing Pipeline (18 steps)

```
Upload → Process Document
  1. AI Categorize
  2. Text/Vision Extract
  3. Screenshots 300 DPI
  4. Enhance (steps + FAQs)
  5. Knowledge Extract (30-50 Q&A pairs with answers + page refs)
  6. Embed in PgVector
  7. Compliance Check (0-100)
→ Auto-Training
  8. Run Q&A pairs through agent (parallel)
→ Self-Learning Discovery
  9. Generate 15 diverse queries
  10. Run through agent → save_discovery
  11. Save keyword→document routes
→ SOP Standardization (if mode=sop)
  12. AI structures (McKinsey/Deloitte format)
  13. Mermaid workflow diagram
  14. Create DOCX
→ Re-Embed
  15. Merge [STANDARDIZED] + [ORIGINAL]
  16. Re-embed combined content
  17. Update summary
→ Wiki Synthesis
  18. Extract entities → create/merge wiki pages
```

## API Routes

### Tenant Admin (`/api/t/{tenant_id}/admin/*`)
```
GET    /stats               → Tenant stats (includes thumbs_up, thumbs_down)
GET    /sops                → List documents
GET    /sops/{id}           → Document detail
POST   /upload              → Upload PDF/DOCX/XLSX
POST   /upload-multiple     → Upload multiple files at once
POST   /process/{id}        → Run pipeline (blocking)
POST   /process/{id}/stream → Run pipeline with SSE progress
GET    /search?q=term       → Full-text search across all page content
GET    /sops/{id}/versions  → Document version history
GET    /sops/{id}/pages/{n} → Render page as PNG (case-insensitive + O/0 normalization)
GET    /logs                → Query logs
GET    /logs/downvoted      → Downvoted queries for review
GET    /wiki                → List wiki pages
GET    /wiki/{id}           → Wiki page detail
POST   /wiki/lint           → Wiki health check
POST   /generate-persona    → Auto-generate agent persona from documents
POST   /extract-knowledge/{id} → Extract Q&A from document
```

### Tenant Chat (`/api/t/{tenant_id}/*`)
```
POST /chat                  → SSE streaming chat (with history support)
PUT  /chat/feedback         → Feedback with learning (creates intent/negative routes)
POST /conversations         → Create conversation
GET  /conversations         → List conversations
```

## New API Routes (v2)

### Tenant Admin (`/api/t/{tenant_id}/admin/*`)
```
POST   /upload-multiple      → Upload multiple files at once
POST   /process/{id}/stream  → SSE streaming pipeline progress (training continues on disconnect)
GET    /search?q=term        → Full-text search across all page content with highlighted snippets
GET    /sops/{id}/versions   → Document version history (linked list chain)
GET    /starter-questions    → Random starter questions from trained Q&A pairs + intent routes
GET    /training/logs        → Poll training status and logs (resumes on page refresh)
```

### Health (`/api/health`)
```
GET    /api/health → Deep health check: DB latency, disk free, memory RSS, OpenRouter key, uptime
```

## Security
- **XSS:** `esc()` in chat widget + tenant-admin.html, `json.dumps()` for JS injection
- **Auth:** DB-backed tokens, 24h expiry, tenant-scoped. Cross-tenant validation (token tenant_id must match URL tenant_id). Constant-time password comparison (hmac.compare_digest). Token cache auto-pruned hourly.
- **CORS:** Credentials disabled with wildcard origins
- **SQL:** Parameterized queries throughout, `_sanitize_tenant_id()` regex validation
- **Connections:** Connection pool (psycopg_pool, min=2, max=10) + try/finally on all 46 DB functions
- **Path traversal:** Validated resolved paths stay within tenant directory
- **O/0 normalization:** Everywhere LLM text matches DB IDs — agent.py, trainer.py, tools.py, chat-widget.js, database.py
- **Concurrent processing:** Document-level lock prevents double-processing
- **SSE cleanup:** Agent tasks cancelled on client disconnect, no zombie threads
- **PyMuPDF:** All fitz.open() wrapped in try/finally to prevent file handle leaks
- **Agent pool:** Thread-safe with double-check locking

## Production Infrastructure
- **Connection Pooling:** psycopg_pool (min=2, max=10, timeout=30) — conn.close() returns to pool via _PooledConnection wrapper
- **Retry Logic:** `call_openrouter()` with 3 retries + exponential backoff for 429/500/timeout
- **Structured Logging:** JSON format (timestamp, level, logger, message, tenant_id, request_id) via contextvars
- **Health Check:** Deep `/api/health` — DB latency, disk space, memory RSS, OpenRouter key, uptime
- **Hybrid Retrieval:** BM25 full-text + PgVector vector search merged with Reciprocal Rank Fusion
- **Chunk Embeddings:** Pages split into 400-token chunks with overlap for better retrieval precision
- **Answer Quality:** Auto-scored 0-100 (citations, length, sources, formatting, confidence)

## Environment Variables
```bash
OPENROUTER_API_KEY=sk-or-v1-...    # Required (all LLM calls go through OpenRouter)
DB_PASS=strong-password             # Required
ADMIN_USER=admin                    # Super admin login
ADMIN_PASS=change-me
PORT=80
DB_USER=scoutrag
DB_DATABASE=scoutragdb

# Optional — Override models without redeploying
ROUTER_MODEL=google/gemini-2.0-flash-001        # Pipeline (categorize, extract, wiki, standardize)
VISION_MODEL=google/gemini-3-flash-preview       # Chat + vision
EMBEDDING_MODEL=text-embedding-3-small           # Embeddings
LOG_LEVEL=INFO                                    # Logging level
```

## Bugs Fixed (v2)

| # | Bug | Root Cause | Fix |
|---|-----|-----------|-----|
| 1 | Click page 5, see page 1 | `loading="lazy"` on all images + 200ms scroll timeout | Eager-load pages near target, min-height on containers, scroll after image load |
| 2 | Pages 7-10 "Failed to load" | O/0 mismatch in source extraction → empty sources → pageCount defaults to 10 | O/0 normalization in agent.py + X-Total-Pages header from backend |
| 3 | O/0 mismatch in trainer.py | LLM writes "OO1" but DB has "001" — training/discovery checks failed | Added _norm() lambda in both training and discovery checks |
| 4 | 46 DB connection leaks | No try/finally on get_db() calls | Wrapped all 46 functions in try/finally |
| 5 | PyMuPDF file handle leaks | fitz.open() without guaranteed close | try/finally in 4 files |
| 6 | Agent pool race condition | Global _agents dict accessed without lock | Threading.Lock with double-check locking |
| 7 | Cross-tenant data access | Tenant-A token could access tenant-B admin endpoints | Token tenant_id validated against URL path |
| 8 | Admin GET routes unprotected | Auth removed for all GET /admin/ routes | Auth required for all /admin/ (except /pages/ for img tags) |
| 9 | XSS in tenant admin | d.title, d.sop_id unescaped in innerHTML | Added esc() function, escaped all user data |
| 10 | Concurrent doc processing | Double-click = corrupted embeddings | Document-level lock prevents re-entry |
| 11 | Token cache memory leak | Tokens never pruned from in-memory cache | Hourly auto-prune of expired tokens |
| 12 | SSE zombie threads | Agent tasks continue after client disconnect | Cancel task on disconnect, proper cleanup |
| 13 | Connection pool exhaustion | conn.close() destroyed connections instead of returning to pool | _PooledConnection wrapper calls pool.putconn() |
| 14 | JS syntax error broke all login | Extra } brace in bulkTrain() function | Removed stray brace |
| 15 | PDF pages fail to load (auth) | Security fix blocked /pages/ img requests that can't send headers | Exempted /pages/ and /preview from auth |
| 16 | Suggestion buttons unclickable behind PDF | PDF panel z-index:100 overlapped chat root | Chat root z-index:101 |
| 17 | Standardize ignores pages 9-50 | Content capped at 12K chars total | Chunked processing: 10 pages/chunk, merge, final summary pass |
| 18 | Preview models will break | Hardcoded model IDs | Env-configurable ROUTER_MODEL, VISION_MODEL, EMBEDDING_MODEL |
| 19 | No retry on LLM calls | Single 429/500 = pipeline failure | call_openrouter() with 3 retries + exponential backoff |

## File Structure
```
├── backend/
│   ├── main.py                 FastAPI + auth + CORS + static serving
│   ├── static/
│   │   ├── chat-widget.js      Shared chat component (admin + public)
│   │   ├── tenant-admin.html   6-tab admin panel (Brutalist design)
│   │   ├── embed.html          Public chat wrapper (loads chat-widget.js)
│   │   └── widget.js           Embeddable widget (iframe)
│   ├── routes/
│   │   ├── super_admin.py      Tenant CRUD + monitoring
│   │   ├── tenant_admin.py     Documents + wiki + feedback + knowledge
│   │   ├── chat.py             SSE streaming + feedback learning
│   │   └── ingest.py           Bulk ingestion
│   ├── core/
│   │   ├── agent.py            Per-tenant agent pool + persona + 11 tools
│   │   ├── config.py           Environment + instance.yaml
│   │   ├── database.py         PostgreSQL + PgVector + schema-per-tenant
│   │   ├── tools.py            11 agent tools (search, wiki, discovery, negative)
│   │   ├── wiki.py             Wiki knowledge layer (synthesize, query, lint, persona)
│   │   ├── pipeline.py         18-step document processing
│   │   ├── trainer.py          Auto-train + discovery + standardize
│   │   ├── knowledge_extract.py 30-50 Q&A pairs with answers + page refs
│   │   └── ...                 (categorize, vision, enhance, compliance, etc.)
│   └── evals/                  Test cases + eval runner
├── frontend/src/routes/        SvelteKit super admin
├── compose.yaml                2 services: scoutrag-db + scoutrag-api
├── Dockerfile                  Multi-stage build
└── .env                        Secrets
```

## Docker
```bash
docker compose up -d          # Start (port 8080)
docker compose down           # Stop
docker compose up -d --build  # Rebuild + restart
docker compose logs -f        # Watch logs
```

## Credentials
- Super Admin: http://localhost:8080 — admin / admin123
- ITSM Tenant: http://localhost:8080/t/itsm-operations/admin — itsm_admin / itsm2026
- Public Chat: http://localhost:8080/c/rXFGKxqWspTJM72k_-8GLzLLT0jeiL2M
