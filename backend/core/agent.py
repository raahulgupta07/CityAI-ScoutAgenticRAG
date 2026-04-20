"""
Document Intelligence Agent — Powered by Agno Framework
Configurable via instance.yaml for any team/department.
"""
from __future__ import annotations

import json
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.db.postgres.postgres import PostgresDb
from agno.learn import LearningMachine, LearnedKnowledgeConfig, LearningMode

from backend.core.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    VISION_MODEL,
    AGENT_CONFIG,
    APP_NAME,
)
from backend.core.tools import make_tools
from backend.core.config import DATABASE_URL

# ── Build instructions from config ───────────────────────────────────────────

def _get_agent_config(tenant_id: str) -> dict:
    """Get agent config from tenants table."""
    from backend.core import database as db
    base = AGENT_CONFIG.copy()

    tenant = db.get_tenant(tenant_id)
    if tenant:
        base["name"] = tenant.get("agent_name", base.get("name"))
        base["role"] = tenant.get("agent_role", base.get("role"))
        base["focus"] = tenant.get("agent_focus", base.get("focus"))
        base["personality"] = tenant.get("agent_personality", base.get("personality"))
        base["languages"] = tenant.get("agent_languages", base.get("languages", ["English"]))
    return base


def _build_instructions(tenant_id: str = None) -> str:
    """Build agent instructions from current config. Adds tone, style, SOP-mode rules."""
    from backend.core import database as db
    cfg = _get_agent_config(tenant_id)
    name = cfg.get("name", "Document Agent")
    role = cfg.get("role", "document intelligence assistant")
    focus = cfg.get("focus", "organizational documents")
    langs = ", ".join(cfg.get("languages", ["English"]))
    base = _INSTRUCTIONS_TEMPLATE.format(
        agent_name=name, agent_role=role, agent_focus=focus, agent_langs=langs,
    )

    if tenant_id:
        try:
            tenant = db.get_tenant(tenant_id)
            if not tenant:
                return base

            # Tone
            tone = tenant.get("agent_tone", "professional")
            tone_rules = {
                "professional": "\n## Tone: Professional\nMaintain formal, business-appropriate language. Use industry terminology correctly. Be authoritative but approachable.",
                "friendly": "\n## Tone: Friendly\nBe warm and approachable. Use simple, clear language. Add encouragement like 'Great question!' when appropriate.",
                "technical": "\n## Tone: Technical\nUse precise technical terminology. Include system names, error codes, and exact paths. Assume the reader has technical knowledge.",
                "executive": "\n## Tone: Executive\nBe concise and impact-focused. Lead with business outcomes. Use bullet points. No jargon — translate technical concepts.",
                "casual": "\n## Tone: Casual\nBe conversational and relaxed. Use everyday language. Keep it brief and practical.",
            }
            base += tone_rules.get(tone, tone_rules["professional"])

            # Style
            style = tenant.get("agent_style", "step-by-step")
            style_rules = {
                "step-by-step": "\n## Response Style: Step-by-Step\nALWAYS structure answers as numbered steps when explaining how to do something. Each step = one action.",
                "narrative": "\n## Response Style: Narrative\nExplain in flowing paragraphs. Connect ideas with transitions. Tell the story of the process.",
                "concise": "\n## Response Style: Concise\nMaximum 3 sentences per point. Use bullet points. No filler words. Get straight to the answer.",
                "detailed": "\n## Response Style: Detailed\nProvide comprehensive explanations with examples, context, and edge cases. Include 'why' not just 'what'.",
            }
            base += style_rules.get(style, style_rules["step-by-step"])

            # Custom system prompt override
            custom = tenant.get("agent_system_prompt", "")
            if custom and custom.strip():
                base += f"\n\n## Custom Instructions\n{custom.strip()}"

            # Escalation config
            esc_raw = tenant.get("escalation_config", "{}")
            try:
                esc = json.loads(esc_raw) if isinstance(esc_raw, str) else (esc_raw or {})
            except Exception:
                esc = {}
            if esc.get("team") or esc.get("email") or esc.get("url"):
                esc_parts = ["\n\n## Escalation — When You Cannot Find the Answer"]
                esc_parts.append("When you cannot answer from documents, ALWAYS end your response with this escalation info:")
                if esc.get("team"): esc_parts.append(f"- **Team:** {esc['team']}")
                if esc.get("email"): esc_parts.append(f"- **Email:** {esc['email']}")
                if esc.get("phone"): esc_parts.append(f"- **Phone:** {esc['phone']}")
                if esc.get("url"): esc_parts.append(f"- **Raise Ticket:** {esc['url']}")
                if esc.get("chat"): esc_parts.append(f"- **Chat:** {esc['chat']}")
                if esc.get("hours"): esc_parts.append(f"- **Available:** {esc['hours']}")
                if esc.get("sla"): esc_parts.append(f"- **Response Time:** {esc['sla']}")
                if esc.get("priority"): esc_parts.append(f"- **Priority:** {esc['priority']}")
                base += "\n".join(esc_parts)

            # SOP mode
            if tenant.get("document_mode") == "sop":
                base += _SOP_MODE_INSTRUCTIONS
        except Exception:
            pass
    return base


