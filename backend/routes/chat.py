"""Chat API route with SSE streaming + real-time tool call reporting."""
from __future__ import annotations

import json
import asyncio
import logging
import re as _re
import time
from queue import Queue
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.models.schemas import ChatRequest
from backend.core.agent import ask, generate_suggestions
from backend.core import database as db
from backend.core.tools import set_status_queue

router = APIRouter()
logger = logging.getLogger(__name__)


_UNCERTAINTY_PHRASES = ("i'm not sure", "i don't have", "no matching", "not found")


def score_answer_quality(answer: str, sources: list, question: str) -> int:
    """Score answer quality 0-100 based on content signals."""
    score = 0
    if _re.search(r'\[REF:[^\]]+\]', answer):
        score += 25
    if len(answer) > 100:
        score += 15
    if len(answer) > 300:
        score += 10
    if sources and len(sources) > 0:
        score += 20
    if _re.search(r'\[IMG:[^\]]+\]', answer):
        score += 10
    if not any(p in answer.lower() for p in _UNCERTAINTY_PHRASES):
        score += 15
    if _re.search(r'(^[\s]*[-*•]|\d+\.\s|^#{2,})', answer, _re.MULTILINE):
        score += 5
    return min(score, 100)


def log_query(question: str, sources: list, model: str, duration: float, answer: str = "", tenant_id: str = None, quality_score: int = None) -> int:
    sop_ids = [s.get("sop_id", "") if isinstance(s, dict) else s for s in sources]
    return db.log_query(question, sop_ids, model, duration, answer, tenant_id=tenant_id, quality_score=quality_score)


async def chat_event_stream(request: ChatRequest, tenant_id: str = None):
    """Generate SSE events with real-time tool call reporting."""
    t0 = time.time()

    # Create a thread-safe queue for tool status reports
    status_queue: Queue = Queue()
    client_disconnected = False

    history = [{"role": m.role, "content": m.content} for m in request.history]

    def on_status(step: str, message: str, detail: str = ""):
        status_queue.put_nowait({"step": step, "message": message, "detail": detail})

    def run_agent():
        # Set the status queue so tools can report in real-time
        set_status_queue(status_queue)
        try:
            return ask(
                question=request.question,
                department_filter=request.department,
                sop_id_filter=request.sop_id,
                chat_history=history,
                on_status=on_status,
                tenant_id=tenant_id,
            )
        finally:
            set_status_queue(None)

    loop = asyncio.get_event_loop()
    agent_task = asyncio.ensure_future(loop.run_in_executor(None, run_agent))

    try:
        # Stream status events while agent is running
        while not agent_task.done():
            try:
                await asyncio.sleep(0.2)
                while not status_queue.empty():
                    status = status_queue.get_nowait()
                    yield f"event: status\ndata: {json.dumps(status)}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                client_disconnected = True
                logger.debug(f"SSE client disconnected for tenant {tenant_id}")
                return
            except Exception as e:
                logger.debug(f"SSE status drain error: {e}")

        # Drain remaining status events
        while not status_queue.empty():
            status = status_queue.get_nowait()
            yield f"event: status\ndata: {json.dumps(status)}\n\n"

        result = agent_task.result()

        # Score answer quality before logging
        quality = score_answer_quality(result.get("answer", ""), result.get("sources", []), request.question)

        # Log and get query ID for feedback
        query_id = log_query(request.question, result.get("sources", []), result.get("model_used", ""), time.time() - t0, result.get("answer", ""), tenant_id=tenant_id, quality_score=quality)

        # Stream answer token by token (ChatGPT-style)
        # Never break [REF:...] or [IMG:...] tags across chunks
        import re
        answer_text = result["answer"]
        segments = re.split(r'(\[(?:REF|IMG):[^\]]+\])', answer_text)
        for seg in segments:
            if not seg:
                continue
            if seg.startswith("[REF:") or seg.startswith("[IMG:"):
                yield f"event: token\ndata: {json.dumps({'token': seg})}\n\n"
                await asyncio.sleep(0.01)
            else:
                i = 0
                while i < len(seg):
                    end = min(i + 40, len(seg))
                    if end < len(seg):
                        sp = seg.rfind(" ", i, end + 10)
                        if sp > i:
                            end = sp + 1
                    yield f"event: token\ndata: {json.dumps({'token': seg[i:end]})}\n\n"
                    i = end
                    await asyncio.sleep(0.02)
        yield f"event: answer_done\ndata: {json.dumps({'query_id': query_id})}\n\n"

        # Send sources
        if result.get("sources"):
            yield f"event: sources\ndata: {json.dumps({'sources': result['sources'], 'model': result['model_used']})}\n\n"

        # Send image map
        if result.get("image_map"):
            image_map_urls = {}
            for key, img in result["image_map"].items():
                sop_id = img.get("sop_id", "")
                filename = Path(img.get("path", "")).name
                default_url = f"/api/t/{tenant_id}/images/{sop_id}/{filename}"
                image_map_urls[key] = {
                    "page": img["page"],
                    "index": img["index"],
                    "sop_id": sop_id,
                    "url": img.get("url", default_url),
                    "width": img.get("width", 0),
                    "height": img.get("height", 0),
                }
            yield f"event: images\ndata: {json.dumps({'image_map': image_map_urls})}\n\n"

        # Generate follow-up suggestions
        try:
            suggestions = await loop.run_in_executor(
                None,
                lambda: generate_suggestions(
                    request.question,
                    result["answer"],
                    result.get("sources", []),
                )
            )
            if suggestions:
                yield f"event: suggestions\ndata: {json.dumps({'suggestions': suggestions})}\n\n"
        except Exception as e:
            logger.debug(f"Suggestion generation failed: {e}")

        yield f"event: done\ndata: {json.dumps({})}\n\n"

    except (asyncio.CancelledError, GeneratorExit):
        client_disconnected = True
        logger.debug(f"SSE client disconnected for tenant {tenant_id}")
    finally:
        # Cancel agent task if client disconnected and agent is still running
        if client_disconnected and not agent_task.done():
            agent_task.cancel()
            logger.debug(f"Cancelled orphaned agent task for tenant {tenant_id}")


