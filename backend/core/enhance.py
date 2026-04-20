"""
Document Enhancement Pipeline.
Combines text + screenshots → click-by-click instructions + missing info + FAQs.
Optimized: 1 combined AI call per page (not 3), skips text-only pages, parallel batches.
"""
from __future__ import annotations

import json
import base64
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed


from backend.core.config import get_openrouter_client, VISION_MODEL, ROUTER_MODEL
from backend.core import database as db
from backend.core.database import SCREENSHOT_DIR, get_tenant_screenshot_dir


# Combined prompt: enhance + missing info + FAQs in ONE call
ENHANCE_COMBINED_PROMPT = """You are a technical documentation expert AND auditor. Given:
1. The original text from a document page
2. Screenshots from that page (if any)

CRITICAL: If the document contains non-English text (Burmese, Myanmar, Chinese, etc.), PRESERVE IT EXACTLY. Include both the original language text AND English in your enhanced output. Do NOT remove or skip non-English content.

Do ALL THREE tasks in one response:

**TASK 1 - ENHANCE:** Create step-by-step instructions:
- Read each screenshot — identify every UI element, button, menu, field
- Create numbered steps: "Click X", "Type Y in Z field", "Navigate to A > B"
- Include EXACT values visible in screenshots: names, numbers, emails, dates
- Reference screenshots with [IMG:page:index] tags
- If no screenshots, restructure text into clear actionable steps

**TASK 2 - MISSING INFO:** Find gaps:
- Vague references: "contact the team" (WHICH team?)
- Missing URLs: "go to the portal" (WHAT URL?)
- Undefined acronyms, missing prerequisites, incomplete steps

**TASK 3 - FAQs:** Generate 3-5 real-world questions users would ask:
- Not generic ("What is this?") but specific problems users face
- "My employee can't log in", "Error when trying to reset", etc.

Return JSON only:
{
  "enhanced_content": "Step 1: ... Step 2: ...",
  "missing_info": ["specific gap 1", "specific gap 2"],
  "completeness_score": 0-100,
  "faqs": ["question 1", "question 2"]
}"""

# Lighter prompt for text-only pages (no vision needed, cheaper model)
TEXT_ONLY_PROMPT = """You are a documentation expert. Given this document page text, extract:

1. missing_info: Any vague references, missing URLs, undefined acronyms, incomplete steps
2. faqs: 2-3 real-world questions users would ask about this content

Return JSON only:
{
  "missing_info": ["gap 1", "gap 2"],
  "faqs": ["question 1", "question 2"]
}"""


def _enhance_page_combined(client: OpenAI, sop_id: str, page_num: int,
                           text: str, screenshot_paths: list, tenant_id: str = None) -> dict:
    """Enhance a single page with combined prompt (enhance + missing + FAQ in 1 call)."""
    content_parts = [
        {"type": "text", "text": f"{ENHANCE_COMBINED_PROMPT}\n\nDocument: {sop_id}, Page {page_num}\n\nOriginal text:\n{text[:3000]}"}
    ]

    # Add screenshot images — use tenant-scoped directory
    ss_dir = get_tenant_screenshot_dir(tenant_id)
    for i, img_path in enumerate(screenshot_paths[:3]):
        path = Path(img_path)
        if not path.exists():
            path = ss_dir / sop_id / img_path
        if path.exists():
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            content_parts.append({"type": "text", "text": f"\n[Screenshot {i+1} from page {page_num}]:"})
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
            })

    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": content_parts}],
            max_tokens=2000,
            temperature=0,
        )
        raw = response.choices[0].message.content or "{}"
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {"enhanced_content": text, "missing_info": [], "faqs": [], "error": str(e)}


def _analyze_text_page(client: OpenAI, text: str) -> dict:
    """Lightweight analysis for text-only pages (no vision, cheaper model)."""
    if len(text.strip()) < 50:
        return {"missing_info": [], "faqs": []}

    try:
        response = client.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[
                {"role": "system", "content": TEXT_ONLY_PROMPT},
                {"role": "user", "content": text[:3000]},
            ],
            max_tokens=400,
            temperature=0,
        )
        raw = response.choices[0].message.content or "{}"
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {"missing_info": [], "faqs": []}


