"""
Extract high-quality screenshots from document PDFs.
Renders pages at 300 DPI and crops to each embedded image area.
Uses PostgreSQL database (not catalog.json).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from backend.core.database import SCREENSHOT_DIR, get_tenant_screenshot_dir
from backend.core import database as db

RENDER_DPI = 300
SCALE = RENDER_DPI / 72.0
MIN_WIDTH = 150
MIN_HEIGHT = 80
CROP_PADDING = 15


def extract_images_from_pdf(pdf_path: str, sop_id: str, tenant_id: str = None) -> dict:
    """Extract all significant screenshots from a PDF at 300 DPI."""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  [ERROR] Cannot open {pdf_path}: {e}")
        return {}

    try:
        mat = fitz.Matrix(SCALE, SCALE)
        extracted = {}
        screenshot_dir = get_tenant_screenshot_dir(tenant_id) / sop_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        for page_num in range(len(doc)):
            page = doc[page_num]
            images = page.get_images(full=True)
            page_images = []
            img_index = 0
            rendered = None

            for img_ref in images:
                xref = img_ref[0]
                try:
                    img_data = doc.extract_image(xref)
                    if not img_data or img_data["width"] < MIN_WIDTH or img_data["height"] < MIN_HEIGHT:
                        continue

                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue

                    rect = rects[0]
                    img_index += 1

                    if rendered is None:
                        pix = page.get_pixmap(matrix=mat)
                        rendered = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    x0 = max(0, int(rect.x0 * SCALE) - CROP_PADDING)
                    y0 = max(0, int(rect.y0 * SCALE) - CROP_PADDING)
                    x1 = min(rendered.width, int(rect.x1 * SCALE) + CROP_PADDING)
                    y1 = min(rendered.height, int(rect.y1 * SCALE) + CROP_PADDING)

                    cropped = rendered.crop((x0, y0, x1, y1))
                    filename = f"p{page_num + 1}_img{img_index}.png"
                    save_path = screenshot_dir / filename
                    cropped.save(str(save_path), "PNG")

                    # Save to database
                    db.upsert_screenshot(sop_id, page_num + 1, img_index, filename, cropped.width, cropped.height, tenant_id=tenant_id)

                    page_images.append({
                        "index": img_index,
                        "filename": filename,
                        "width": cropped.width,
                        "height": cropped.height,
                    })
                except Exception:
                    continue

            if page_images:
                extracted[page_num + 1] = page_images

        return extracted
    finally:
        doc.close()


def extract_all(force: bool = False, tenant_id: str = None):
    """Extract screenshots from all indexed documents."""
    sops = db.list_sops(tenant_id=tenant_id)
    for sop in sops:
        sop_id = sop["sop_id"]
        if not force and sop.get("total_screenshots", 0) > 0:
            print(f"  [SKIP] {sop_id}: already has screenshots")
            continue

        pdf_path = sop.get("pdf_path", "")
        resolved = db.resolve_pdf_path(pdf_path)
        if not resolved:
            print(f"  [SKIP] {sop_id}: PDF not found")
            continue
        pdf_path = resolved

        print(f"  Extracting: {sop_id}")
        extracted = extract_images_from_pdf(pdf_path, sop_id, tenant_id=tenant_id)
        total = sum(len(imgs) for imgs in extracted.values())

        # Update screenshot count
        sop["total_screenshots"] = total
        db.upsert_sop(sop, tenant_id=tenant_id)
        print(f"  Done: {sop_id} → {total} screenshots")