@router.post("/api/t/{tenant_id}/chat")
async def tenant_chat(tenant_id: str, request: ChatRequest):
    """Tenant-scoped chat — agent only sees this tenant's documents."""
    return StreamingResponse(
        chat_event_stream(request, tenant_id=tenant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

@router.put("/api/t/{tenant_id}/chat/feedback")
async def tenant_feedback(tenant_id: str, request: dict):
    """Tenant-scoped feedback with learning side effects."""
    query_id = request.get("query_id")
    feedback = request.get("feedback")
    if not query_id or feedback not in ("up", "down"):
        return {"error": "query_id and feedback required"}

    # 1. Save feedback
    db.update_query_feedback(query_id, feedback, request.get("comment", ""), tenant_id=tenant_id)

    # 2. Fetch query for learning
    query = db.get_query_by_id(query_id, tenant_id=tenant_id)
    if not query:
        return {"status": "saved"}

    question = query.get("question", "")
    sop_ids = query.get("sources", [])
    stop = {"the","and","for","are","but","not","you","all","can","had","was","one","our","has","how","what","when","where","which","who","why","this","that","with","from","will","would","could","should","about","into","them","then","than","been","have","each","make","like","just","over","also","more","some","very"}
    keywords = list(dict.fromkeys(w for w in question.lower().split() if len(w) > 2 and w not in stop))

    if feedback == "up" and sop_ids and keywords:
        # Create intent routes from positive feedback
        for sid in sop_ids[:3]:
            db.upsert_intent_route(
                intent=question, keywords=keywords, sop_id=sid, pages="",
                reason=f"Positive feedback (query #{query_id})", source="feedback",
                tenant_id=tenant_id,
            )
        # Bump wiki hits for matching pages
        try:
            for wp in db.search_wiki_pages(question, limit=3, tenant_id=tenant_id):
                db.bump_wiki_hit(wp["id"], tenant_id=tenant_id)
        except Exception as e:
            logger.debug(f"Wiki hit bump failed: {e}")

    elif feedback == "down" and keywords:
        # Save negative route
        where = ", ".join(sop_ids[:3]) if sop_ids else "unknown"
        db.upsert_intent_route(
            intent=f"NEGATIVE: {question}", keywords=keywords, sop_id=where, pages="",
            reason=f"DEAD END: Negative feedback (query #{query_id}). {request.get('comment', '')}",
            source="negative", tenant_id=tenant_id,
        )

    # 3. Audit log
    try:
        db.log_audit(tenant_id, f"feedback_{feedback}", resource_type="query",
                     resource_id=str(query_id), details=f"Q: {question[:100]}")
    except Exception as e:
        logger.debug(f"Audit log failed: {e}")

    return {"status": "saved", "learned": True}


# ── Tenant-Scoped Conversations ──────────────────────────────────────────────

@router.post("/api/t/{tenant_id}/conversations")
async def tenant_create_conversation(tenant_id: str, request: dict):
    import uuid
    conv_id = request.get("id") or str(uuid.uuid4())[:12]
    return db.create_conversation(conv_id, request.get("title", "New conversation"), tenant_id=tenant_id)

@router.get("/api/t/{tenant_id}/conversations")
async def tenant_list_conversations(tenant_id: str):
    return db.list_conversations(tenant_id=tenant_id)

@router.get("/api/t/{tenant_id}/conversations/{conv_id}/messages")
async def tenant_get_messages(tenant_id: str, conv_id: str):
    return db.get_conversation_messages(conv_id, tenant_id=tenant_id)

@router.delete("/api/t/{tenant_id}/conversations/{conv_id}")
async def tenant_delete_conversation(tenant_id: str, conv_id: str):
    db.delete_conversation(conv_id, tenant_id=tenant_id)
    return {"status": "deleted"}

@router.post("/api/t/{tenant_id}/conversations/{conv_id}/messages")
async def tenant_add_message(tenant_id: str, conv_id: str, request: dict):
    db.add_conversation_message(conv_id, request.get("role", "user"), request.get("content", ""),
        request.get("sources"), request.get("image_map"), request.get("suggestions"), tenant_id=tenant_id)
    msgs = db.get_conversation_messages(conv_id, tenant_id=tenant_id)
    if len(msgs) == 1 and msgs[0]["role"] == "user":
        db.update_conversation_title(conv_id, msgs[0]["content"][:50], tenant_id=tenant_id)
    return {"status": "saved"}
