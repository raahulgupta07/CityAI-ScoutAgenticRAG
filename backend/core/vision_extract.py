"""
Vision Page Extraction Pipeline.
Classifies pages, extracts text from text-only pages (free),
sends visual pages to Gemini 3 Flash in batches (vision).
"""
from __future__ import annotations

import json
import base64
from pathlib import Path
from typing import Optional, Callable

import fitz  # PyMuPDF
import PyPDF2
from PIL import Image
from io import BytesIO

from backend.core.config import get_openrouter_client, VISION_MODEL
from backend.core import database as db


VISION_PROMPT = """You are a document page analyzer. Given this page image, extract ALL information:

1. text: ALL text on this page exactly as written (better than OCR)
2. tables: Any tables as JSON array: [{"headers": [...], "rows": [[...], ...]}]
3. image_descriptions: Describe each image/screenshot/diagram on this page
4. key_info: What is the most important information on this page? (1-2 sentences)

Return JSON only:
{
  "text": "...",
  "tables": [],
  "image_descriptions": [],
  "key_info": "..."
}"""


def classify_pages(pdf_path: str) -> dict:
    """
    Classify each page: text-only, visual, or scanned.
    Returns: {page_num: {"type": "text"|"visual"|"scanned", "has_images": bool, "has_tables": bool}}
    """
    doc = fitz.open(pdf_path)
    try:
        page_map = {}

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text") or ""
            images = page.get_images(full=True)

            # Filter significant images (> 150x80)
            sig_images = []
            for img in images:
                try:
                    info = doc.extract_image(img[0])
                    if info and info.get("width", 0) > 150 and info.get("height", 0) > 80:
                        sig_images.append(img)
                except Exception:
                    continue

            has_text = len(text.strip()) > 20
            has_images = len(sig_images) > 0

            # Heuristic for tables: look for tab characters or aligned columns
            has_tables = "\t" in text or text.count("  ") > 10

            if not has_text and has_images:
                page_type = "scanned"
            elif has_images:
                page_type = "visual"
            else:
                page_type = "text"

            page_map[page_num + 1] = {
                "type": page_type,
                "has_text": has_text,
                "has_images": has_images,
                "has_tables": has_tables,
                "text_length": len(text.strip()),
                "image_count": len(sig_images),
            }

        return page_map
    finally:
        doc.close()


def extract_text_pages(pdf_path: str, text_pages: list, sop_id: str, tenant_id: str = None):
    """Extract text from text-only pages using PyPDF2. Free, instant."""
    try:
        reader = PyPDF2.PdfReader(pdf_path)
    except Exception:
        return

    for page_num in text_pages:
        try:
            text = reader.pages[page_num - 1].extract_text() or ""
            db.upsert_page_content(
                sop_id=sop_id,
                page=page_num,
                text_content=text.strip(),
                extraction_method="text",
                has_images=False,
                has_tables=False,
                tenant_id=tenant_id,
            )
        except Exception:
            continue


def extract_vision_pages(pdf_path: str, visual_pages: list, sop_id: str,
                         batch_size: int = 5, on_status: Optional[Callable] = None, tenant_id: str = None):
    """
    Extract content from visual pages using Gemini 3 Flash vision.
    Batches pages to reduce API calls.
    """
    if not visual_pages:
        return

    doc = fitz.open(pdf_path)
    try:
        client = get_openrouter_client()

        # Process in batches
        for i in range(0, len(visual_pages), batch_size):
            batch = visual_pages[i:i + batch_size]
            if on_status:
                on_status("vision", f"Vision extracting pages {batch}...", f"Batch {i // batch_size + 1}")

            # Build multi-image message
            content_parts = [{"type": "text", "text": VISION_PROMPT + f"\n\nDocument: {sop_id}\nPages in this batch: {batch}\nReturn a JSON array with one object per page, in order."}]

            for page_num in batch:
                page = doc[page_num - 1]
                mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 DPI
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                b64 = base64.b64encode(img_bytes).decode("utf-8")

                content_parts.append({"type": "text", "text": f"\n[Page {page_num}]:"})
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
                })

            try:
                response = client.chat.completions.create(
                    model=VISION_MODEL,
                    messages=[{"role": "user", "content": content_parts}],
                    max_tokens=3000,
                    temperature=0,
                )
                raw = response.choices[0].message.content or ""

                # Parse response
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                parsed = json.loads(raw.strip())

                # Handle both array and single object
                if isinstance(parsed, dict):
                    parsed = [parsed]

                for j, page_num in enumerate(batch):
                    if j < len(parsed):
                        page_data = parsed[j]
                        db.upsert_page_content(
                            sop_id=sop_id,
                            page=page_num,
                            text_content="",  # vision replaces text
                            vision_content=page_data.get("text", ""),
                            tables=page_data.get("tables", []),
                            image_descriptions=page_data.get("image_descriptions", []),
                            key_info=page_data.get("key_info", ""),
                            has_images=True,
                            has_tables=len(page_data.get("tables", [])) > 0,
                            extraction_method="vision",
                            tenant_id=tenant_id,
                        )

            except Exception as e:
                if on_status:
                    on_status("vision_error", f"Vision batch failed: {e}")
                # Fallback: extract text at least
                for page_num in batch:
                    try:
                        page = doc[page_num - 1]
                        text = page.get_text("text") or ""
                        db.upsert_page_content(
                            sop_id=sop_id,
                            page=page_num,
                            text_content=text.strip(),
                            extraction_method="text_fallback",
                            has_images=True,
                            tenant_id=tenant_id,
                        )
                    except Exception:
                        continue
    finally:
        doc.close()


def extract_all_pages(pdf_path: str, sop_id: str, on_status: Optional[Callable] = None, tenant_id: str = None) -> dict:
    """
    Full page extraction pipeline:
    1. Classify pages (local, free)
    2. Text extract text-only pages (free)
    3. Vision extract visual/scanned pages (batched LLM)

    Returns stats: {total, text_pages, visual_pages, cost_estimate}
    """
    if on_status:
        on_status("classify", "Classifying pages...")

    page_map = classify_pages(pdf_path)
    total = len(page_map)

    text_pages = [p for p, info in page_map.items() if info["type"] == "text"]
    visual_pages = [p for p, info in page_map.items() if info["type"] in ("visual", "scanned")]

    # Limit vision pages to control API costs
    from backend.core.config import MAX_VISION_PAGES
    if len(visual_pages) > MAX_VISION_PAGES:
        visual_pages = visual_pages[:MAX_VISION_PAGES]

    if on_status:
        on_status("classify_done", f"{total} pages: {len(text_pages)} text, {len(visual_pages)} visual (max {MAX_VISION_PAGES})")

    # Text extraction (free, instant)
    if text_pages:
        if on_status:
            on_status("text_extract", f"Extracting text from {len(text_pages)} pages (free)...")
        extract_text_pages(pdf_path, text_pages, sop_id, tenant_id=tenant_id)

    # Vision extraction (batched LLM calls)
    if visual_pages:
        if on_status:
            on_status("vision_extract", f"Vision extracting {len(visual_pages)} pages (Gemini 3 Flash)...")
        extract_vision_pages(pdf_path, visual_pages, sop_id, on_status=on_status, tenant_id=tenant_id)

    batches = (len(visual_pages) + 4) // 5  # ceil division
    cost = round(batches * 0.003, 4)

    return {
        "total_pages": total,
        "text_pages": len(text_pages),
        "visual_pages": len(visual_pages),
        "batches": batches,
        "cost_estimate": cost,
    }