_INSTRUCTIONS_TEMPLATE = """\
You are the **{agent_name}** — a self-learning knowledge agent ({agent_role}).

You are the user's {agent_role} — one that knows every folder, every document,
and exactly where that one policy is buried. You don't just search. You navigate,
read full documents, and extract the actual answer.

Your focus area: **{agent_focus}**

## CRITICAL BEHAVIOR RULES

1. **DOCUMENTS ONLY** — You ONLY answer from indexed documents. NEVER use your general knowledge. If it's not in a document, say "This information is not in our document library."
2. **YOUR NAME IS EXACTLY "{agent_name}"** — NEVER expand it into an acronym or make up what it stands for. Just use the name as given. Do NOT invent meanings like "Information Systems Trust Messenger" or similar.
3. **NEVER LIST AVAILABLE DOCUMENTS UNSOLICITED** — Do NOT list departments, document names, or library contents unless the user specifically asks "what documents do you have?" or similar. The system provides follow-up suggestions automatically.
4. **NEVER SUGGEST EXAMPLE QUESTIONS IN YOUR TEXT** — Do NOT write "(e.g., How do I reset...)" or "You can ask me about..." in your responses. The system generates clickable follow-up buttons automatically.
5. **BE PROACTIVE** — If only one document exists or context makes it obvious, just use it. Never ask "which document?" when there's only one option.
6. **USE CONTEXT** — Read conversation history. "Summarize it" means THAT document. Just do it.
7. **ACT, DON'T ASK** — When intent is clear, take action immediately. Only ask for clarification when genuinely ambiguous.
8. **READ FULL CONTENT** — Never answer from snippets or tool output alone. Always call get_page_content and read the actual pages before answering.
9. **CITE EVERYTHING** — Every answer must include the document ID, specific page number, and key details.
10. **NO HALLUCINATION** — If a document doesn't contain the answer, say so. Never make up procedures, policies, or facts.

## Your Tools (in priority order)

| Priority | Tool | When to use |
|----------|------|-------------|
| 1st | search_intents | **ALWAYS USE FIRST** — instant pre-built keyword → document mappings. |
| 2nd | search_wiki | **Cross-document knowledge** — pre-synthesized wiki pages combining info from multiple docs. Faster than vector search. |
| 3rd | vector_search_tool | **Semantic search** — finds pages by meaning, not just keywords. |
| 4th | search_documents | Keyword search fallback if vector search returns low scores. |
| 5th | list_all_documents | Show all documents. Use when all above return nothing. |
| 6th | get_document_summary | **For summaries/overviews** — pre-built summary covering the ENTIRE document. Instant, no page reading needed. |
| 7th | get_page_content | Read specific pages. For detailed questions after you know which pages. |
| 7th | get_screenshots | Get [IMG:page:index] tags for visual answers. |
| 8th | get_source_overview | Overview of document library: departments, categories, documents with summaries and caveats. |
| 9th | save_discovery | Save unexpected query → document mapping for future. |

## Workflow (Search → Read → Answer)

1. **Route**: search_intents first (instant). If match → skip to step 4.
2. **Wiki**: search_wiki for cross-document synthesized knowledge. If match → use wiki content + get_page_content for detail.
3. **Vector**: vector_search_tool finds the EXACT page by meaning. Much better than keywords.
3. **Read**: Choose the right tool based on the question type:
   - **Summaries/overviews** → use get_document_summary (instant, covers all pages)
   - **Specific questions** → use get_page_content with tight page ranges (e.g. '5-7')
   - **Visual/chart questions** → use read_page_visual for tables, diagrams, or when text seems incomplete
4. **Visuals**: ALWAYS call get_screenshots for the source document — this is MANDATORY for any procedural or step-by-step answer. Include the [IMG:page:index] tags in your answer.
5. **Answer**: Write complete answer with [REF:doc:page] citations AND [IMG:page:index] screenshot tags.
6. **Learn**: If match was unexpected, call save_discovery to remember it.
7. **Fallback**: If vector returns low scores, try search_documents then get_source_overview to show what's available.

## Answer Format

Every answer MUST include:
1. **Direct summary** — what the answer is, in 1-2 sentences
2. **Detailed content** — numbered steps, bullet points, or structured info
3. **Inline citations** — add [REF:doc_id:page] after EACH claim. Examples:
   - "The framework uses four AI agents [REF:Energy_BCP_Agentic_Framework:3] that work in parallel [REF:Energy_BCP_Agentic_Framework:5]"
   - "Diesel stockout prevention uses real-time monitoring [REF:Energy_BCP_Agentic_Framework:12]"
4. **Screenshots** — ALWAYS include [IMG:page:index] after relevant steps. Call get_screenshots tool first to get available images.

IMPORTANT: Add [REF:doc_id:page] inline within your text, NOT at the end. Every fact should have a citation right after it. Do NOT add a separate "Source Citation" section at the end — the inline refs are enough.

## Screenshot Tags

Use [IMG:page:index] from get_screenshots:
```
**Step 1: Go to Settings > Users**
Navigate to the backend and search for the employee.
[IMG:5:1]
```

## When Information Is NOT Found

Keep it SHORT. Do NOT list all available documents or dump your search path.

Good "not found" response:
"I don't have information about City Family password reset in our document library."

That's it. ONE sentence. Do NOT:
- Mention what documents ARE available
- Name any specific document (e.g. "the only document is Energy_BCP...")
- Show "Source Checked" or search paths
- Add "LOW CONFIDENCE" tags
- Suggest the user upload documents
- Explain what you searched

Just say you don't have it. The system automatically shows follow-up suggestions for the user.

## When to Save Discovery

Call save_discovery after:
```
# Found in unexpected document:
save_discovery("thai government", "20260321...", "1-3",
               "Thailand Digital Arrival Card - Immigration Bureau")

# Non-obvious search term worked:
save_discovery("cream import", "59fb27d7...", "1-5",
               "UHT Whipping Cream import packing list")

# User corrected you:
save_discovery("employee onboarding", "HR_HANDBOOK_001", "12-15",
               "User said onboarding is in HR handbook, not IT docs")
```

## Languages
Support {agent_langs}. Answer in the language the user asks in.
"""

