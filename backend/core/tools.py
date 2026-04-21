"""
Agno tools for the Document Agent.
Factory pattern: make_tools(tenant_id) creates tenant-scoped tools.
Each tool is closed over tenant_id so it only accesses that tenant's data.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional
from queue import Queue
from agno.tools import tool

from backend.core import database as db

# Thread-local status queue — each request thread gets its own queue
_thread_local = threading.local()


def set_status_queue(q: Optional[Queue]):
    """Set the status queue for the current thread (called by chat route)."""
    _thread_local.status_queue = q


def _report(step: str, message: str, detail: str = ""):
    q = getattr(_thread_local, "status_queue", None)
    if q:
        q.put_nowait({"step": step, "message": message, "detail": detail})


def _keyword_search(query: str, tenant_id: str, limit: int = 5) -> list:
    """Full-text (BM25-style) search on page_content and sops tables.

    Returns a list of dicts: [{sop_id, page, content, rank}, ...]
    """
    conn = db.get_db(tenant_id)
    try:
        # Search page_content using enhanced_content / text_content
        rows = conn.execute("""
            SELECT sop_id, page,
                   COALESCE(enhanced_content, text_content, '') AS content,
                   ts_rank(
                       to_tsvector('english', COALESCE(enhanced_content, text_content, '')),
                       plainto_tsquery('english', %s)
                   ) AS rank
            FROM page_content
            WHERE to_tsvector('english', COALESCE(enhanced_content, text_content, ''))
                  @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s
        """, (query, query, limit)).fetchall()

        results = []
        for r in rows:
            content = r["content"] or ""
            results.append({
                "sop_id": r["sop_id"],
                "page": r["page"],
                "content": content[:300],
                "rank": float(r["rank"]),
            })

        # If page_content didn't yield enough, also search sops.search_text
        if len(results) < limit:
            remaining = limit - len(results)
            seen_sops = {r["sop_id"] for r in results}
            sop_rows = conn.execute("""
                SELECT sop_id,
                       ts_rank(
                           to_tsvector('english', search_text),
                           plainto_tsquery('english', %s)
                       ) AS rank
                FROM sops
                WHERE to_tsvector('english', search_text)
                      @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
            """, (query, query, remaining + 5)).fetchall()

            for sr in sop_rows:
                if sr["sop_id"] not in seen_sops and len(results) < limit:
                    results.append({
                        "sop_id": sr["sop_id"],
                        "page": 1,
                        "content": f"[Matched via document-level keywords for {sr['sop_id']}]",
                        "rank": float(sr["rank"]),
                    })
                    seen_sops.add(sr["sop_id"])

        return results
    except Exception:
        return []
    finally:
        conn.close()


def make_tools(tenant_id: str = None) -> list:
    """Create tenant-scoped tool functions. Each tool is closed over tenant_id."""

    @tool(description="Search documents by keywords, tags, or descriptions. Try different keywords if first search returns nothing.")
    def search_documents(query: str) -> str:
        """Search the document library by keyword."""
        _report("search", f"search_documents('{query}')", "Keyword search")
        results = db.list_sops(search=query, tenant_id=tenant_id)
        if not results:
            for word in query.split():
                if len(word) > 2:
                    results = db.list_sops(search=word, tenant_id=tenant_id)
                    if results:
                        break
        if not results:
            return "No documents found. Try different keywords or use list_all_documents to see everything available."
        lines = []
        for r in results[:5]:
            doc_type = r.get('type', '') or r.get('category_id', '')
            summary = r.get('summary_short', '') or r.get('doc_description', '')[:150]
            line = f"- {r['sop_id']}: {r.get('title', '')} | Type: {doc_type} | Dept: {r.get('department', '')} | {summary}"
            caveats = r.get('caveats', [])
            if caveats and isinstance(caveats, list) and len(caveats) > 0:
                line += f"\n  ⚠ Caveats: {'; '.join(str(c) for c in caveats[:3])}"
            lines.append(line)
        return f"Found {len(results)} document(s):\n" + "\n".join(lines)

    @tool(description="List ALL available documents with their titles and departments.")
    def list_all_documents() -> str:
        """List every document in the system."""
        _report("list", "list_all_documents()", "Listing all documents")
        docs = db.list_sops(tenant_id=tenant_id)
        if not docs:
            return "No documents indexed yet."
        lines = []
        for s in docs:
            doc_type = s.get('type', '') or s.get('category_id', '')
            summary = s.get('summary_short', '') or s.get('doc_description', '')[:100]
            lines.append(f"- {s['sop_id']}: {s.get('title', '')} | Type: {doc_type} | {s.get('department', '')} | {s.get('page_count', 0)} pages | {summary}")
        return f"Total: {len(docs)} document(s)\n" + "\n".join(lines)

    @tool(description="Semantic search across all document pages using vector similarity. Finds pages by MEANING, not just keywords.")
    def vector_search_tool(query: str) -> str:
        """Search documents by meaning using PgVector embeddings."""
        _report("vector", f"vector_search('{query}')", "Hybrid search: vector + keyword")
        try:
            from backend.core.config import EMBEDDING_MODEL, get_openrouter_client
            client = get_openrouter_client()
            emb_response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
            query_embedding = emb_response.data[0].embedding

            # --- Vector results ---
            vector_results = db.vector_search(query_embedding, limit=5, tenant_id=tenant_id)

            # --- Keyword (full-text) results ---
            keyword_results = _keyword_search(query, tenant_id, limit=5)

            # --- Reciprocal Rank Fusion ---
            def _rrf_score(rank: int, k: int = 60) -> float:
                return 1.0 / (k + rank)

            # Build a combined score map keyed by (sop_id, page)
            scored: dict[tuple, dict] = {}

            for rank, r in enumerate(vector_results, start=1):
                meta = r.get("metadata", {})
                sop_id = meta.get("sop_id", r.get("sop_id", ""))
                page = meta.get("page", r.get("page", "?"))
                key = (str(sop_id), str(page))
                if key not in scored:
                    scored[key] = {
                        "sop_id": sop_id,
                        "page": page,
                        "content": (r.get("content", ""))[:150],
                        "similarity": round(r.get("similarity", 0), 3),
                        "rrf": 0.0,
                        "sources": [],
                    }
                scored[key]["rrf"] += _rrf_score(rank)
                scored[key]["sources"].append("vector")

            for rank, kr in enumerate(keyword_results, start=1):
                sop_id = kr.get("sop_id", "")
                page = kr.get("page", "?")
                key = (str(sop_id), str(page))
                if key not in scored:
                    scored[key] = {
                        "sop_id": sop_id,
                        "page": page,
                        "content": kr.get("content", "")[:150],
                        "similarity": 0,
                        "rrf": 0.0,
                        "sources": [],
                    }
                scored[key]["rrf"] += _rrf_score(rank)
                scored[key]["sources"].append("keyword")
                # If vector didn't supply content, use keyword's
                if not scored[key]["content"]:
                    scored[key]["content"] = kr.get("content", "")[:150]

            if not scored:
                return "No semantic matches found. Try search_documents for keyword search."

            # Sort by combined RRF score descending, take top 5
            merged = sorted(scored.values(), key=lambda x: x["rrf"], reverse=True)[:5]

            lines = []
            for r in merged:
                src = "+".join(sorted(set(r["sources"])))
                sim_str = f"{r['similarity']} sim" if r["similarity"] else "keyword"
                content_preview = r["content"].replace("\n", " ")
                lines.append(f"- [{src}] {sim_str} | {r['sop_id']} page {r['page']} | {content_preview}")
            return f"Found {len(merged)} hybrid matches (vector+keyword RRF):\n" + "\n".join(lines)
        except Exception as e:
            return f"Vector search error: {e}. Try search_documents as fallback."

    @tool(description="Get the pre-built summary, Q&A pairs, keywords, and key info for a document. Use this FIRST for summary/overview requests.")
    def get_document_summary(sop_id: str) -> str:
        """Get pre-extracted document summary, Q&A pairs, keywords, caveats."""
        _report("summary", f"get_document_summary('{sop_id}')", "Document overview")
        sop = db.get_sop(sop_id, tenant_id=tenant_id)
        if not sop:
            return f"Document {sop_id} not found."
        parts = []
        parts.append(f"Document: {sop.get('title', sop_id)} ({sop.get('page_count', 0)} pages)")
        parts.append(f"Department: {sop.get('department', '—')}")
        short = sop.get("summary_short", "")
        if short: parts.append(f"\nSummary: {short}")
        detailed = sop.get("summary_detailed", "")
        if detailed: parts.append(f"\nDetailed Summary: {detailed}")
        caveats = sop.get("caveats", [])
        if caveats and isinstance(caveats, list): parts.append(f"\nCaveats: {'; '.join(str(c) for c in caveats)}")
        qa = sop.get("qa_pairs", [])
        if qa and isinstance(qa, list):
            parts.append(f"\nKey Questions ({len(qa)}):")
            for q in qa[:10]: parts.append(f"  - {q}")
        kw = sop.get("search_keywords", [])
        if kw and isinstance(kw, list): parts.append(f"\nKeywords: {', '.join(str(k) for k in kw)}")
        page_contents = db.get_page_contents(sop_id, tenant_id=tenant_id)
        if page_contents:
            parts.append(f"\nPage-by-page highlights ({len(page_contents)} pages):")
            for pc in page_contents[:15]:
                key = pc.get("key_info", "")
                text = pc.get("enhanced_content") or pc.get("vision_content") or pc.get("text_content") or ""
                preview = text[:150].replace('\n', ' ') if text else ""
                if key: parts.append(f"  Page {pc['page']}: {key}")
                elif preview: parts.append(f"  Page {pc['page']}: {preview}...")
        return "\n".join(parts)

    @tool(description="Read the actual text content of specific pages from a document. Use tight page ranges like '3-7' for specific questions. For summaries, use get_document_summary instead.")
    def get_page_content(sop_id: str, pages: str) -> str:
        """Read page content — prefers vision-extracted content over raw text."""
        _report("pages", f"get_page_content('{sop_id}', '{pages}')", "Reading pages")
        sop = db.get_sop(sop_id, tenant_id=tenant_id)
        if not sop:
            return f"Document {sop_id} not found."
        page_nums = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    page_nums.extend(range(int(start), int(end) + 1))
                except (ValueError, TypeError): pass
            else:
                try: page_nums.append(int(part))
                except (ValueError, TypeError): pass
        if not page_nums: page_nums = [1, 2, 3]
        page_contents = db.get_page_contents(sop_id, page_nums, tenant_id=tenant_id)
        if page_contents:
            parts = []
            for pc in page_contents:
                text = pc.get("enhanced_content") or pc.get("vision_content") or pc.get("text_content") or ""
                method = "enhanced" if pc.get("enhanced_content") else pc.get("extraction_method", "text")
                section = f"--- Page {pc['page']} ({method}) ---\n{text}"
                tables = pc.get("tables", [])
                if tables and isinstance(tables, list) and len(tables) > 0:
                    section += f"\n\nTables on this page: {json.dumps(tables)}"
                if not pc.get("enhanced_content"):
                    img_desc = pc.get("image_descriptions", [])
                    if img_desc and isinstance(img_desc, list) and len(img_desc) > 0:
                        section += f"\n\nImages on this page: {'; '.join(str(d) for d in img_desc)}"
                if pc.get("key_info") and not pc.get("enhanced_content"):
                    section += f"\n\nKey info: {pc['key_info']}"
                missing = pc.get("missing_info", [])
                if missing and isinstance(missing, list) and len(missing) > 0:
                    section += f"\n\n⚠ Documentation gaps: {'; '.join(str(m) for m in missing)}"
                parts.append(section)
            return "\n\n".join(parts)[:15000]
        return f"No page content available for {sop_id} pages {pages}."

    @tool(description="Get all available screenshots for a document with their page numbers and image URLs.")
    def get_screenshots(sop_id: str) -> str:
        """Get screenshot images for a document."""
        _report("images", f"get_screenshots('{sop_id}')", "Finding screenshots")
        screenshots = db.get_screenshots(sop_id, tenant_id=tenant_id)
        if not screenshots:
            return f"No screenshots available for {sop_id}."
        lines = []
        for page_str, imgs in sorted(screenshots.items(), key=lambda x: int(x[0])):
            for img in imgs:
                lines.append(f"- [IMG:{page_str}:{img['index']}] Page {page_str}, Screenshot {img['index']} ({img['width']}x{img['height']})")
        return f"{len(lines)} screenshots available:\n" + "\n".join(lines)

    @tool(description="Get a high-level overview of the document library: total documents, departments, categories.")
    def get_source_overview() -> str:
        """Get global source registry — what's in the document library."""
        _report("overview", "get_source_overview()", "Library overview")
        stats = db.get_stats(tenant_id=tenant_id)
        sops = db.list_sops(tenant_id=tenant_id)[:100]  # Limit for agent context
        lines = [f"Document Library: {stats['total_indexed']} documents, {stats['total_pages']} pages, {stats['departments']} departments"]
        lines.append("")
        dept_map: dict = {}
        for s in sops:
            dept = s.get("department", "Uncategorized") or "Uncategorized"
            if dept not in dept_map: dept_map[dept] = []
            dept_map[dept].append(s)
        for dept, docs in sorted(dept_map.items()):
            lines.append(f"**{dept}** ({len(docs)} documents):")
            for d in docs[:5]:
                title = d.get("title", d.get("sop_id", ""))
                line = f"  - {d['sop_id']}: {title} ({d.get('page_count', 0)}p)"
                summary = d.get("summary_short", "")[:80]
                if summary: line += f" — {summary}"
                lines.append(line)
            if len(docs) > 5: lines.append(f"  ... and {len(docs) - 5} more")
            lines.append("")
        if not sops:
            lines.append("No documents indexed yet.")
        return "\n".join(lines)

    @tool(description="Search intent routes — instant keyword-to-document mappings. Use this FIRST.")
    def search_intents(query: str) -> str:
        """Search pre-built intent routes (fastest path to answer)."""
        _report("intent", f"search_intents('{query}')", "Intent routing")
        results = db.search_intent_routes(query, tenant_id=tenant_id)
        if not results:
            return "No intent routes matched. Use search_documents as fallback."
        lines = []
        for r in results:
            lines.append(f"- MATCH: {r['sop_id']} | Intent: {r['intent']} | Pages: {r.get('pages', 'all')} | Reason: {r.get('reason', '')}")
        return f"Found {len(results)} intent route(s):\n" + "\n".join(lines)

    @tool(description="Search the knowledge wiki for pre-synthesized cross-document information. Use AFTER search_intents, BEFORE vector_search. Returns wiki pages that combine knowledge from multiple documents.")
    def search_wiki(query: str) -> str:
        """Search wiki — synthesized knowledge across all documents."""
        _report("wiki", f"search_wiki('{query}')", "Wiki knowledge search")
        from backend.core.wiki import wiki_query
        results = wiki_query(query, tenant_id=tenant_id)
        if not results:
            return "No wiki pages found. Try vector_search_tool for semantic search."
        lines = []
        for r in results:
            sources = r.get("sources", [])
            if isinstance(sources, str):
                try: sources = json.loads(sources)
                except: sources = []
            source_ids = ", ".join(s.get("sop_id", "") for s in sources[:5])
            contradictions = r.get("contradictions", [])
            if isinstance(contradictions, str):
                try: contradictions = json.loads(contradictions)
                except: contradictions = []
            warn = f" | ⚠ {len(contradictions)} contradiction(s)" if contradictions else ""
            lines.append(f"--- Wiki: {r['title']} ({r.get('category', '')}) ---\n{r['content'][:1000]}\nSources: {source_ids}{warn}")
        return f"Found {len(results)} wiki page(s):\n\n" + "\n\n".join(lines)

    @tool(description="Save a negative finding: when a search path FAILS, save it to avoid repeating.")
    def save_negative(query: str, where_checked: str, why_failed: str) -> str:
        """Save negative knowledge — what didn't work."""
        _report("save_neg", f"save_negative('{query}')", f"{where_checked}: {why_failed}")
        words = [w.lower() for w in query.split() if len(w) > 2]
        db.upsert_intent_route(intent=f"NEGATIVE: {query}", keywords=words, sop_id=where_checked,
                               pages="", reason=f"DEAD END: {why_failed}", source="negative", tenant_id=tenant_id)
        return f"Saved negative: '{query}' does NOT match '{where_checked}'."

    @tool(description="Save a discovery: when you find that a query maps to a specific document, save it for instant future routing.")
    def save_discovery(query: str, document_id: str, pages: str, reason: str) -> str:
        """Save intent discovery for future instant routing."""
        _report("save", f"save_discovery('{query}' → '{document_id}')", "Learning new route")
        words = [w.lower() for w in query.split() if len(w) > 2]
        db.upsert_intent_route(intent=query, keywords=words, sop_id=document_id,
                               pages=pages, reason=reason, source="discovered", tenant_id=tenant_id)
        return f"Saved: '{query}' → {document_id} (pages {pages})."

    @tool(description="Visually read a PDF page by sending the actual page image to AI vision. Use this when text extraction seems incomplete, or when the user asks about charts, tables, diagrams, or visual elements on a specific page.")
    def read_page_visual(sop_id: str, page_number: int) -> str:
        """Read a PDF page using AI vision for detailed content extraction."""
        _report("vision_read", f"read_page_visual('{sop_id}', {page_number})", "Reading page visually with AI")
        try:
            import fitz
            import base64
            from backend.core.config import get_openrouter_client, VISION_MODEL

            sop = db.get_sop(sop_id, tenant_id=tenant_id)
            if not sop or not sop.get("pdf_path"):
                return f"Document {sop_id} not found or has no PDF."

            pdf_path = db.resolve_pdf_path(sop.get("pdf_path", ""))
            if not pdf_path:
                from pathlib import Path
                pdf_path = str(Path(f"/data/tenants/{tenant_id}/uploads") / Path(sop.get("pdf_path", "")).name)

            doc = fitz.open(pdf_path)
            try:
                if page_number < 1 or page_number > len(doc):
                    return f"Page {page_number} out of range (document has {len(doc)} pages)."

                page = doc[page_number - 1]
                mat = fitz.Matrix(200/72, 200/72)  # 200 DPI
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                b64 = base64.b64encode(img_bytes).decode("utf-8")
            finally:
                doc.close()

            client = get_openrouter_client()
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Read this document page carefully. Extract ALL text, tables, diagrams, charts, and visual elements. Describe what you see in detail. Document: {sop_id}, Page: {page_number}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}}
                    ]
                }],
                max_tokens=2000,
                temperature=0,
            )

            content = response.choices[0].message.content or ""
            return f"[Visual reading of {sop_id} page {page_number}]\n{content}"
        except Exception as e:
            return f"Error reading page visually: {e}"

    return [search_intents, search_wiki, vector_search_tool, search_documents,
            list_all_documents, get_document_summary, get_page_content, get_screenshots,
            get_source_overview, save_discovery, save_negative, read_page_visual]
