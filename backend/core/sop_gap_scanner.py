"""
AI Gap Scanner — Scans entire SOP library for:
1. Missing SOPs (topics that should have SOPs but don't)
2. Broken cross-references (SOP references a doc that doesn't exist)
3. Quality distribution (score analysis)
4. Coverage analysis per department
"""
from __future__ import annotations
import json, logging, re
from backend.core import database as db
from backend.core.config import call_openrouter, ROUTER_MODEL

logger = logging.getLogger(__name__)


def _call_llm(prompt: str) -> str:
    return call_openrouter(prompt, model=ROUTER_MODEL, max_tokens=4000, temperature=0.2)


def scan_library(tenant_id: str = None) -> dict:
    """Full gap scan of tenant's SOP library."""

    docs = db.list_sops(tenant_id=tenant_id)
    if not docs:
        return {"error": "No documents in library", "total_docs": 0}

    # ── 1. Basic stats ──
    total = len(docs)
    indexed = [d for d in docs if d.get("department") and d.get("department") != "Uploaded"]
    standardized = [d for d in docs if d.get("sop_score", 0) > 0]
    scores = [d.get("sop_score", 0) for d in standardized]
    avg_score = round(sum(scores) / len(scores)) if scores else 0

    # Department breakdown
    departments = {}
    for d in indexed:
        dept = d.get("department", "Unknown")
        if dept not in departments:
            departments[dept] = {"count": 0, "avg_score": 0, "scores": []}
        departments[dept]["count"] += 1
        if d.get("sop_score", 0) > 0:
            departments[dept]["scores"].append(d["sop_score"])

    for dept in departments:
        s = departments[dept]["scores"]
        departments[dept]["avg_score"] = round(sum(s) / len(s)) if s else 0
        del departments[dept]["scores"]

    # ── 2. Cross-reference check ──
    broken_refs = []
    all_titles = set(d.get("title", "").lower() for d in docs)
    all_ids = set(d.get("sop_id", "").lower() for d in docs)

    for d in docs:
        std_json = d.get("standardized_json")
        if isinstance(std_json, str):
            try: std_json = json.loads(std_json)
            except: continue
        if not std_json:
            continue

        refs = std_json.get("references", [])
        for ref in refs:
            ref_str = str(ref).lower() if not isinstance(ref, dict) else str(ref.get("name", ref.get("title", ""))).lower()
            if not ref_str:
                continue
            # Check if referenced doc exists (fuzzy match)
            found = False
            for title in all_titles:
                if ref_str in title or title in ref_str:
                    found = True
                    break
            for sid in all_ids:
                if ref_str in sid or sid in ref_str:
                    found = True
                    break
            if not found and len(ref_str) > 5:
                broken_refs.append({
                    "sop": d.get("title", d.get("sop_id")),
                    "references": str(ref)[:100],
                    "status": "NOT FOUND in library"
                })

    # ── 3. AI Gap Analysis ──
    doc_summaries = []
    for d in indexed[:30]:  # Limit to 30 docs for prompt size
        doc_summaries.append(f"- {d.get('title', d['sop_id'])} ({d.get('department', '?')}, {d.get('page_count', 0)}p, score:{d.get('sop_score', 0)})")

    # Get tenant focus for context
    tenant_focus = "organizational documents"
    if tenant_id:
        try:
            tenant = db.get_tenant(tenant_id)
            if tenant:
                tenant_focus = tenant.get("agent_focus", tenant_focus)
        except:
            pass

    missing_sops = []
    recommendations = []
    try:
        prompt = f"""You are a document compliance auditor. Analyze this document library and identify gaps.

TENANT FOCUS: {tenant_focus}
DEPARTMENTS: {', '.join(departments.keys())}
TOTAL DOCUMENTS: {total}

CURRENT LIBRARY:
{chr(10).join(doc_summaries)}

Based on the tenant focus "{tenant_focus}" and the existing documents, identify:

1. MISSING DOCUMENTS — What critical documents are missing from this library? (e.g., if it's ITSM focused and there's no Incident Management SOP, that's a gap)
2. RECOMMENDATIONS — What should be improved or added?

Return ONLY valid JSON (no markdown):
{{
  "missing_sops": [
    {{"title": "expected SOP name", "department": "department", "priority": "Critical|High|Medium", "reason": "why this is needed"}}
  ],
  "recommendations": [
    {{"category": "Coverage|Quality|Compliance|Process", "description": "what to do", "priority": "Critical|High|Medium"}}
  ]
}}"""

        result_text = _call_llm(prompt).strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.rstrip().endswith("```"):
                result_text = result_text.rstrip()[:-3]
        ai_result = json.loads(result_text.strip())
        missing_sops = ai_result.get("missing_sops", [])
        recommendations = ai_result.get("recommendations", [])
    except Exception as e:
        logger.warning(f"AI gap analysis failed: {e}")
        recommendations = [{"category": "Error", "description": f"AI analysis failed: {str(e)[:100]}", "priority": "Medium"}]

    # ── 4. Quality distribution ──
    quality_dist = {
        "excellent": len([s for s in scores if s >= 80]),
        "good": len([s for s in scores if 60 <= s < 80]),
        "needs_work": len([s for s in scores if 40 <= s < 60]),
        "poor": len([s for s in scores if s < 40]),
        "not_standardized": total - len(standardized),
    }

    return {
        "total_docs": total,
        "indexed": len(indexed),
        "standardized": len(standardized),
        "avg_score": avg_score,
        "departments": departments,
        "quality_distribution": quality_dist,
        "broken_references": broken_refs,
        "missing_sops": missing_sops,
        "recommendations": recommendations,
    }
