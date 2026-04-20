"""
Wiki Knowledge Layer — Synthesizes cross-document knowledge.
Inspired by Karpathy's LLM Wiki pattern.

After document processing, extracts entities and facts, merges them
into persistent wiki pages that span multiple documents. The agent
searches wiki BEFORE vector search for faster, richer answers.
"""
from __future__ import annotations

import json
import re
import logging
from typing import Optional

from backend.core import database as db
from backend.core.config import get_openrouter_client, ROUTER_MODEL

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a wiki page ID slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return slug[:80]


def _get_llm_client():
    return get_openrouter_client()


def wiki_synthesize(sop_id: str, tenant_id: str = None) -> dict:
    """
    Extract entities from a processed document and create/update wiki pages.
    Called after train_on_document() in the pipeline.

    Returns: {"created": int, "updated": int, "contradictions": int}
    """
    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return {"error": "Document not found", "created": 0, "updated": 0, "contradictions": 0}

    # Gather document content
    title = sop.get("title", sop_id)
    summary = sop.get("summary_detailed") or sop.get("summary_short") or ""
    qa_pairs = sop.get("qa_pairs", [])
    if isinstance(qa_pairs, str):
        try:
            qa_pairs = json.loads(qa_pairs)
        except Exception:
            qa_pairs = []
    keywords = sop.get("search_keywords", [])
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except Exception:
            keywords = []

    # Get page content for richer extraction
    pages = db.get_page_contents(sop_id, tenant_id=tenant_id)
    page_text = ""
    for p in pages[:10]:  # Limit to first 10 pages
        text = p.get("enhanced_content") or p.get("vision_content") or p.get("text_content") or ""
        if text:
            page_text += f"\n--- Page {p['page']} ---\n{text[:500]}"

    doc_context = f"""Document: {title}
Summary: {summary}
Keywords: {', '.join(str(k) for k in keywords[:20])}
Q&A Pairs: {json.dumps(qa_pairs[:10])}
Content Preview: {page_text[:3000]}"""

    # Step 1: Ask LLM to extract entities and facts
    client = _get_llm_client()
    try:
        extract_resp = client.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[{"role": "user", "content": f"""Analyze this document and extract the key knowledge entities.

{doc_context}

Return a JSON array of entities. Each entity should be a concept, process, system, policy, role, or topic that someone might search for.

Rules:
- Extract 3-8 entities (not too many)
- Each entity should be a standalone topic, not a sentence
- Include facts that are specific and useful (not generic)
- Add the page numbers where each fact is found

Return ONLY valid JSON:
[
  {{
    "entity": "Entity Name",
    "category": "process|policy|system|role|concept",
    "facts": ["Specific fact 1 [page X]", "Specific fact 2 [page Y]"],
    "related": ["Related Entity 1", "Related Entity 2"]
  }}
]"""}],
            temperature=0.3,
            max_tokens=2000,
        )

        raw = extract_resp.choices[0].message.content.strip()
        # Parse JSON from response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        entities = json.loads(raw.strip())
        if not isinstance(entities, list):
            entities = []

    except Exception as e:
        logger.error(f"Wiki entity extraction failed for {sop_id}: {e}")
        return {"created": 0, "updated": 0, "contradictions": 0, "error": str(e)}

    # Step 2: For each entity, create or merge wiki page
    created = 0
    updated = 0
    contradictions = 0

    for entity in entities:
        entity_name = entity.get("entity", "").strip()
        if not entity_name or len(entity_name) < 3:
            continue

        page_id = _slugify(entity_name)
        category = entity.get("category", "concept")
        facts = entity.get("facts", [])
        related_entities = entity.get("related", [])
        related_slugs = [_slugify(r) for r in related_entities if r]

        # Check if wiki page already exists
        existing = db.get_wiki_page(page_id, tenant_id=tenant_id)

        if existing:
            # MERGE: Update existing page with new facts
            try:
                merge_resp = client.chat.completions.create(
                    model=ROUTER_MODEL,
                    messages=[{"role": "user", "content": f"""Update this wiki page with new information.

EXISTING WIKI PAGE:
{existing['content']}

EXISTING SOURCES:
{json.dumps(existing.get('sources', []))}

NEW INFORMATION from document "{title}" (ID: {sop_id}):
{json.dumps(facts)}

Rules:
- Integrate new facts into the existing content naturally
- Add [REF:{sop_id}:page] citations for new facts
- If new info CONTRADICTS existing info, add a "⚠ Contradiction:" note
- Keep the page concise and well-structured (markdown)
- Do NOT remove existing content — only add/update
- Return ONLY the updated markdown content (no JSON wrapper)"""}],
                    temperature=0.2,
                    max_tokens=1500,
                )

                new_content = merge_resp.choices[0].message.content.strip()

                # Merge sources
                existing_sources = existing.get("sources", [])
                if isinstance(existing_sources, str):
                    try:
                        existing_sources = json.loads(existing_sources)
                    except Exception:
                        existing_sources = []
                existing_sources.append({
                    "sop_id": sop_id,
                    "title": title,
                    "facts_added": len(facts),
                })

                # Merge related
                existing_related = existing.get("related", [])
                if isinstance(existing_related, str):
                    try:
                        existing_related = json.loads(existing_related)
                    except Exception:
                        existing_related = []
                merged_related = list(set(existing_related + related_slugs))

                # Check for contradictions
                existing_contradictions = existing.get("contradictions", [])
                if isinstance(existing_contradictions, str):
                    try:
                        existing_contradictions = json.loads(existing_contradictions)
                    except Exception:
                        existing_contradictions = []
                if "contradiction" in new_content.lower() or "⚠" in new_content:
                    existing_contradictions.append({
                        "source": sop_id,
                        "detected_at": title,
                    })
                    contradictions += 1

                db.upsert_wiki_page(
                    page_id=page_id,
                    title=entity_name,
                    category=category,
                    content=new_content,
                    sources=existing_sources,
                    related=merged_related,
                    contradictions=existing_contradictions,
                    tenant_id=tenant_id,
                )
                updated += 1

            except Exception as e:
                logger.error(f"Wiki merge failed for {page_id}: {e}")

        else:
            # CREATE: New wiki page
            # Build initial content from facts
            content_parts = [f"## {entity_name}\n"]
            for fact in facts:
                content_parts.append(f"- {fact} [REF:{sop_id}]")
            if related_entities:
                content_parts.append(f"\n**Related:** {', '.join(related_entities)}")

            content = "\n".join(content_parts)

            db.upsert_wiki_page(
                page_id=page_id,
                title=entity_name,
                category=category,
                content=content,
                sources=[{"sop_id": sop_id, "title": title, "facts_added": len(facts)}],
                related=related_slugs,
                contradictions=[],
                tenant_id=tenant_id,
            )
            created += 1

    # Track usage
    if tenant_id:
        try:
            db.log_usage(tenant_id, "wiki_synthesize", ROUTER_MODEL,
                         cost_usd=0.001 * (1 + updated),
                         metadata={"sop_id": sop_id, "created": created,
                                   "updated": updated, "contradictions": contradictions})
            db.log_audit(tenant_id, "wiki_synthesize", resource_type="wiki",
                         resource_id=sop_id,
                         details=f"{created} created, {updated} updated, {contradictions} contradictions")
        except Exception:
            pass

    return {"created": created, "updated": updated, "contradictions": contradictions}