def _process_single_page(client: OpenAI, sop_id: str, sop_title: str,
                          page_data: dict, page_screenshots: list, tenant_id: str = None) -> dict:
    """Process a single page — choose strategy based on whether it has screenshots."""
    page_num = page_data["page"]
    text = page_data.get("vision_content") or page_data.get("text_content") or ""
    screenshot_paths = [s.get("path", "") for s in page_screenshots]
    has_screenshots = bool(screenshot_paths)

    if has_screenshots:
        # Full enhancement: text + screenshots → combined AI call (vision model)
        result = _enhance_page_combined(client, sop_id, page_num, text, screenshot_paths, tenant_id=tenant_id)
        enhanced = result.get("enhanced_content", text)
        missing = result.get("missing_info", [])
        faqs = result.get("faqs", [])
    else:
        # Text-only: lightweight analysis (cheaper model, no vision)
        result = _analyze_text_page(client, text)
        enhanced = text  # Keep original text, no enhancement needed
        missing = result.get("missing_info", [])
        faqs = result.get("faqs", [])

    return {
        "page_num": page_num,
        "enhanced_content": enhanced,
        "missing_info": missing,
        "faqs": faqs,
        "had_screenshots": has_screenshots,
        "extraction_method": page_data.get("extraction_method", "text"),
        "has_images": page_data.get("has_images", False),
        "has_tables": page_data.get("has_tables", False),
    }


def enhance_document(sop_id: str, on_status: Optional[Callable] = None, tenant_id: str = None) -> dict:
    """
    Enhance all pages of a document.
    Optimized: 1 AI call per page (not 3), parallel processing, skips already-enhanced.

    For 50-page PDF with 15 visual pages:
      - 15 vision calls (visual pages: enhance + missing + FAQ combined)
      - 35 text calls (text pages: missing + FAQ only, cheaper model)
      - ~50 calls total, parallel 3 at a time
    """
    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return {"error": "Document not found"}

    # Check if already enhanced
    if sop.get("is_enhanced"):
        if on_status:
            on_status("enhance_skip", f"{sop_id} already enhanced, skipping")
        return {"sop_id": sop_id, "status": "skipped", "reason": "already enhanced"}

    pages = db.get_page_contents(sop_id, tenant_id=tenant_id)
    if not pages:
        return {"error": "No page content to enhance"}

    # Filter out already-enhanced pages
    pages_to_process = [p for p in pages if not (p.get("enhanced_content") and len(p["enhanced_content"]) > 50)]
    if not pages_to_process:
        return {"sop_id": sop_id, "status": "skipped", "reason": "all pages already enhanced"}

    screenshots = db.get_screenshots(sop_id, tenant_id=tenant_id)
    visual_count = sum(1 for p in pages_to_process if screenshots.get(str(p["page"]), []))
    text_count = len(pages_to_process) - visual_count

    if on_status:
        on_status("enhance_start", f"Enhancing {len(pages_to_process)} pages ({visual_count} visual + {text_count} text-only)...")

    client = get_openrouter_client()
    sop_title = sop.get("title", sop_id)

    all_results = []
    all_faqs = []
    enhanced_count = 0
    missing_count = 0

    # Process pages in parallel (3 concurrent)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for page_data in pages_to_process:
            page_num = page_data["page"]
            page_screenshots = screenshots.get(str(page_num), [])
            future = executor.submit(
                _process_single_page, client, sop_id, sop_title, page_data, page_screenshots, tenant_id
            )
            futures[future] = page_num

        for future in as_completed(futures):
            page_num = futures[future]
            try:
                result = future.result()
                all_results.append(result)

                # Save to database
                db.upsert_page_content(
                    sop_id=sop_id,
                    page=result["page_num"],
                    enhanced_content=result["enhanced_content"],
                    missing_info=result["missing_info"],
                    faqs=result["faqs"],
                    extraction_method=result["extraction_method"],
                    has_images=result["has_images"],
                    has_tables=result["has_tables"],
                    tenant_id=tenant_id,
                )

                enhanced_count += 1
                missing_count += len(result["missing_info"])
                all_faqs.extend(result["faqs"])

                if on_status:
                    tag = "visual" if result["had_screenshots"] else "text"
                    on_status("enhance_page", f"Page {result['page_num']} done ({tag}, {len(result['faqs'])} FAQs)")

            except Exception as e:
                if on_status:
                    on_status("enhance_error", f"Page {page_num} failed: {e}")

    # Mark document as enhanced
    sop["is_enhanced"] = True
    db.upsert_sop(sop, tenant_id=tenant_id)

    # Auto-generate intent routes from FAQs
    if all_faqs:
        if on_status:
            on_status("faq_routes", f"Creating {len(all_faqs)} intent routes from FAQs...")
        for faq in all_faqs:
            if isinstance(faq, str) and len(faq) > 5:
                words = [w.lower() for w in faq.split() if len(w) > 2]
                db.upsert_intent_route(
                    intent=faq,
                    keywords=words,
                    sop_id=sop_id,
                    reason=f"FAQ from enhancement of {sop.get('title', sop_id)}",
                    source="faq",
                    tenant_id=tenant_id,
                )

    if on_status:
        on_status("enhance_done", f"Enhanced {enhanced_count} pages, {missing_count} gaps, {len(all_faqs)} FAQs")

    return {
        "sop_id": sop_id,
        "pages_enhanced": enhanced_count,
        "missing_info_found": missing_count,
        "faqs_generated": len(all_faqs),
        "all_faqs": all_faqs,
    }
