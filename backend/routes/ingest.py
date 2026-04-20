"""Ingest API routes — tenant-aware."""
from __future__ import annotations

import asyncio
import threading
from fastapi import APIRouter

from backend.models.schemas import IngestRequest, IngestStatus

router = APIRouter()

# Per-tenant ingest state (thread-safe)
_ingest_statuses: dict[str, IngestStatus] = {}
_ingest_lock = threading.Lock()


def _get_key(tenant_id: str) -> str:
    return tenant_id


def _get_status(tenant_id: str = None) -> IngestStatus:
    return _ingest_statuses.get(_get_key(tenant_id), IngestStatus())


def _set_status(status: IngestStatus, tenant_id: str = None):
    _ingest_statuses[_get_key(tenant_id)] = status


# ── Tenant-scoped ingest routes ─────────────────────────────────────────────

@router.get("/api/t/{tenant_id}/admin/ingest/status", response_model=IngestStatus)
async def tenant_ingest_status(tenant_id: str):
    return _get_status(tenant_id)


@router.post("/api/t/{tenant_id}/admin/ingest", response_model=IngestStatus)
async def tenant_trigger_ingest(tenant_id: str, request: IngestRequest):
    return _trigger(request, tenant_id=tenant_id)


# ── Shared logic ────────────────────────────────────────────────────────────

def _trigger(request: IngestRequest, tenant_id: str = None) -> IngestStatus:
    with _ingest_lock:
        current = _get_status(tenant_id)
        if current.status == "running":
            return IngestStatus(status="running", message="Already running")
        _set_status(IngestStatus(status="running", message=f"Starting {request.action}..."), tenant_id)

    asyncio.get_event_loop().run_in_executor(None, _run_ingest, request, tenant_id)
    return _get_status(tenant_id)


def _run_ingest(request: IngestRequest, tenant_id: str = None):
    """Run ingestion (blocking, runs in thread)."""
    try:
        if request.action == "extract_images":
            from backend.core.extract_images import extract_all
            _set_status(IngestStatus(status="running", message="Extracting images..."), tenant_id)
            extract_all(force=False, tenant_id=tenant_id)
            _set_status(IngestStatus(status="completed", message="Image extraction done"), tenant_id)

        elif request.action in ("scan", "index_all"):
            _set_status(IngestStatus(status="completed", message="Indexing done (use upload + process workflow)"), tenant_id)

        elif request.action == "extract_knowledge":
            from backend.core.knowledge_extract import extract_all_knowledge
            _set_status(IngestStatus(status="running", message="Extracting knowledge from documents..."), tenant_id)
            results = extract_all_knowledge(tenant_id=tenant_id)
            _set_status(IngestStatus(status="completed", message=f"Extracted knowledge from {len(results)} documents"), tenant_id)

        else:
            _set_status(IngestStatus(status="error", message=f"Unknown action: {request.action}"), tenant_id)

    except Exception as e:
        _set_status(IngestStatus(status="error", message=str(e)), tenant_id)