def wiki_query(query: str, limit: int = 3, tenant_id: str = None) -> list:
    """
    Search wiki pages by keyword. Returns matching pages with content.
    Pure DB query — $0 cost, instant.
    """
    results = db.search_wiki_pages(query, limit=limit, tenant_id=tenant_id)
    # Bump hit counts
    for r in results:
        try:
            db.bump_wiki_hit(r["id"], tenant_id=tenant_id)
        except Exception:
            pass
    return results


def wiki_lint(tenant_id: str = None) -> dict:
    """
    Health check on the wiki. Pure DB queries — $0 cost.
    Returns report of stale sources, orphans, contradiction counts.
    """
    pages = db.list_wiki_pages(tenant_id=tenant_id)
    all_docs = db.list_sops(tenant_id=tenant_id)
    doc_ids = {d["sop_id"] for d in all_docs}

    stale_sources = []
    orphan_pages = []
    contradiction_count = 0
    never_hit = []

    for page in pages:
        page_id = page["id"]
        sources = page.get("sources", [])
        if isinstance(sources, str):
            try:
                sources = json.loads(sources)
            except Exception:
                sources = []

        contradictions = page.get("contradictions", [])
        if isinstance(contradictions, str):
            try:
                contradictions = json.loads(contradictions)
            except Exception:
                contradictions = []

        # Check for stale sources (doc was deleted)
        valid_sources = [s for s in sources if s.get("sop_id") in doc_ids]
        stale = [s for s in sources if s.get("sop_id") not in doc_ids]
        if stale:
            stale_sources.append({"page": page_id, "stale": [s.get("sop_id") for s in stale]})

        # Orphan: all sources are stale
        if sources and not valid_sources:
            orphan_pages.append(page_id)

        # Contradiction count
        contradiction_count += len(contradictions)

        # Never hit
        if page.get("hit_count", 0) == 0:
            never_hit.append(page_id)

    return {
        "total_pages": len(pages),
        "stale_sources": stale_sources,
        "orphan_pages": orphan_pages,
        "contradiction_count": contradiction_count,
        "never_hit_pages": never_hit,
        "health": "good" if not stale_sources and not orphan_pages else "needs_attention",
    }


