"""
Evaluation runner for the ITSM Agent.
Runs test cases, scores results, returns detailed report.
"""
from __future__ import annotations

import time
from typing import Optional
from backend.evals.test_cases import TestCase, get_test_cases
from backend.core.agent import ask


def score_result(test: TestCase, answer: str, sources: list) -> dict:
    """Score a single test result."""
    answer_lower = answer.lower()

    # Check expected strings
    found_strings = []
    missing_strings = []
    for s in test.expected_strings:
        if s.lower() in answer_lower:
            found_strings.append(s)
        else:
            missing_strings.append(s)

    if test.expected_strings:
        string_score = len(found_strings) / len(test.expected_strings)
    else:
        string_score = 1.0  # No expected strings = pass if no crash

    # Check golden document
    doc_match = False
    if test.golden_doc:
        source_ids = [s.get("sop_id", "") for s in sources] if sources else []
        doc_match = test.golden_doc in source_ids

    # Overall score
    if string_score >= 0.8 and (not test.golden_doc or doc_match):
        status = "pass"
    elif string_score >= 0.5:
        status = "partial"
    else:
        status = "fail"

    return {
        "status": status,
        "string_score": round(string_score, 2),
        "found_strings": found_strings,
        "missing_strings": missing_strings,
        "doc_match": doc_match,
        "golden_doc": test.golden_doc,
    }


def run_single_eval(test: TestCase, tenant_id: str = None) -> dict:
    """Run a single test case."""
    t0 = time.time()
    try:
        result = ask(test.question, tenant_id=tenant_id)
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        duration = round(time.time() - t0, 2)

        scoring = score_result(test, answer, sources)

        return {
            "question": test.question,
            "category": test.category,
            "description": test.description,
            "answer_preview": answer[:300],
            "duration_s": duration,
            **scoring,
        }
    except Exception as e:
        return {
            "question": test.question,
            "category": test.category,
            "description": test.description,
            "answer_preview": f"ERROR: {e}",
            "duration_s": round(time.time() - t0, 2),
            "status": "error",
            "string_score": 0,
            "found_strings": [],
            "missing_strings": test.expected_strings,
            "doc_match": False,
            "golden_doc": test.golden_doc,
        }


def run_all_evals(category: Optional[str] = None, tenant_id: str = None) -> dict:
    """Run all test cases and return summary."""
    tests = get_test_cases(category)
    results = []

    for test in tests:
        result = run_single_eval(test, tenant_id=tenant_id)
        results.append(result)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    partial = sum(1 for r in results if r["status"] == "partial")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    avg_duration = round(sum(r["duration_s"] for r in results) / max(total, 1), 2)

    # Category breakdown
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "pass": 0, "partial": 0, "fail": 0, "error": 0}
        categories[cat]["total"] += 1
        categories[cat][r["status"]] += 1

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "partial": partial,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / max(total, 1) * 100, 1),
            "avg_duration_s": avg_duration,
        },
        "categories": categories,
        "results": results,
    }
