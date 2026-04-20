"""
AI Compliance Check for documents.
Checks: version, author, date, signatures, missing sections, quality score.
"""
from __future__ import annotations

import json

from backend.core.config import get_openrouter_client, ROUTER_MODEL
from backend.core import database as db

COMPLIANCE_PROMPT = """You are a document quality auditor. Given the text from a document, check its compliance:

1. has_version: Does the document have a version number? (true/false)
2. has_author: Does it mention an author or creator? (true/false)
3. has_date: Does it have a creation or update date? (true/false)
4. has_signatures: Does it have approval signatures or sign-offs? (true/false)
5. is_expired: Based on dates, is this document likely outdated (>1 year old)? (true/false)
6. missing_sections: What standard sections are missing? (e.g., "Purpose", "Scope", "Version History")
7. quality_score: Overall quality 0-100 (100=perfect, 0=unusable)
8. recommendations: 2-4 specific improvements

Return JSON only:
{
  "has_version": true,
  "has_author": false,
  "has_date": true,
  "has_signatures": false,
  "is_expired": false,
  "missing_sections": ["Scope", "Version History"],
  "quality_score": 65,
  "recommendations": ["Add author name", "Add version number", "Include scope section"]
}"""


def check_compliance(sop_id: str, tenant_id: str = None) -> dict:
    """Run compliance check on a document."""
    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return {"error": f"Document {sop_id} not found"}

    # Get text content (prefer vision-extracted)
    text = db.get_all_page_text(sop_id, tenant_id=tenant_id)
    if not text:
        # Fallback to description
        text = sop.get("doc_description", "") or sop.get("description", "")
    if not text:
        return {"error": "No text content to check"}

    context = f"Document: {sop_id}\nTitle: {sop.get('title', '')}\nDepartment: {sop.get('department', '')}\n\nContent:\n{text[:4000]}"

    try:
        from backend.core.config import call_openrouter
        raw = call_openrouter(
            prompt=context,
            model=ROUTER_MODEL,
            max_tokens=500,
            temperature=0,
            messages=[
                {"role": "system", "content": COMPLIANCE_PROMPT},
                {"role": "user", "content": context},
            ],
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
    except Exception as e:
        return {"error": f"Compliance check failed: {e}"}

    db.upsert_compliance(sop_id, result, tenant_id=tenant_id)

    return {"sop_id": sop_id, **result}


def check_all_compliance(tenant_id: str = None) -> list:
    """Run compliance check on all documents."""
    sops = db.list_sops(tenant_id=tenant_id)
    results = []
    for sop in sops:
        result = check_compliance(sop["sop_id"], tenant_id=tenant_id)
        results.append(result)
    return results
