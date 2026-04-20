"""Pydantic schemas for API request/response validation."""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    department: Optional[str] = None
    sop_id: Optional[str] = None
    history: List[ChatMessage] = []


class ImageInfo(BaseModel):
    page: int
    index: int
    path: str
    sop_id: str = ""
    width: int = 0
    height: int = 0


class SourceInfo(BaseModel):
    sop_id: str
    doc_name: str = ""
    pages: str = ""
    department: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceInfo] = []
    images: List[ImageInfo] = []
    image_map: Dict[str, Any] = {}
    model_used: str = ""


# ── SOPs ─────────────────────────────────────────────────────────────────────

class SOPSummary(BaseModel):
    sop_id: str
    doc_name: str = ""
    doc_description: str = ""
    department: str = ""
    page_count: int = 0
    total_extracted_images: int = 0


class SOPDetail(BaseModel):
    sop_id: str
    doc_id: str = ""
    doc_name: str = ""
    doc_description: str = ""
    department: str = ""
    page_count: int = 0
    file_path: str = ""
    pages_with_images: List[int] = []
    extracted_images: Dict[str, Any] = {}
    total_extracted_images: int = 0
    tree_structure: Any = None


# ── Stats ────────────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_indexed: int = 0
    errors: int = 0
    departments: int = 0
    total_pages: int = 0
    pages_with_images: int = 0


# ── Settings ─────────────────────────────────────────────────────────────────

class LLMSettings(BaseModel):
    provider: str = "openrouter"
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    router_model: str = "google/gemini-2.0-flash-001"       # Categorize + extract (fast, cheap)
    vision_model: str = "google/gemini-3-flash-preview"      # Chat + vision (smart)
    embedding_model: str = "text-embedding-3-small"          # PgVector embeddings


class WidgetSettings(BaseModel):
    title: str = "Document Assistant"
    primary_color: str = "#1976d2"
    logo_url: str = ""
    welcome_message: str = "Hi! Ask me about any document in our library."
    max_images: int = 8
    allowed_domains: List[str] = ["*"]


class AppSettings(BaseModel):
    llm: LLMSettings = LLMSettings()
    widget: WidgetSettings = WidgetSettings()


# ── Ingest ───────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    action: str = "scan"  # "scan" | "index_all" | "extract_images"
    limit: Optional[int] = None
    sop_id: Optional[str] = None


class IngestStatus(BaseModel):
    status: str = "idle"  # "idle" | "running" | "completed" | "error"
    total: int = 0
    processed: int = 0
    errors: int = 0
    current_sop: str = ""
    message: str = ""