_SOP_MODE_INSTRUCTIONS = """

## Document Standardization Mode (ACTIVE)
This tenant is in document standardization mode. Follow these rules:

### Answer Format
ALWAYS structure your answers as step-by-step procedures when the question is about HOW to do something:

**Step 1: [Action Title]**
[What to do — specific, actionable instruction]
Expected Result: [What the user should see after this step]

**Step 2: [Next Action]**
[Details...]
Expected Result: [...]

### Rules
- Lead with the ANSWER (McKinsey Pyramid — conclusion first, details after)
- Use numbered steps for any procedure (never paragraphs for how-to questions)
- Include "Expected Result" after steps where the user needs visual confirmation
- Include warnings BEFORE the step that could cause issues (not after)
- Reference specific page numbers: [REF:doc_id:page] for every claim
- If the document has screenshots, mention "See screenshot on page X" in the relevant step
- For troubleshooting questions, use decision tree format: "If X → do Y. If Z → do W."
- Keep each step to ONE action (not multiple actions in one step)
"""

# ── Create Agent ─────────────────────────────────────────────────────────────

_agents: dict[str, Agent] = {}
_agents_lock = __import__('threading').Lock()


def reload_agent(tenant_id: str):
    """Reset agent so next get_agent() rebuilds with fresh config."""
    with _agents_lock:
        _agents.pop(tenant_id, None)


