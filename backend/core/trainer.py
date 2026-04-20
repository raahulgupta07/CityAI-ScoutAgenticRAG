"""
Auto-trainer: After document upload+process, runs simulated queries
to teach the Agno agent about the new document.
Reports progress to a log queue for real-time CLI display.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from backend.core import database as db


# Shared log list — the API reads this for real-time streaming
_training_logs: list = []
_training_status = {"running": False, "sop_id": "", "progress": 0, "total": 0}


def get_training_logs(since: int = 0) -> list:
    """Get training logs since index."""
    return _training_logs[since:]


def get_training_status() -> dict:
    return _training_status.copy()


def clear_training_logs():
    global _training_logs
    _training_logs = []


def _log(level: str, message: str, detail: str = ""):
    """Add a log entry with timestamp."""
    entry = {
        "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "level": level,
        "message": message,
        "detail": detail,
    }
    _training_logs.append(entry)


def _run_single_training_query(agent, sop_id: str, title: str, question: str, index: int, total: int) -> dict:
    """Run a single training query. Thread-safe for parallel execution."""
    _log("query", f"Training {index}/{total}", question[:80])

    t0 = time.time()
    try:
        response = agent.run(
            input=f"[Training mode - document: {sop_id}] {question}",
            session_id=f"training_{sop_id}_{index}",
        )

        answer = response.content or ""
        duration = round(time.time() - t0, 1)

        # Check if it found useful info (fixed boolean precedence)
        # O/0 normalization — LLM often writes letter O instead of digit 0
        _norm = lambda s: s.lower().replace('o', '0')
        found = (len(answer) > 50) and (sop_id in answer or _norm(sop_id) in _norm(answer) or title[:20] in answer)
        status = "learned" if found else "partial"

        _log("result", f"  #{index} → {status} ({duration}s)", answer[:80])

        return {
            "question": question,
            "status": status,
            "duration": duration,
            "answer_length": len(answer),
        }

    except Exception as e:
        _log("error", f"  #{index} → Failed: {e}")
        return {"question": question, "status": "error", "error": str(e)}


def _update_pages_with_standardized(sop_id: str, tenant_id: str = None):
    """
    After SOP standardization, MERGE standardized content WITH original content.
    Agent gets BOTH: structured standardized (primary) + raw original (fallback).
    Format: [STANDARDIZED]\n...\n[ORIGINAL]\n...
    Re-embeds in PgVector with the combined content for better search.
    """
    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return

    std_json = sop.get("standardized_json")
    if isinstance(std_json, str):
        try: std_json = json.loads(std_json)
        except: return
    if not std_json:
        return

    procedure = std_json.get("procedure", [])
    if not procedure:
        return

    # Build standardized content per page
    page_std = {}
    for step in procedure:
        source_page = step.get("source_page", 0)
        if not source_page:
            continue
        if source_page not in page_std:
            page_std[source_page] = []

        step_text = f"Step {step.get('step_number', '')}: {step.get('title', '')}\n"
        activity = step.get("activity", step.get("description", ""))
        if activity:
            step_text += f"{activity}\n"
        s_input = step.get("input", "")
        if s_input:
            step_text += f"Input: {s_input}\n"
        s_output = step.get("output", "")
        if s_output:
            step_text += f"Output: {s_output}\n"
        expected = step.get("expected_result", "")
        if expected:
            step_text += f"Expected Result: {expected}\n"
        verification = step.get("verification", "")
        if verification:
            step_text += f"Verification: {verification}\n"
        warnings = step.get("warnings", "")
        if warnings:
            step_text += f"Warning: {warnings}\n"
        page_std[source_page].append(step_text)

    # Add executive summary, purpose, scope, definitions, RACI to page 1
    page_1_extra = []
    exec_summary = std_json.get("executive_summary", "")
    if exec_summary:
        page_1_extra.append(f"Executive Summary: {exec_summary}")
    purpose = std_json.get("purpose", "")
    if purpose:
        page_1_extra.append(f"Purpose: {purpose}")
    scope = std_json.get("scope", {})
    if isinstance(scope, dict) and scope.get("description"):
        page_1_extra.append(f"Scope: {scope['description']}")
    # Add definitions
    defs = std_json.get("definitions", [])
    if defs:
        def_text = "Key Definitions:\n"
        for d in defs:
            if isinstance(d, dict):
                def_text += f"- {d.get('term', '')}: {d.get('definition', '')}\n"
        page_1_extra.append(def_text)
    # Add RACI summary
    raci = std_json.get("raci", [])
    if raci:
        raci_text = "RACI Matrix:\n"
        for r in raci:
            if isinstance(r, dict):
                raci_text += f"- {r.get('activity', '')}: R={r.get('responsible', '')} A={r.get('accountable', '')}\n"
        page_1_extra.append(raci_text)
    # Add KPIs
    kpis = std_json.get("kpis", [])
    if kpis:
        kpi_text = "KPIs:\n"
        for k in kpis:
            if isinstance(k, dict):
                kpi_text += f"- {k.get('metric', '')}: target {k.get('target', '')}\n"
        page_1_extra.append(kpi_text)

    if page_1_extra:
        if 1 not in page_std:
            page_std[1] = []
        page_std[1] = page_1_extra + page_std.get(1, [])

    # MERGE: Keep original content + prepend standardized content
    updated_count = 0
    conn = db.get_db(tenant_id)
    try:
        for page_num, std_texts in page_std.items():
            std_combined = "\n\n".join(std_texts)
            if not std_combined.strip():
                continue

            # Get current original content
            row = conn.execute(
                "SELECT enhanced_content, vision_content, text_content FROM page_content WHERE sop_id = %s AND page = %s",
                (sop_id, page_num)
            ).fetchone()

            original = ""
            if row:
                original = row["enhanced_content"] or row["vision_content"] or row["text_content"] or ""

            # Merge: standardized first (primary), original second (fallback)
            merged = f"[STANDARDIZED CONTENT]\n{std_combined}"
            if original.strip() and "[STANDARDIZED CONTENT]" not in original:
                merged += f"\n\n[ORIGINAL CONTENT]\n{original}"

            conn.execute(
                "UPDATE page_content SET enhanced_content = %s WHERE sop_id = %s AND page = %s",
                (merged, sop_id, page_num)
            )
            updated_count += 1
        conn.commit()
    finally:
        conn.close()

    _log("info", f"  Merged standardized + original content for {updated_count} pages")

    # Re-embed with the combined content (agent searches BOTH)
    try:
        from backend.core.database import embed_document_pages
        embedded = embed_document_pages(sop_id, tenant_id=tenant_id)
        _log("info", f"  Re-embedded {embedded} pages in PgVector (combined content)")
    except Exception as e:
        _log("error", f"  Re-embedding failed: {e}")

    # Update document summary
    if exec_summary:
        try:
            conn = db.get_db(tenant_id)
            try:
                conn.execute(
                    "UPDATE sops SET summary_short = %s, summary_detailed = %s WHERE sop_id = %s",
                    (exec_summary[:200], exec_summary, sop_id)
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass


def _run_discovery_phase(sop_id: str, title: str, agent, tenant_id: str = None) -> int:
    """
    Self-Learning Discovery: Generate diverse queries from document content,
    run them through the agent, and explicitly save intent route discoveries.
    Returns count of new discoveries saved.
    """
    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return 0

    discoveries = 0

    # Build discovery queries from multiple sources
    discovery_queries = set()

    # Source 1: Keywords from document
    keywords = sop.get("search_keywords", [])
    if isinstance(keywords, str):
        try: keywords = json.loads(keywords)
        except: keywords = []
    for kw in keywords[:10]:
        if isinstance(kw, str) and len(kw) > 3:
            discovery_queries.add(f"What about {kw}?")
            discovery_queries.add(kw)

    # Source 2: Q&A pairs — extract the topic, rephrase differently
    qa_pairs = sop.get("qa_pairs", [])
    if isinstance(qa_pairs, str):
        try: qa_pairs = json.loads(qa_pairs)
        except: qa_pairs = []
    for q in qa_pairs[:5]:
        if isinstance(q, str) and len(q) > 10:
            # Extract key nouns (simple: take words > 4 chars)
            key_words = [w for w in q.split() if len(w) > 4 and w.isalpha()]
            if key_words:
                discovery_queries.add(" ".join(key_words[:3]))

    # Source 3: Title-based queries
    title_words = [w for w in title.split() if len(w) > 3 and w.isalpha()]
    if title_words:
        discovery_queries.add(f"How to {' '.join(title_words[:4]).lower()}")
        discovery_queries.add(f"Steps for {' '.join(title_words[:3]).lower()}")
        discovery_queries.add(f"What is {' '.join(title_words[:3]).lower()}")

    # Source 4: Department-based
    dept = sop.get("department", "")
    if dept:
        discovery_queries.add(f"Show me {dept} documents")
        discovery_queries.add(f"What procedures exist for {dept}")

    queries = list(discovery_queries)[:15]  # Cap at 15 discovery queries
    if not queries:
        return 0

    _log("info", f"Running {len(queries)} discovery queries...", "Building self-learning routes")

    # Run each discovery query and save the mapping
    pages = db.get_page_contents(sop_id, tenant_id=tenant_id)
    page_nums = ",".join(str(p.get("page", 0)) for p in pages[:5])

    for i, query in enumerate(queries):
        try:
            t0 = time.time()
            response = agent.run(
                input=f"[Discovery mode] {query}",
                session_id=f"discovery_{sop_id}_{i}",
            )
            answer = response.content or ""
            duration = round(time.time() - t0, 1)

            # Check if the agent found relevant content from this document
            # O/0 normalization — LLM often writes letter O instead of digit 0
            _norm = lambda s: s.lower().replace('o', '0')
            if sop_id in answer or _norm(sop_id) in _norm(answer) or title[:15] in answer or len(answer) > 100:
                # Save the discovery — this query maps to this document
                words = [w.lower() for w in query.split() if len(w) > 2]
                db.upsert_intent_route(
                    intent=query,
                    keywords=words,
                    sop_id=sop_id,
                    pages=page_nums,
                    reason=f"Discovered during training: {title}",
                    source="discovered",
                    tenant_id=tenant_id,
                )
                discoveries += 1
                _log("info", f"  Discovery #{discoveries}: '{query[:50]}' → {sop_id}", f"{duration}s")
            else:
                _log("info", f"  No match: '{query[:50]}'", f"{duration}s")

        except Exception as e:
            _log("error", f"  Discovery query failed: {e}")

    # Also save some direct keyword→document routes (these are instant, no agent call needed)
    for kw in keywords[:8]:
        if isinstance(kw, str) and len(kw) > 3:
            words = [w.lower() for w in kw.split() if len(w) > 2]
            try:
                db.upsert_intent_route(
                    intent=kw,
                    keywords=words,
                    sop_id=sop_id,
                    pages=page_nums,
                    reason=f"Keyword from {title}",
                    source="discovered",
                    tenant_id=tenant_id,
                )
                discoveries += 1
            except Exception:
                pass

    # Track in usage log
    if tenant_id:
        try:
            db.log_usage(tenant_id, "self_learning", cost_usd=0.001 * len(queries),
                         metadata={"sop_id": sop_id, "discoveries": discoveries, "queries": len(queries)})
            db.log_audit(tenant_id, "self_learning", resource_type="sop", resource_id=sop_id,
                         details=f"{discoveries} discoveries from {len(queries)} queries")
        except Exception:
            pass

    return discoveries


def train_on_document(sop_id: str, tenant_id: str = None, on_status=None) -> dict:
    """
    Auto-train the Agno agent on a document by running its Q&A pairs.
    Uses parallel execution (3 concurrent) for speed.
    """
    global _training_status

    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        _log("error", f"Document {sop_id} not found")
        return {"error": "Document not found"}

    qa_pairs = sop.get("qa_pairs", [])
    if isinstance(qa_pairs, str):
        try:
            qa_pairs = json.loads(qa_pairs)
        except Exception:
            qa_pairs = []

    if not qa_pairs:
        _log("warn", f"No Q&A pairs for {sop_id}", "Run knowledge extraction first")
        return {"error": "No Q&A pairs to train on"}

    title = sop.get("title", sop_id)
    total_qa = len(qa_pairs)
    _log("info", f"Training on: {title}", f"{total_qa} Q&A pairs")
    _training_status = {"running": True, "sop_id": sop_id, "progress": 0, "total": total_qa}

    def _sub(msg):
        if on_status:
            try: on_status("training_sub", msg)
            except: pass

    from backend.core.agent import get_agent
    agent = get_agent(tenant_id)

    results = []
    completed = 0

    # Run training queries in parallel (3 concurrent for speed)
    BATCH_SIZE = 3
    with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        futures = {}
        for i, qa in enumerate(qa_pairs):
            question = qa.get("question", qa) if isinstance(qa, dict) else str(qa)
            if not question or not isinstance(question, str):
                continue
            future = executor.submit(
                _run_single_training_query,
                agent, sop_id, title, question, i + 1, total_qa
            )
            futures[future] = i

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1
            _training_status["progress"] = completed
            status_icon = "✓" if result.get("status") == "learned" else "~"
            q_preview = result.get('question', '')[:60]
            _log("info", f"  [{completed}/{total_qa}] {status_icon} {q_preview}")
            _sub(f"Training Q&A [{completed}/{total_qa}]: {q_preview}")

    # Summary
    learned = sum(1 for r in results if r.get("status") == "learned")
    partial = sum(1 for r in results if r.get("status") == "partial")
    errors = sum(1 for r in results if r.get("status") == "error")

    _log("done", f"Training: {learned} learned, {partial} partial, {errors} errors out of {total_qa}", sop_id)
    _sub(f"Training complete: {learned} learned, {partial} partial")

    # ── Self-Learning Discovery Phase ──
    _log("step", "━━━ SELF-LEARNING DISCOVERY ━━━", "Building intent routes from document")
    _sub("Self-learning discovery: generating diverse queries...")
    discoveries = _run_discovery_phase(sop_id, title, agent, tenant_id=tenant_id)
    _log("done", f"Discovery: {discoveries} new intent routes saved", sop_id)
    _sub(f"Discovery complete: {discoveries} intent routes saved")

    _training_status = {"running": False, "sop_id": sop_id, "progress": len(qa_pairs), "total": len(qa_pairs)}

    return {
        "sop_id": sop_id,
        "total_queries": len(qa_pairs),
        "learned": learned,
        "partial": partial,
        "errors": errors,
        "discoveries": discoveries,
    }


def process_and_train(pdf_path: str, sop_id: str, on_status=None, tenant_id: str = None) -> dict:
    """Full pipeline: process document + auto-train. With detailed logging."""
    global _training_status
    clear_training_logs()
    _training_status = {"running": True, "sop_id": sop_id, "progress": 0, "total": 0}

    _log("step", "━━━ PIPELINE START ━━━", sop_id)
    _log("info", f"File: {pdf_path}")

    # Broadcast to external SSE listener if provided
    def _notify(step: str, msg: str):
        if on_status:
            try:
                on_status(step, msg)
            except Exception:
                pass

    _notify("pipeline_start", f"Starting pipeline for {sop_id}")

    from backend.core.pipeline import process_document

    def on_pipeline_status(step: str, msg: str):
        level = "pipeline"
        if "error" in step.lower():
            level = "error"
        elif step == "done":
            level = "done"
        elif any(k in step for k in ["categoriz", "vision", "extract", "enhanc", "embed", "compli", "saving", "storing"]):
            level = "step"
        _log(level, msg, step)
        _notify(step, msg)

    t0 = time.time()
    result = process_document(pdf_path, sop_id, on_status=on_pipeline_status, tenant_id=tenant_id)

    if result.get("error"):
        _log("error", f"Pipeline failed: {result['error']}")
        _notify("error", f"Pipeline failed: {result['error']}")
        _training_status = {"running": False, "sop_id": sop_id, "progress": 0, "total": 0}
        return result

    pipeline_time = round(time.time() - t0, 1)
    _log("info", f"Processing done in {pipeline_time}s", f"{result.get('page_count', 0)} pages, {result.get('screenshots', 0)} screenshots")
    _notify("processing_done", f"Processing done in {pipeline_time}s — {result.get('page_count', 0)} pages, {result.get('screenshots', 0)} screenshots")

    # Auto-train (knowledge + embedding + compliance already done in pipeline)
    _log("step", "━━━ AUTO-TRAINING ━━━", "Teaching agent about new document")
    _notify("auto_training", "Auto-training: teaching agent about new document")
    t2 = time.time()
    train_result = train_on_document(sop_id, tenant_id=tenant_id, on_status=_notify)
    train_time = round(time.time() - t2, 1)

    # ── SOP Standardization + Re-embed with standardized content ──
    std_result = None
    if tenant_id:
        try:
            tenant = db.get_tenant(tenant_id)
            if tenant and tenant.get("document_mode") == "sop":
                _log("step", "━━━ SOP STANDARDIZATION ━━━", "Generating Tier-1 consulting DOCX")
                _notify("sop_standardization", "SOP Standardization: generating structured DOCX")
                t3 = time.time()
                from backend.core.sop_standardize import standardize_sop
                std_result = standardize_sop(sop_id, tenant_id=tenant_id, on_status=on_pipeline_status)
                std_time = round(time.time() - t3, 1)

                if std_result and "error" not in std_result:
                    _log("done", f"SOP standardized: score {std_result.get('score', 0)}/100 ({std_time}s)")

                    # ── Feed standardized content BACK into agent's knowledge ──
                    _log("step", "━━━ RE-EMBEDDING WITH STANDARDIZED CONTENT ━━━")
                    _notify("re_embedding", "Re-embedding with standardized content")
                    _update_pages_with_standardized(sop_id, tenant_id)
                    _log("done", "Agent now uses standardized content for answers")
                else:
                    _log("error", f"SOP standardize error: {std_result.get('error', '?')}")
        except Exception as e:
            _log("error", f"Standardization failed: {e}")

    # ── Wiki Synthesis — cross-document knowledge layer ──
    wiki_result = None
    try:
        _log("step", "━━━ WIKI SYNTHESIS ━━━", "Building cross-document knowledge")
        _notify("wiki_synthesis", "Wiki synthesis: building cross-document knowledge")
        from backend.core.wiki import wiki_synthesize
        wiki_result = wiki_synthesize(sop_id, tenant_id=tenant_id)
        if wiki_result and "error" not in wiki_result:
            _log("done", f"Wiki: {wiki_result.get('created', 0)} new, {wiki_result.get('updated', 0)} updated, {wiki_result.get('contradictions', 0)} contradictions")
        else:
            _log("error", f"Wiki synthesis error: {wiki_result.get('error', '?')}")
    except Exception as e:
        _log("error", f"Wiki synthesis failed: {e}")

    total_time = round(time.time() - t0, 1)
    _log("step", "━━━ PIPELINE COMPLETE ━━━")
    _log("info", f"Total: {total_time}s (process: {pipeline_time}s, train: {train_time}s)")
    _log("info", f"  Category: {result.get('category', '?')}")
    _log("info", f"  Pages: {result.get('page_count', 0)}, Screenshots: {result.get('screenshots', 0)}")
    _log("info", f"  Trained: {train_result.get('learned', 0)} learned, {train_result.get('partial', 0)} partial")
    _log("info", f"  Self-Learned: {train_result.get('discoveries', 0)} new intent routes")
    if std_result and "error" not in (std_result or {}):
        _log("info", f"  SOP Score: {std_result.get('score', 0)}/100")
    if wiki_result and "error" not in (wiki_result or {}):
        _log("info", f"  Wiki: {wiki_result.get('created', 0)} new, {wiki_result.get('updated', 0)} updated")
    _log("done", "All done!", sop_id)
    _notify("pipeline_complete", f"Pipeline complete in {total_time}s")

    _training_status = {"running": False, "sop_id": sop_id, "progress": 100, "total": 100}

    return {
        **result,
        "training": train_result,
        "standardization": std_result,
        "wiki": wiki_result,
        "total_time": total_time,
    }
