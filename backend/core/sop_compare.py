"""
SOP Comparison — Compare two versions of the same SOP or two different SOPs.
Shows added/removed/changed sections, steps, definitions.
"""
from __future__ import annotations
import json, logging, difflib
from typing import Optional
from backend.core import database as db

logger = logging.getLogger(__name__)


def compare_sops(sop_id_old: str, sop_id_new: str, tenant_id: str = None) -> dict:
    """Compare two SOPs (or two versions of the same SOP). Returns structured diff."""

    old_sop = db.get_sop(sop_id_old, tenant_id=tenant_id)
    new_sop = db.get_sop(sop_id_new, tenant_id=tenant_id)
    if not old_sop:
        return {"error": f"Document not found: {sop_id_old}"}
    if not new_sop:
        return {"error": f"Document not found: {sop_id_new}"}

    old_json = old_sop.get("standardized_json")
    new_json = new_sop.get("standardized_json")

    if isinstance(old_json, str):
        try: old_json = json.loads(old_json)
        except: old_json = None
    if isinstance(new_json, str):
        try: new_json = json.loads(new_json)
        except: new_json = None

    if not old_json:
        return {"error": f"{sop_id_old} has no standardized version. Standardize it first."}
    if not new_json:
        return {"error": f"{sop_id_new} has no standardized version. Standardize it first."}

    result = {
        "old_sop": sop_id_old,
        "new_sop": sop_id_new,
        "old_title": old_json.get("title", sop_id_old),
        "new_title": new_json.get("title", sop_id_new),
        "old_score": old_sop.get("sop_score", 0),
        "new_score": new_sop.get("sop_score", 0),
        "changes": [],
        "summary": {},
    }

    added, removed, changed = 0, 0, 0

    # Compare simple fields
    for field in ["purpose", "executive_summary", "classification", "review_cycle"]:
        old_val = str(old_json.get(field, ""))
        new_val = str(new_json.get(field, ""))
        if old_val != new_val:
            if not old_val:
                result["changes"].append({"type": "added", "section": field.replace("_", " ").title(), "new": new_val[:300]})
                added += 1
            elif not new_val:
                result["changes"].append({"type": "removed", "section": field.replace("_", " ").title(), "old": old_val[:300]})
                removed += 1
            else:
                result["changes"].append({"type": "changed", "section": field.replace("_", " ").title(), "old": old_val[:300], "new": new_val[:300]})
                changed += 1

    # Compare procedures (step by step)
    old_steps = old_json.get("procedure", [])
    new_steps = new_json.get("procedure", [])

    old_step_titles = {s.get("step_number", i): s.get("title", "") for i, s in enumerate(old_steps)}
    new_step_titles = {s.get("step_number", i): s.get("title", "") for i, s in enumerate(new_steps)}

    all_step_nums = sorted(set(list(old_step_titles.keys()) + list(new_step_titles.keys())))

    for sn in all_step_nums:
        old_t = old_step_titles.get(sn, "")
        new_t = new_step_titles.get(sn, "")
        if old_t and not new_t:
            result["changes"].append({"type": "removed", "section": f"Step {sn}", "old": old_t})
            removed += 1
        elif new_t and not old_t:
            result["changes"].append({"type": "added", "section": f"Step {sn}", "new": new_t})
            added += 1
        elif old_t != new_t:
            # Compare step details
            old_step = next((s for s in old_steps if s.get("step_number") == sn), {})
            new_step = next((s for s in new_steps if s.get("step_number") == sn), {})
            old_activity = old_step.get("activity", old_step.get("description", ""))
            new_activity = new_step.get("activity", new_step.get("description", ""))
            result["changes"].append({
                "type": "changed", "section": f"Step {sn}: {new_t}",
                "old": old_activity[:300], "new": new_activity[:300]
            })
            changed += 1

    # Compare definitions
    old_defs = {d.get("term", ""): d.get("definition", "") for d in old_json.get("definitions", [])}
    new_defs = {d.get("term", ""): d.get("definition", "") for d in new_json.get("definitions", [])}

    for term in set(list(old_defs.keys()) + list(new_defs.keys())):
        if term in new_defs and term not in old_defs:
            result["changes"].append({"type": "added", "section": f"Definition: {term}", "new": new_defs[term][:200]})
            added += 1
        elif term in old_defs and term not in new_defs:
            result["changes"].append({"type": "removed", "section": f"Definition: {term}", "old": old_defs[term][:200]})
            removed += 1
        elif old_defs.get(term) != new_defs.get(term):
            result["changes"].append({"type": "changed", "section": f"Definition: {term}", "old": old_defs[term][:200], "new": new_defs[term][:200]})
            changed += 1

    # Compare RACI
    old_raci = {r.get("activity", ""): r for r in old_json.get("raci", [])}
    new_raci = {r.get("activity", ""): r for r in new_json.get("raci", [])}
    for act in set(list(old_raci.keys()) + list(new_raci.keys())):
        if act in new_raci and act not in old_raci:
            result["changes"].append({"type": "added", "section": f"RACI: {act}"})
            added += 1
        elif act in old_raci and act not in new_raci:
            result["changes"].append({"type": "removed", "section": f"RACI: {act}"})
            removed += 1

    # Compare KPIs
    old_kpis = {k.get("metric", ""): k for k in old_json.get("kpis", [])}
    new_kpis = {k.get("metric", ""): k for k in new_json.get("kpis", [])}
    for metric in set(list(old_kpis.keys()) + list(new_kpis.keys())):
        if metric in new_kpis and metric not in old_kpis:
            result["changes"].append({"type": "added", "section": f"KPI: {metric}", "new": new_kpis[metric].get("target", "")})
            added += 1
        elif metric in old_kpis and metric not in new_kpis:
            result["changes"].append({"type": "removed", "section": f"KPI: {metric}"})
            removed += 1

    # Compare references
    old_refs = set(str(r) for r in old_json.get("references", []))
    new_refs = set(str(r) for r in new_json.get("references", []))
    for ref in new_refs - old_refs:
        result["changes"].append({"type": "added", "section": "Reference", "new": ref})
        added += 1
    for ref in old_refs - new_refs:
        result["changes"].append({"type": "removed", "section": "Reference", "old": ref})
        removed += 1

    result["summary"] = {
        "total_changes": added + removed + changed,
        "added": added,
        "removed": removed,
        "changed": changed,
        "old_steps": len(old_steps),
        "new_steps": len(new_steps),
    }

    return result
