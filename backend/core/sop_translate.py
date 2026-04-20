"""
SOP Multi-Language — Translate standardized SOP to other languages.
Takes the structured JSON, translates all text fields via AI, generates new DOCX.
"""
from __future__ import annotations
import json, logging
from backend.core import database as db
from backend.core.config import call_openrouter, ROUTER_MODEL

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "en": "English", "my": "Burmese (Myanmar)", "zh": "Mandarin Chinese",
    "ja": "Japanese", "ko": "Korean", "th": "Thai", "vi": "Vietnamese",
    "hi": "Hindi", "ar": "Arabic", "fr": "French", "de": "German",
    "es": "Spanish", "pt": "Portuguese", "ru": "Russian", "id": "Bahasa Indonesia",
}


def _call_llm(prompt: str) -> str:
    return call_openrouter(prompt, model=ROUTER_MODEL, max_tokens=10000, temperature=0.1)


def translate_sop(sop_id: str, target_lang: str, tenant_id: str = None) -> dict:
    """Translate a standardized SOP to another language. Returns new structured JSON."""

    if target_lang not in SUPPORTED_LANGUAGES:
        return {"error": f"Unsupported language: {target_lang}. Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"}

    lang_name = SUPPORTED_LANGUAGES[target_lang]

    sop = db.get_sop(sop_id, tenant_id=tenant_id)
    if not sop:
        return {"error": "Document not found"}

    std_json = sop.get("standardized_json")
    if isinstance(std_json, str):
        try: std_json = json.loads(std_json)
        except: return {"error": "Invalid standardized JSON"}
    if not std_json:
        return {"error": "Document not standardized yet. Standardize it first."}

    # Build translation prompt — send the full structured JSON
    # Remove non-translatable fields to reduce token usage
    translatable = {}
    for key in ["title", "subtitle", "executive_summary", "purpose", "scope", "definitions",
                "prerequisites", "procedure", "escalation", "references", "ai_improvements"]:
        if key in std_json:
            translatable[key] = std_json[key]

    prompt = f"""Translate this document content from English to {lang_name}.

RULES:
1. Translate ALL text content accurately — do not skip any field
2. Keep technical terms in English if no standard translation exists (e.g., "RACI", "SLA", "KPI")
3. Keep proper nouns, document IDs, and version numbers unchanged
4. Maintain the exact same JSON structure — only translate the text values
5. For procedure steps: translate title, activity, input, output, verification, warnings, notes
6. For definitions: translate both term and definition
7. For scope: translate description, in_scope items, out_of_scope items

Return ONLY valid JSON (no markdown fences):

CONTENT TO TRANSLATE:
{json.dumps(translatable, ensure_ascii=False, indent=2)[:12000]}"""

    try:
        result_text = _call_llm(prompt).strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.rstrip().endswith("```"):
                result_text = result_text.rstrip()[:-3]

        translated = json.loads(result_text.strip())

        # Merge translated fields back into the full structure
        full_translated = std_json.copy()
        full_translated.update(translated)
        full_translated["language"] = target_lang
        full_translated["language_name"] = lang_name
        full_translated["original_language"] = "en"

        # Generate DOCX in target language
        from backend.core.sop_standardize import generate_docx
        docx_bytes = generate_docx(full_translated, sop_id, tenant_id=tenant_id)

        # Save
        data_dir = db.DATA_DIR / "tenants" / tenant_id / "standardized" if tenant_id else db.DATA_DIR / "standardized"
        data_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{sop_id}_standardized_{target_lang}.docx"
        (data_dir / filename).write_bytes(docx_bytes)

        return {
            "status": "translated",
            "sop_id": sop_id,
            "language": lang_name,
            "language_code": target_lang,
            "docx_path": str(data_dir / filename),
            "size_kb": len(docx_bytes) // 1024,
        }
    except json.JSONDecodeError as e:
        return {"error": f"Translation response was not valid JSON: {str(e)[:100]}"}
    except Exception as e:
        return {"error": f"Translation failed: {str(e)[:200]}"}


def get_available_translations(sop_id: str, tenant_id: str = None) -> list:
    """Check which translations exist for a SOP."""
    data_dir = db.DATA_DIR / "tenants" / tenant_id / "standardized" if tenant_id else db.DATA_DIR / "standardized"
    available = []
    for code, name in SUPPORTED_LANGUAGES.items():
        path = data_dir / f"{sop_id}_standardized_{code}.docx"
        if path.exists():
            available.append({"code": code, "name": name, "size_kb": path.stat().st_size // 1024})
    # Also check English (default)
    en_path = data_dir / f"{sop_id}_standardized.docx"
    if en_path.exists():
        available.insert(0, {"code": "en", "name": "English", "size_kb": en_path.stat().st_size // 1024})
    return available