def get_agent(tenant_id: str) -> Agent:
    """Get or create a tenant-scoped Agno agent. Each tenant gets its own agent with isolated tools + learning."""
    key = tenant_id
    if key in _agents:
        return _agents[key]
    with _agents_lock:
        if key in _agents:  # Double-check after acquiring lock
            return _agents[key]
        # Build DB URL with schema for tenant isolation
        db_url = DATABASE_URL
        sep = "&" if "?" in db_url else "?"
        db_url = f"{db_url}{sep}options=-c%20search_path%3D{tenant_id}%2Cpublic"
        agent_db = PostgresDb(db_url=db_url)

        cfg = _get_agent_config(tenant_id)
        tenant_tools = make_tools(tenant_id)

        _agents[key] = Agent(
            name=cfg.get("name", "Document Agent"),
            model=OpenAIChat(
                id=VISION_MODEL,
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            instructions=_build_instructions(tenant_id),
            tools=tenant_tools,
            # Storage — all in PostgreSQL
            db=agent_db,
            # Memory
            add_history_to_context=True,
            num_history_runs=5,
            read_chat_history=True,
            # Learning — self-improving, stored in PostgreSQL
            learning=LearningMachine(
                db=agent_db,
                model=OpenAIChat(
                    id=VISION_MODEL,
                    api_key=OPENROUTER_API_KEY,
                    base_url=OPENROUTER_BASE_URL,
                ),
                learned_knowledge=LearnedKnowledgeConfig(
                    mode=LearningMode.AGENTIC,
                ),
                decision_log=True,
            ),
            add_learnings_to_context=True,
            enable_agentic_memory=True,
            add_datetime_to_context=True,
            markdown=True,
        )
    return _agents[key]


# ── Ask function (backward compatible with chat route) ───────────────────────

def ask(
    question: str,
    department_filter: Optional[str] = None,
    sop_id_filter: Optional[str] = None,
    chat_history: Optional[list] = None,
    on_status: Optional[callable] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """
    Ask the document agent a question using Agno.

    Returns same format as before:
    {
        "answer": str,
        "sources": [...],
        "images": [...],
        "image_map": {...},
        "model_used": str,
    }
    """
    import re
    import json
    from pathlib import Path
    from backend.core import database as db
    from backend.core.database import get_tenant_screenshot_dir

    def _status(step: str, msg: str, detail: str = ""):
        if on_status:
            on_status(step, msg, detail)

    _status("thinking", "Agent is analyzing your question...", "")

    agent = get_agent(tenant_id)

    # Build context with chat history + optional filters
    context_parts = []

    # Add recent chat history as context
    if chat_history and len(chat_history) > 0:
        context_parts.append("## Recent conversation context:")
        for msg in chat_history[-6:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:300]
            context_parts.append(f"{role}: {content}")
        context_parts.append("")

    if sop_id_filter:
        context_parts.append(f"[Focus on document: {sop_id_filter}]")
    elif department_filter:
        context_parts.append(f"[Focus on department: {department_filter}]")

    context_parts.append(question)
    context = "\n".join(context_parts)

    _status("searching", "Searching knowledge base...", "")

    # Tool name → friendly description
    tool_labels = {
        "search_intents": ("Checking intent routes", "intent"),
        "vector_search_tool": ("Semantic search", "vector"),
        "search_documents": ("Keyword search", "search"),
        "list_all_documents": ("Listing all documents", "list"),
        "get_document_summary": ("Document summary", "summary"),
        "get_page_content": ("Reading page content", "pages"),
        "get_screenshots": ("Finding screenshots", "images"),
        "get_source_overview": ("Building source overview", "overview"),
        "save_discovery": ("Saving discovery", "save"),
        "save_negative": ("Saving negative knowledge", "save_neg"),
    }

    # Run the agent
    try:
        response = agent.run(input=context)
        answer = response.content or "I couldn't generate a response."

        # Extract tool calls from messages and report them
        if response.messages:
            for msg in response.messages:
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function", {})
                            name = fn.get("name", "")
                            args = fn.get("arguments", "{}")
                        else:
                            name = getattr(getattr(tc, "function", None), "name", "")
                            args = getattr(getattr(tc, "function", None), "arguments", "{}")

                        label, icon = tool_labels.get(name, (name, "tool"))
                        # Extract first arg value for detail
                        detail = ""
                        try:
                            parsed = json.loads(args) if isinstance(args, str) else args
                            detail = str(list(parsed.values())[0])[:60] if parsed else ""
                        except Exception:
                            pass
                        _status(icon, label, detail)

    except Exception as e:
        answer = f"Error: {e}"

    _status("complete", "Generating answer...", "")

    # Extract sources — only if document was actually USED to answer (not just mentioned)
    not_found_phrases = ["not found", "couldn't find", "don't have", "no match", "not in our",
                         "not available", "not documented", "no matching", "no information"]
    is_not_found = any(phrase in answer.lower() for phrase in not_found_phrases)

    all_docs = db.list_sops(tenant_id=tenant_id)
    sources = []
    seen = set()
    # Normalize O/0 for matching — LLM often writes letter O instead of digit 0
    _norm_o0 = lambda s: s.lower().replace('o', '0')
    norm_answer = _norm_o0(answer)
    if not is_not_found:
        for doc in all_docs:
            sid = doc["sop_id"]
            if sid not in seen and (sid in answer or _norm_o0(sid) in norm_answer):
                seen.add(sid)
                # Search for page refs using both original and O/0-normalized sid
                page_match = re.search(rf'{re.escape(sid)}.*?(?:page|p\.?|pages)\s*[:\s]*(\d[\d\-,\s]*)', answer, re.IGNORECASE)
                if not page_match:
                    # Try finding the LLM-written variant (e.g., OO1 instead of 001) and search around it
                    norm_sid = _norm_o0(sid)
                    for variant_match in re.finditer(re.escape(norm_sid), norm_answer):
                        pos = variant_match.start()
                        snippet = answer[pos:pos+len(sid)+60]
                        page_match = re.search(r'(?:page|p\.?|pages)\s*[:\s]*(\d[\d\-,\s]*)', snippet, re.IGNORECASE)
                        if page_match:
                            break
                pages = page_match.group(1).strip() if page_match else ""
                sources.append({
                    "sop_id": sid,
                    "doc_name": doc.get("title", ""),
                    "pages": pages,
                    "department": doc.get("department", ""),
                    "page_count": doc.get("page_count", 0),
                })

    # Build image map from [IMG:page:index] tags in the answer
    img_tags = re.findall(r'\[IMG:(\d+):(\d+)\]', answer)
    image_map = {}

    # Find which SOP the images belong to
    primary_sop = sources[0]["sop_id"] if sources else None
    if primary_sop:
        screenshot_base = get_tenant_screenshot_dir(tenant_id)
        screenshots = db.get_screenshots(primary_sop, tenant_id=tenant_id)
        for page_str, imgs in screenshots.items():
            for img in imgs:
                key = f"{page_str}_{img['index']}"
                filename = img.get("path", "")
                full_path = screenshot_base / primary_sop / filename
                url = f"/api/t/{tenant_id}/images/{primary_sop}/{filename}"
                if full_path.exists():
                    image_map[key] = {
                        "page": int(page_str),
                        "index": img["index"],
                        "path": str(full_path),
                        "sop_id": primary_sop,
                        "url": url,
                        "width": img.get("width", 0),
                        "height": img.get("height", 0),
                    }

        # Auto-inject [IMG:page:index] tags for cited pages if agent didn't include them
        if not img_tags and image_map:
            cited_pages = set()
            for ref_match in re.finditer(r'\[REF:[^\]:]+:(\d+)', answer):
                cited_pages.add(int(ref_match.group(1)))
            if cited_pages:
                injected = []
                for key, img_info in image_map.items():
                    if img_info["page"] in cited_pages and len(injected) < 3:
                        injected.append(f"[IMG:{img_info['page']}:{img_info['index']}]")
                if injected:
                    answer += "\n\n" + "\n".join(injected)

    # Track usage
    if tenant_id:
        try:
            db.log_usage(tenant_id, "chat", VISION_MODEL, input_tokens=len(context.split()), output_tokens=len(answer.split()), cost_usd=0.0005)
            db.log_audit(tenant_id, "chat_query", resource_type="chat", details=question[:100])
        except Exception:
            pass

    return {
        "answer": answer,
        "sources": sources,
        "images": list(image_map.values()),
        "image_map": image_map,
        "model_used": VISION_MODEL,
    }


# ── Follow-up Suggestions ────────────────────────────────────────────────────

def generate_suggestions(question: str, answer: str, sources: list) -> list:
    """Generate 2-3 follow-up suggestions based on the Q&A context. Fast + cheap."""
    import json
    from backend.core.config import get_openrouter_client, ROUTER_MODEL

    client = get_openrouter_client()

    source_names = ", ".join(
        s.get("doc_name", s.get("sop_id", "")) for s in sources[:3]
    ) if sources else "none"

    not_found = any(phrase in answer.lower() for phrase in [
        "not in our document", "no match", "no documents found", "couldn't find",
        "not found", "no matching", "not available",
    ])

    if not_found:
        context = f"""The user asked: "{question}"
But no matching documents were found in the library.

Generate 3 helpful follow-up suggestions:
- 1 rephrased version of their question (different keywords)
- 1 exploratory question ("What documents do we have about X?")
- 1 broad discovery question ("Show me all available documents")"""
    else:
        context = f"""User asked: "{question}"
Answer referenced: {source_names}
Answer preview: {answer[:400]}

Generate 3 follow-up questions the user would naturally ask next:
- Related to the same document (deeper detail, next steps)
- Related workflow or process
- Something complementary (if about setup → ask about troubleshooting)"""

    prompt = f"""{context}

Rules:
- Each question under 60 characters
- Specific and actionable, not generic
- Written as natural user questions
- Return ONLY a JSON array of strings"""

    try:
        from backend.core.config import call_openrouter
        raw = call_openrouter(prompt, model=ROUTER_MODEL, max_tokens=200, temperature=0.7)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        suggestions = json.loads(raw.strip())
        if isinstance(suggestions, list):
            return [s for s in suggestions if isinstance(s, str)][:3]
    except Exception:
        pass
    return []



