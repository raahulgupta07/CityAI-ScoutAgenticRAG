"""
AI Knowledge Extraction from documents.
Extracts Q&A pairs, search keywords, entities, and summary for better search.
Run once per document during ingestion. Cost: ~$0.005 per document.
"""
from __future__ import annotations

import json

from backend.core.config import get_openrouter_client, ROUTER_MODEL
from backend.core import database as db

EXTRACT_PROMPT = """You are a knowledge extractor for organizational documents (policies, guides, manuals, reports, procedures, etc.). Given the text from a document, extract:

1. summary_short: A 1-2 sentence summary of what this document covers
1b. summary_detailed: A 3-5 sentence detailed summary covering the main sections and key information
2. qa_pairs: Generate 30-50 question-answer pairs. Each pair MUST have:
   - "q": A natural question a user would ask
   - "a": A clear answer (1-2 sentences) with specific details from the document — include names, numbers, steps, system names. Not one word, but don't write paragraphs either.
   - "page": The page number where the answer is found
   Cover ALL topics: how-to steps, definitions, contacts, policies, exceptions, timelines, roles, systems.
   Include varied phrasings: "How do I...", "What is...", "Who is responsible for...", "When should I...", "Where can I find..."
   IMPORTANT: Generate the FULL 30-50 pairs. Do NOT stop early. Cover every section of the document.
3. search_keywords: 15-25 keywords/phrases someone might search to find this document. Include abbreviations, synonyms, related terms.
4. entities: Key entities mentioned (organizations, systems, people, urls, countries)
5. caveats: 2-4 important warnings, gotchas, or things to watch out for.

Return JSON only:
{
  "summary_short": "...",
  "summary_detailed": "...",
  "qa_pairs": [
    {"q": "How do I...?", "a": "According to the document, you should...", "page": 2},
    {"q": "What is the process for...?", "a": "The process involves...", "page": 3}
  ],
  "search_keywords": ["keyword1", "keyword2", ...],
  "caveats": ["Warning: ...", "Note: ...", ...],
  "entities": {
    "organizations": ["..."],
    "systems": ["..."],
    "urls": ["..."],
    "countries": ["..."]
  }
}"""


def extract_knowledge(sop_id: str, tenant_id: str = None) -> dict:
    """Extract knowledge from a document's text content."""
    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return {"error": f"Document {sop_id} not found"}

    pdf_path = sop.get("pdf_path", "")
    if not pdf_path:
        return {"error": "No PDF path"}

    # Try vision-extracted content first (much richer than raw PDF text)
    from pathlib import Path
    text = ""
    page_contents = db.get_page_contents(sop_id, tenant_id=tenant_id)
    if page_contents:
        for pc in page_contents[:15]:  # first 15 pages for richer extraction
            page_text = pc.get("vision_content") or pc.get("text_content") or ""
            if page_text:
                text += f"\n--- Page {pc['page']} ---\n{page_text}"
            # Include table data
            tables = pc.get("tables", [])
            if tables and isinstance(tables, list):
                text += f"\nTables: {json.dumps(tables)}"
            # Include image descriptions
            img_desc = pc.get("image_descriptions", [])
            if img_desc and isinstance(img_desc, list):
                text += f"\nImages: {'; '.join(str(d) for d in img_desc)}"

    # Fallback to raw file if no vision content
    if not text.strip():
        resolved = db.resolve_pdf_path(pdf_path)
        if resolved:
            from backend.core.categorize import _extract_text
            text = _extract_text(resolved)

    if not text.strip():
        return {"error": "No text extracted"}

    # Build context for LLM
    context = f"Document ID: {sop_id}\nTitle: {sop.get('title', '')}\nDepartment: {sop.get('department', '')}\n\nDocument content:\n{text[:10000]}"

    # Call LLM with retry
    try:
        from backend.core.config import call_openrouter
        raw = call_openrouter(
            prompt=context,
            model=ROUTER_MODEL,
            max_tokens=8000,
            temperature=0,
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": context},
            ],
            max_retries=5,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
    except Exception as e:
        return {"error": f"LLM error: {e}"}

    # Update the SOP in database
    db.upsert_sop({
        **sop,
        "qa_pairs": result.get("qa_pairs", []),
        "search_keywords": result.get("search_keywords", []),
        "entities": result.get("entities", {}),
        "summary_short": result.get("summary_short", ""),
        "summary_detailed": result.get("summary_detailed", ""),
        "caveats": result.get("caveats", []),
    }, tenant_id=tenant_id)

    # Auto-generate intent routes from extracted Q&A pairs + keywords
    intent_count = db.generate_intent_routes_from_sop(sop_id, tenant_id=tenant_id)

    return {
        "sop_id": sop_id,
        "summary_short": result.get("summary_short", ""),
        "qa_pairs": len(result.get("qa_pairs", [])),
        "search_keywords": len(result.get("search_keywords", [])),
        "intent_routes": intent_count,
    }


def extract_all_knowledge(tenant_id: str = None):
    """Extract knowledge from all documents that don't have it yet."""
    sops = db.list_sops(tenant_id=tenant_id)
    results = []
    for sop in sops:
        # Skip if already extracted (search_keywords is stored as JSON string)
        kw = sop.get("search_keywords", "[]")
        if isinstance(kw, str):
            try:
                kw = json.loads(kw)
            except Exception:
                kw = []
        if isinstance(kw, list) and len(kw) > 0:
            continue
        result = extract_knowledge(sop["sop_id"], tenant_id=tenant_id)
        results.append(result)
    return results