def generate_persona(tenant_id: str) -> dict:
    """
    Analyze all documents for a tenant and auto-generate an agent persona.
    Reads document summaries, keywords, entities, wiki pages, Q&A samples,
    and page content to understand the organization's writing style.
    Saves the generated persona to tenants.agent_system_prompt.
    """
    # Collect all document data
    docs = db.list_sops(tenant_id=tenant_id)
    if not docs:
        return {"error": "No documents to analyze", "persona": ""}

    wiki_pages = db.list_wiki_pages(tenant_id=tenant_id)

    # Build context from all documents
    context_parts = []
    all_keywords = set()
    all_entities = {}
    qa_samples = []

    for doc in docs[:20]:  # Limit to 20 docs
        title = doc.get("title", doc.get("sop_id", ""))
        dept = doc.get("department", "")
        summary = doc.get("summary_short", "")
        keywords = doc.get("search_keywords", [])
        if isinstance(keywords, str):
            try: keywords = json.loads(keywords)
            except: keywords = []
        entities = doc.get("entities", {})
        if isinstance(entities, str):
            try: entities = json.loads(entities)
            except: entities = {}
        qa = doc.get("qa_pairs", [])
        if isinstance(qa, str):
            try: qa = json.loads(qa)
            except: qa = []

        context_parts.append(f"Document: {title} | Dept: {dept} | Summary: {summary}")
        for k in keywords:
            if isinstance(k, str): all_keywords.add(k)
        for key, vals in entities.items():
            if key not in all_entities: all_entities[key] = set()
            if isinstance(vals, list):
                for v in vals:
                    if isinstance(v, str): all_entities[key].add(v)
        # Take first 2 Q&A as samples
        for q in qa[:2]:
            if isinstance(q, str): qa_samples.append(q)
            elif isinstance(q, dict): qa_samples.append(f"Q: {q.get('q','')} A: {q.get('a','')}")

    # Add page content samples (first page of first 3 docs)
    content_samples = []
    for doc in docs[:3]:
        pages = db.get_page_contents(doc["sop_id"], [1], tenant_id=tenant_id)
        if pages:
            text = pages[0].get("enhanced_content") or pages[0].get("vision_content") or pages[0].get("text_content") or ""
            if text: content_samples.append(f"[{doc.get('title','')} Page 1]: {text[:300]}")

    # Add wiki summaries
    wiki_summary = ""
    for wp in wiki_pages[:10]:
        wiki_summary += f"Wiki: {wp.get('title','')} ({wp.get('category','')}) | "

    # Build the analysis prompt
    doc_overview = "\n".join(context_parts[:15])
    keywords_str = ", ".join(list(all_keywords)[:40])
    entities_str = json.dumps({k: list(v)[:5] for k, v in all_entities.items()})
    qa_str = "\n".join(qa_samples[:8])
    samples_str = "\n\n".join(content_samples[:3])

    prompt = f"""Analyze these documents from an organization and generate an agent persona.

DOCUMENTS ({len(docs)} total):
{doc_overview}

DOMAIN VOCABULARY (keywords across all docs):
{keywords_str}

ENTITIES (systems, people, organizations):
{entities_str}

SAMPLE Q&A PAIRS:
{qa_str}

WRITING STYLE SAMPLES:
{samples_str}

WIKI KNOWLEDGE:
{wiki_summary}

Based on this analysis, generate a SYSTEM PROMPT for an AI agent that works with these documents. The prompt should make the agent speak naturally in this organization's style.

Include:
1. VOCABULARY — specific domain terms the agent should use naturally
2. TONE — how formal/casual/technical the documents are
3. STRUCTURE — how the agent should format answers (steps, bullets, paragraphs)
4. KEY CONTACTS — important people, teams, systems mentioned across documents
5. DOMAIN RULES — recurring patterns, warnings, or conventions
6. ORGANIZATION CONTEXT — what kind of organization this is, what they do

Return ONLY the system prompt text (no JSON, no markdown code blocks). Write it as direct instructions to the agent. Keep it under 500 words. Be specific — use actual names, systems, and terms from the documents."""

    client = _get_llm_client()
    try:
        response = client.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        persona = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        if persona.startswith("```"):
            persona = "\n".join(persona.split("\n")[1:])
            if persona.rstrip().endswith("```"):
                persona = persona.rstrip()[:-3].strip()
    except Exception as e:
        logger.error(f"Persona generation failed: {e}")
        return {"error": str(e), "persona": ""}

    # Save to tenant
    try:
        conn = db.get_db()
        conn.execute(
            "UPDATE tenants SET agent_system_prompt = %s WHERE id = %s",
            (persona, tenant_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to save persona: {e}")
        return {"error": f"Save failed: {e}", "persona": persona}

    # Reload agent with new persona
    try:
        from backend.core.agent import reload_agent
        reload_agent(tenant_id)
    except Exception:
        pass

    # Log
    try:
        db.log_usage(tenant_id, "generate_persona", ROUTER_MODEL, cost_usd=0.003,
                     metadata={"docs_analyzed": len(docs), "wiki_pages": len(wiki_pages)})
        db.log_audit(tenant_id, "generate_persona", resource_type="tenant",
                     details=f"Analyzed {len(docs)} docs, {len(wiki_pages)} wiki pages")
    except Exception:
        pass

    return {
        "persona": persona,
        "docs_analyzed": len(docs),
        "keywords_found": len(all_keywords),
        "wiki_pages": len(wiki_pages),
    }
