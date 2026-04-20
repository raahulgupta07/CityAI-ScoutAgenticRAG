"""
Full ingestion pipeline: Upload → Categorize → Index → Extract → Store
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

import fitz
from PIL import Image

from backend.core.config import OPENROUTER_API_KEY
from backend.core.database import (
    DATA_DIR, PDF_DIR, SCREENSHOT_DIR,
    upsert_sop, upsert_screenshot, upsert_category, update_category_counts,
    get_sop, get_tenant_screenshot_dir, get_tenant_pdf_dir,
)
from backend.core import database as db
from backend.core.categorize import categorize_document

os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY


def process_document(file_path: str, sop_id: Optional[str] = None, on_status: Optional[callable] = None, tenant_id: str = None) -> dict:
    """
    Route document to correct pipeline based on file type.
    PDF → full vision pipeline
    DOCX → direct text+image extraction (no vision needed)
    XLSX → direct data extraction (no vision needed)
    All types → knowledge extraction + embedding + compliance + train
    """
    ext = Path(file_path).suffix.lower()

    if ext in (".docx", ".doc"):
        return process_docx(file_path, sop_id, on_status, tenant_id=tenant_id)
    elif ext in (".xlsx", ".xls"):
        return process_xlsx(file_path, sop_id, on_status, tenant_id=tenant_id)
    else:
        return process_pdf(file_path, sop_id, on_status, tenant_id=tenant_id)


def process_docx(file_path: str, sop_id: Optional[str] = None, on_status: Optional[callable] = None, tenant_id: str = None) -> dict:
    """Pipeline for DOCX files: extract directly, then knowledge + embed + train."""
    def _status(step, msg):
        if on_status:
            on_status(step, msg)

    if not sop_id:
        sop_id = Path(file_path).stem

    _status("docx_extract", "Extracting text and images from DOCX...")
    from backend.core.docx_extract import extract_docx
    result = extract_docx(file_path, sop_id, on_status, tenant_id=tenant_id)
    if result.get("error"):
        return result

    # Categorize
    _status("categorize", "AI categorizing document...")
    from backend.core.categorize import categorize_document
    cat = categorize_document(file_path)

    # Save to database
    _status("saving", "Saving to database...")
    upsert_sop({
        "sop_id": sop_id,
        "title": cat.get("title", sop_id),
        "description": cat.get("title", ""),
        "category_id": cat.get("category", ""),
        "department": cat.get("department", ""),
        "system": cat.get("system", ""),
        "type": cat.get("type", ""),
        "tags": cat.get("tags", []),
        "pdf_path": file_path,
        "page_count": result.get("pages", 0),
        "doc_description": cat.get("title", ""),
        "total_screenshots": result.get("images", 0),
    }, tenant_id=tenant_id)

    # Knowledge + embed + compliance (shared with PDF pipeline)
    _run_post_extraction(sop_id, cat.get("category", ""), result.get("pages", 0), result.get("images", 0), _status, tenant_id=tenant_id)

    return {"sop_id": sop_id, "category": cat.get("category", ""), "pages": result.get("pages", 0), "screenshots": result.get("images", 0)}


def process_xlsx(file_path: str, sop_id: Optional[str] = None, on_status: Optional[callable] = None, tenant_id: str = None) -> dict:
    """Pipeline for XLSX files: extract directly, then knowledge + embed + train."""
    def _status(step, msg):
        if on_status:
            on_status(step, msg)

    if not sop_id:
        sop_id = Path(file_path).stem

    _status("xlsx_extract", "Extracting data from XLSX...")
    from backend.core.xlsx_extract import extract_xlsx
    result = extract_xlsx(file_path, sop_id, on_status, tenant_id=tenant_id)
    if result.get("error"):
        return result

    # Categorize
    _status("categorize", "AI categorizing document...")
    from backend.core.categorize import categorize_document
    cat = categorize_document(file_path)

    # Save to database
    _status("saving", "Saving to database...")
    upsert_sop({
        "sop_id": sop_id,
        "title": cat.get("title", sop_id),
        "description": cat.get("title", ""),
        "category_id": cat.get("category", ""),
        "department": cat.get("department", ""),
        "system": cat.get("system", ""),
        "type": cat.get("type", ""),
        "tags": cat.get("tags", []),
        "pdf_path": file_path,
        "page_count": result.get("pages", 0),
        "doc_description": cat.get("title", ""),
        "total_screenshots": 0,
    }, tenant_id=tenant_id)

    _run_post_extraction(sop_id, cat.get("category", ""), result.get("pages", 0), 0, _status, tenant_id=tenant_id)

    return {"sop_id": sop_id, "category": cat.get("category", ""), "pages": result.get("pages", 0), "screenshots": 0}


def _run_post_extraction(sop_id: str, category_id: str, page_count: int, screenshot_count: int, _status, tenant_id: str = None):
    """Shared post-extraction steps: knowledge + embed + compliance + train."""
    update_category_counts(tenant_id=tenant_id)

    _status("extracting_knowledge", "Extracting Q&A pairs and search keywords...")
    try:
        from backend.core.knowledge_extract import extract_knowledge
        extract_knowledge(sop_id, tenant_id=tenant_id)
    except Exception as e:
        _status("knowledge_error", f"Knowledge error: {e}")

    _status("embedding", "Embedding in PgVector...")
    try:
        from backend.core.database import embed_document_pages
        embedded = embed_document_pages(sop_id, tenant_id=tenant_id)
        _status("embed_done", f"Embedded {embedded} pages")
    except Exception as e:
        _status("embed_error", f"Embedding error: {e}")

    _status("compliance", "Running compliance check...")
    try:
        from backend.core.compliance import check_compliance
        comp = check_compliance(sop_id, tenant_id=tenant_id)
        _status("compliance_done", f"Quality: {comp.get('quality_score', '?')}/100")
    except Exception as e:
        _status("compliance_error", f"Compliance error: {e}")

    # SOP Standardization moved to trainer.py (runs after training + discovery, then re-embeds)

    _status("done", f"Done: {sop_id} → {category_id} ({page_count}p, {screenshot_count} imgs)")
    if tenant_id:
        try:
            db.log_usage(tenant_id, "process_document", cost_usd=0.01, metadata={"sop_id": sop_id, "pages": page_count})
            db.log_audit(tenant_id, "process_document", resource_type="sop", resource_id=sop_id, details=f"{page_count} pages, {screenshot_count} screenshots")
        except Exception: pass


def process_pdf(pdf_path: str, sop_id: Optional[str] = None, on_status: Optional[callable] = None, tenant_id: str = None) -> dict:
    """
    Full pipeline for one PDF:
    1. AI categorize
    2. Copy to organized folder
    3. Get page count
    4. Extract screenshots at 300 DPI
    5. Store in database

    Returns: {"sop_id": str, "category": str, "screenshots": int, "error": str?}
    """
    def _status(step: str, msg: str, *args):
        if on_status:
            on_status(step, msg)

    pdf_path = str(pdf_path)
    if not Path(pdf_path).exists():
        return {"error": f"File not found: {pdf_path}"}

    if not sop_id:
        sop_id = Path(pdf_path).stem

    # ── Step 1: AI Categorize ────────────────────────────────────────────
    _status("categorizing", f"AI categorizing {sop_id}...")
    cat = categorize_document(pdf_path)

    category_id = cat.get("category", "uncategorized")
    title = cat.get("title", sop_id)
    department = cat.get("department", "")
    system = cat.get("system", "")
    sop_type = cat.get("type", "")
    tags = cat.get("tags", [])

    # Create category if needed
    parts = category_id.split("/")
    for i in range(len(parts)):
        cat_id = "/".join(parts[:i + 1])
        parent = "/".join(parts[:i]) if i > 0 else ""
        upsert_category(cat_id, parts[i], parent, tenant_id=tenant_id)

    # ── Step 2: Copy PDF to organized folder ─────────────────────────────
    _status("storing", f"Storing PDF in {category_id}/")
    pdf_base = get_tenant_pdf_dir(tenant_id)
    dest_dir = pdf_base / category_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{sop_id}.pdf"
    if not dest_path.exists() or str(dest_path) != pdf_path:
        shutil.copy2(pdf_path, dest_path)

    # ── Step 3: Get page count ───────────────────────────────────────────
    page_count = 0
    doc_description = cat.get("title", "")
    try:
        doc = fitz.open(str(dest_path))
        page_count = len(doc)
        doc.close()
        _status("pages", f"Document has {page_count} pages")
    except Exception:
        pass

    # ── Step 4: Vision page extraction ──────────────────────────────────
    _status("vision", "Classifying and extracting page content...")
    vision_stats = {"total_pages": 0, "text_pages": 0, "visual_pages": 0}
    try:
        from backend.core.vision_extract import extract_all_pages
        vision_stats = extract_all_pages(str(dest_path), sop_id, on_status=_status, tenant_id=tenant_id)
        _status("vision_done", f"Pages extracted: {vision_stats['text_pages']} text + {vision_stats['visual_pages']} vision (~${vision_stats.get('cost_estimate', 0)})")
    except Exception as e:
        _status("vision_error", f"Vision extraction error: {e}")

    # ── Step 5: Extract screenshots at 300 DPI ───────────────────────────
    _status("extracting", "Extracting screenshots at 300 DPI...")
    screenshot_count = 0
    screenshot_dir = get_tenant_screenshot_dir(tenant_id) / sop_id
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(str(dest_path))
        if page_count == 0:
            page_count = len(doc)

        DPI = 300
        SCALE = DPI / 72.0
        MIN_W, MIN_H = 150, 80
        PADDING = 15

        for page_num in range(len(doc)):
            page = doc[page_num]
            images = page.get_images(full=True)
            rendered = None
            img_index = 0

            for img_ref in images:
                xref = img_ref[0]
                try:
                    img_data = doc.extract_image(xref)
                    if not img_data or img_data["width"] < MIN_W or img_data["height"] < MIN_H:
                        continue

                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue

                    rect = rects[0]
                    img_index += 1

                    if rendered is None:
                        mat = fitz.Matrix(SCALE, SCALE)
                        pix = page.get_pixmap(matrix=mat)
                        rendered = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    x0 = max(0, int(rect.x0 * SCALE) - PADDING)
                    y0 = max(0, int(rect.y0 * SCALE) - PADDING)
                    x1 = min(rendered.width, int(rect.x1 * SCALE) + PADDING)
                    y1 = min(rendered.height, int(rect.y1 * SCALE) + PADDING)

                    cropped = rendered.crop((x0, y0, x1, y1))
                    filename = f"p{page_num + 1}_img{img_index}.png"
                    save_path = screenshot_dir / filename
                    cropped.save(str(save_path), "PNG")

                    upsert_screenshot(sop_id, page_num + 1, img_index, filename, cropped.width, cropped.height, tenant_id=tenant_id)
                    screenshot_count += 1
                except Exception:
                    continue

        doc.close()
    except Exception as e:
        _status("extracting", f"Image extraction error: {e}")

    # Brief pause to avoid OpenRouter rate limits between LLM-heavy steps
    import time as _time
    _time.sleep(3)

    # ── Step 5a: Enhance documentation ───────────────────────────────────
    _status("enhancing", "Enhancing documentation (text + screenshots → steps)...")
    enhance_stats = {}
    try:
        from backend.core.enhance import enhance_document
        enhance_stats = enhance_document(sop_id, on_status=_status, tenant_id=tenant_id)
        if enhance_stats.get("status") != "skipped":
            _status("enhance_done", f"Enhanced {enhance_stats.get('pages_enhanced', 0)} pages, {enhance_stats.get('missing_info_found', 0)} gaps, {enhance_stats.get('faqs_generated', 0)} FAQs")
    except Exception as e:
        _status("enhance_error", f"Enhancement error: {e}")

    # ── Step 6: Store in database ────────────────────────────────────────
    _status("saving", "Saving to database...")
    upsert_sop({
        "sop_id": sop_id,
        "title": title,
        "description": doc_description,
        "category_id": category_id,
        "department": department,
        "system": system,
        "type": sop_type,
        "tags": tags,
        "pdf_path": str(dest_path),
        "page_count": page_count,
        "doc_description": doc_description,
        "total_screenshots": screenshot_count,
        "indexed_at": datetime.now().isoformat(),
    }, tenant_id=tenant_id)

    update_category_counts(tenant_id=tenant_id)

    _time.sleep(3)  # Rate limit pause

    # ── Step 6: Extract knowledge ────────────────────────────────────────
    _status("extracting_knowledge", "Extracting Q&A pairs and search keywords...")
    try:
        from backend.core.knowledge_extract import extract_knowledge
        knowledge_result = extract_knowledge(sop_id, tenant_id=tenant_id)
        if knowledge_result and knowledge_result.get("error"):
            _status("extracting_knowledge", f"Knowledge extraction failed: {knowledge_result['error']} — retrying...")
            _time.sleep(5)  # Wait longer before retry
            knowledge_result = extract_knowledge(sop_id, tenant_id=tenant_id)
            if knowledge_result and knowledge_result.get("error"):
                _status("extracting_knowledge", f"Knowledge extraction failed again: {knowledge_result['error']}")
            else:
                _status("extracting_knowledge", f"Q&A extracted: {knowledge_result.get('qa_pairs', 0)} pairs, {knowledge_result.get('search_keywords', 0)} keywords")
        else:
            _status("extracting_knowledge", f"Q&A extracted: {knowledge_result.get('qa_pairs', 0)} pairs, {knowledge_result.get('search_keywords', 0)} keywords")
    except Exception as e:
        _status("extracting_knowledge", f"Knowledge extraction error: {e}")

    # ── Step 7: Embed pages in PgVector ──────────────────────────────────
    _status("embedding", "Embedding pages in PgVector for semantic search...")
    embedded_count = 0
    try:
        from backend.core.database import embed_document_pages
        embedded_count = embed_document_pages(sop_id, tenant_id=tenant_id)
        _status("embedding_done", f"Embedded {embedded_count} pages in PgVector")
    except Exception as e:
        _status("embedding_error", f"Embedding error: {e}")

    # ── Step 7b: Feed standardized content into embeddings if available ──
    sop_data = db.get_sop(sop_id, tenant_id=tenant_id)
    std_json = sop_data.get("standardized_json") if sop_data else None
    if std_json:
        if isinstance(std_json, str):
            try: std_json = json.loads(std_json)
            except: std_json = None
        if std_json and std_json.get("procedure"):
            _status("embedding", "Adding standardized procedure steps to embeddings...")
            std_texts = []
            for step in std_json.get("procedure", []):
                step_text = f"Step {step.get('step_number', '')}: {step.get('title', '')}\n{step.get('activity', '')}\nVerification: {step.get('verification', '')}"
                std_texts.append(step_text)
            if std_texts:
                from backend.core.config import get_openrouter_client, EMBEDDING_MODEL
                client = get_openrouter_client()
                for i in range(0, len(std_texts), 20):
                    batch = std_texts[i:i+20]
                    try:
                        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
                        for j, emb in enumerate(resp.data):
                            db.upsert_embedding(sop_id=sop_id, page=900+i+j, chunk_index=0,
                                content=batch[j][:500], embedding=emb.embedding,
                                metadata={"sop_id": sop_id, "page": 900+i+j, "source": "standardized"},
                                tenant_id=tenant_id)
                    except: pass
                embedded_count += len(std_texts)
                _status("embedding", f"Added {len(std_texts)} standardized procedure embeddings")

    # ── Step 8: Compliance check ────────────────────────────────────────
    _status("compliance", "Running compliance check...")
    try:
        from backend.core.compliance import check_compliance
        comp = check_compliance(sop_id, tenant_id=tenant_id)
        _status("compliance_done", f"Quality score: {comp.get('quality_score', '?')}/100")
    except Exception as e:
        _status("compliance_error", f"Compliance check error: {e}")

    _status("done", f"Done: {sop_id} → {category_id} ({page_count} pages, {screenshot_count} screenshots, {embedded_count} embeddings)")

    return {
        "sop_id": sop_id,
        "category": category_id,
        "title": title,
        "page_count": page_count,
        "screenshots": screenshot_count,
    }
