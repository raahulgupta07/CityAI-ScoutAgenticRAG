/**
 * Chat Widget — Single source of truth for admin + public chat.
 *
 * Usage:
 *   ChatWidget.init({
 *     mode: 'admin' | 'public',
 *     container: document.getElementById('chat-root'),
 *     chatApi: '/api/t/TENANT/chat',
 *     tenantId: 'my-tenant',
 *     adminApi: '/api/t/TENANT/admin',    // admin mode only
 *     agentName: 'ITSM Agent',
 *     allDocs: [],                         // admin mode: doc list for context panel + DOCX download
 *     feedbackApi: '/api/chat/feedback',   // defaults to /api/chat/feedback
 *   });
 */
(function() {
'use strict';

/* ── CSS (injected once) ──────────────────────────────────────────────────── */
const CSS = `
/* Chat Widget Styles */
.cw-root { height: 100%; display: flex; flex-direction: column; width: 100%; transition: width 0.3s ease; font-family: 'Space Grotesk', sans-serif; background: #feffd6; position: relative; z-index: 2; }

/* Header */
.cw-header { padding: 12px 24px; display: flex; align-items: center; gap: 12px; border-bottom: 3px solid #383832; background: #383832; width: 100%; flex-shrink: 0; }
.cw-header-icon { width: 36px; height: 36px; background: #007518; display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; }
.cw-header-icon img { background: white; }
.cw-header-icon .material-symbols-outlined { color: white; font-size: 20px; }
.cw-header-name { font-weight: 900; font-size: 16px; color: #feffd6; text-transform: uppercase; letter-spacing: -0.02em; }
.cw-header-badge { font-size: 9px; background: #007518; color: white; padding: 2px 8px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px; }
.cw-header-actions { margin-left: auto; display: flex; gap: 8px; }
.cw-header-actions button { padding: 6px 12px; background: transparent; border: 1px solid #feffd6; color: #feffd6; font-size: 10px; font-weight: 900; text-transform: uppercase; cursor: pointer; font-family: 'Space Grotesk', sans-serif; display: flex; align-items: center; gap: 4px; }
.cw-header-actions button:hover { background: rgba(254,255,214,0.1); }

/* Messages */
.cw-messages { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 24px; background: #feffd6; }
.cw-messages-inner { max-width: 900px; margin: 0 auto; width: 100%; overflow: hidden; }
.cw-welcome { text-align: center; padding: 60px 20px 20px; }
.cw-welcome h2 { font-size: 22px; font-weight: 900; margin-bottom: 8px; color: #383832; text-transform: uppercase; }
.cw-welcome p { color: #65655e; font-size: 14px; margin-bottom: 24px; }
.cw-starter-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 100%; padding: 0 16px; margin: 0 auto; text-align: left; box-sizing: border-box; }
.cw-starter-card { background: white; border: 2px solid #383832; padding: 12px; cursor: pointer; transition: all 0.15s; box-shadow: 2px 2px 0 #383832; overflow: hidden; min-width: 0; }
.cw-starter-card:hover { background: #007518; color: white; border-color: #383832; }
.cw-starter-card:hover .cw-starter-q { color: white; }
.cw-starter-card:hover .cw-starter-src { color: rgba(255,255,255,0.7); }
.cw-starter-card:active { transform: translate(2px,2px); box-shadow: 1px 1px 0 #383832; }
.cw-starter-q { font-size: 12px; font-weight: 700; color: #383832; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.cw-starter-src { font-size: 8px; font-weight: 900; color: #65655e; text-transform: uppercase; margin-top: 6px; letter-spacing: 0.05em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cw-starter-icon { font-size: 14px; color: #00fc40; margin-bottom: 4px; }

/* Message row */
.cw-msg { display: flex; gap: 12px; margin-bottom: 20px; max-width: 90%; }
.cw-msg-user { margin-left: auto; flex-direction: row-reverse; max-width: 75%; }
.cw-msg-avatar { width: 32px; height: 32px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; margin-top: 4px; background: #ebe8dd; }
.cw-msg-avatar .material-symbols-outlined { font-size: 16px; }
.cw-msg-body { flex: 1; min-width: 0; overflow: hidden; }
.cw-msg-time { font-size: 10px; color: #65655e; margin-top: 4px; display: block; font-weight: 700; }
.cw-msg-user .cw-msg-time { text-align: right; }

/* User bubble */
.cw-msg-user .cw-bubble { background: #00fc40; color: #383832; padding: 14px 20px; font-size: 14px; line-height: 1.6; }

/* Bot bubble */
.cw-msg-bot .cw-bubble { background: #f6f4e9; border: none; padding: 16px 20px; font-size: 14px; line-height: 1.5; color: #383832; overflow-wrap: break-word; word-break: break-word; min-width: 0; }
.cw-msg-bot .cw-bubble h2, .cw-msg-bot .cw-bubble h3 { margin: 12px 0 4px; font-weight: 900; text-transform: uppercase; }
.cw-msg-bot .cw-bubble h2 { font-size: 15px; }
.cw-msg-bot .cw-bubble h3 { font-size: 13px; }
.cw-msg-bot .cw-bubble strong { font-weight: 900; }
.cw-msg-bot .cw-bubble ul { padding-left: 18px; margin: 4px 0; }
.cw-msg-bot .cw-bubble li { margin: 2px 0; }
.cw-msg-bot .cw-bubble code { background: #ebe8dd; padding: 1px 5px; font-size: 12px; }
.cw-msg-bot .cw-bubble table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; }
.cw-msg-bot .cw-bubble th { background: #383832; color: #feffd6; padding: 8px; text-align: left; border: 2px solid #383832; font-weight: 900; text-transform: uppercase; font-size: 10px; }
.cw-msg-bot .cw-bubble td { padding: 8px; border: 1px solid rgba(56,56,50,0.15); }

/* Thinking */
.cw-thinking-box { background: #f6f4e9; border: 2px solid #383832; padding: 14px 18px; margin-bottom: 12px; max-width: 85%; }
.cw-thinking-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cw-thinking-badge { background: #ebe8dd; color: #006f7c; padding: 2px 8px; font-size: 10px; font-weight: 900; text-transform: uppercase; letter-spacing: -0.02em; }
.cw-thinking-dots { display: flex; gap: 4px; }
.cw-thinking-dots span { width: 8px; height: 8px; border-radius: 50% !important; }
.cw-thinking-dots span:nth-child(1) { background: #007518; animation: cwBounce 0.6s ease-in-out infinite; }
.cw-thinking-dots span:nth-child(2) { background: #ff9d00; animation: cwBounce 0.6s ease-in-out infinite 0.2s; }
.cw-thinking-dots span:nth-child(3) { background: #be2d06; animation: cwBounce 0.6s ease-in-out infinite 0.4s; }
@keyframes cwBounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
.cw-think-steps { border-top: 1px solid rgba(56,56,50,0.15); padding-top: 8px; margin-top: 4px; }
.cw-think-step { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.cw-step-text { font-size: 11px; font-family: monospace; color: #383832; }
.cw-step-detail { font-size: 10px; color: #65655e; margin-left: 4px; }

/* Citations */
.cw-cite-ref { cursor: pointer; color: #007518; font-weight: 900; font-size: 10px; padding: 1px 6px; background: #ebe8dd; border: 1px solid #383832; vertical-align: super; margin: 0 2px; transition: all 0.1s; }
.cw-cite-ref:hover { background: #383832; color: #feffd6; }

/* Screenshots */
.cw-screenshot { margin: 12px 0; overflow: hidden; border: 2px solid #383832; max-width: 400px; }
.cw-screenshot img { max-width: 100%; width: auto; height: auto; display: block; cursor: pointer; max-height: 300px; object-fit: contain; background: #f6f4e9; }
.cw-screenshot-label { font-size: 9px; padding: 4px 12px; background: #383832; color: #feffd6; display: flex; align-items: center; gap: 6px; font-weight: 900; text-transform: uppercase; }

/* Sources */
.cw-sources-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 14px; padding-top: 14px; border-top: 2px solid #383832; }
.cw-sources-row .cw-label { font-size: 9px; color: #65655e; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 900; }
.cw-source-badge { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 900; color: #383832; background: white; padding: 5px 12px; cursor: pointer; border: 2px solid #383832; box-shadow: 2px 2px 0 #383832; text-transform: uppercase; }
.cw-source-badge:hover { background: #f6f4e9; }
.cw-source-badge .material-symbols-outlined { font-size: 14px; }
.cw-model-badge { font-size: 10px; color: #65655e; background: #ebe8dd; padding: 4px 8px; font-weight: 900; text-transform: uppercase; }

/* Feedback */
.cw-feedback-row { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; }
.cw-fb-label { font-size: 9px; color: #65655e; font-weight: 900; text-transform: uppercase; }
.cw-fb-btn { width: 28px; height: 28px; border: 1px solid #383832; background: transparent; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; color: #65655e; }
.cw-fb-btn:hover { background: #ebe8dd; }
.cw-fb-btn.cw-active-up { color: #007518; background: #feffd6; border-color: #007518; }
.cw-fb-btn.cw-active-down { color: #be2d06; background: #feffd6; border-color: #be2d06; }
.cw-copy-btn { font-size: 10px; color: #65655e; background: none; border: none; cursor: pointer; display: flex; align-items: center; gap: 4px; font-weight: 900; text-transform: uppercase; font-family: 'Space Grotesk', sans-serif; }
.cw-copy-btn:hover { color: #383832; }

/* Feedback popup */
.cw-fb-popup { margin-top: 8px; padding: 12px; background: white; border: 2px solid #383832; box-shadow: 4px 4px 0 #383832; }
.cw-fb-popup-title { font-size: 10px; font-weight: 900; text-transform: uppercase; color: #65655e; margin-bottom: 8px; }
.cw-fb-reasons { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.cw-fb-reason { font-size: 10px; padding: 4px 10px; border: 2px solid #383832; background: #f6f4e9; color: #383832; cursor: pointer; font-weight: 700; font-family: 'Space Grotesk', sans-serif; text-transform: uppercase; }
.cw-fb-reason:hover { background: #ebe8dd; }
.cw-fb-reason.cw-selected { background: #383832; color: #feffd6; }
.cw-fb-popup textarea { width: 100%; padding: 8px; border: 2px solid #383832; font-size: 12px; font-family: 'Space Grotesk', sans-serif; resize: none; outline: none; margin-bottom: 8px; background: white; color: #383832; }
.cw-fb-popup textarea:focus { border-color: #007518; }
.cw-fb-submit { padding: 6px 16px; background: #00fc40; border: 2px solid #383832; color: #383832; font-size: 10px; font-weight: 900; cursor: pointer; font-family: 'Space Grotesk', sans-serif; text-transform: uppercase; box-shadow: 2px 2px 0 #383832; }
.cw-fb-submit:hover { filter: brightness(1.05); }

/* Escalation card */
.cw-escalation { margin-top: 12px; padding: 14px 18px; background: white; border: 2px solid #383832; box-shadow: 3px 3px 0 #ff9d00; }
.cw-escalation-title { font-size: 10px; font-weight: 900; text-transform: uppercase; color: #ff9d00; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
.cw-escalation-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.cw-escalation-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #383832; font-weight: 700; }
.cw-escalation-item a { color: #007518; text-decoration: none; font-weight: 900; }
.cw-escalation-item a:hover { text-decoration: underline; }
.cw-escalation-meta { font-size: 10px; color: #65655e; margin-top: 8px; display: flex; flex-wrap: wrap; gap: 12px; }

/* Referenced page thumbnails */
.cw-ref-pages { margin-top: 12px; padding-top: 12px; border-top: 2px solid #383832; }
.cw-ref-pages-title { font-size: 9px; font-weight: 900; text-transform: uppercase; color: #65655e; letter-spacing: 0.5px; margin-bottom: 8px; }
.cw-ref-pages-grid { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 4px; }
.cw-ref-thumb { flex-shrink: 0; width: 140px; border: 2px solid #383832; box-shadow: 2px 2px 0 #383832; background: white; cursor: pointer; overflow: hidden; }
.cw-ref-thumb:hover { box-shadow: 3px 3px 0 #007518; border-color: #007518; }
.cw-ref-thumb img { width: 100%; height: 150px; object-fit: cover; object-position: top; display: block; }
.cw-ref-thumb-label { padding: 4px 8px; background: #383832; color: #feffd6; font-size: 9px; font-weight: 900; text-transform: uppercase; display: flex; justify-content: space-between; align-items: center; }
.cw-ref-thumb-label .cw-view { color: #00fc40; }

/* Scroll to bottom button */
.cw-scroll-btn { display: none; position: absolute; bottom: 80px; right: 24px; width: 36px; height: 36px; background: #383832; border: 2px solid #383832; color: #feffd6; cursor: pointer; align-items: center; justify-content: center; box-shadow: 2px 2px 0 #383832; z-index: 10; }
.cw-scroll-btn:hover { background: #007518; }

/* Suggestions */
.cw-suggestions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; margin-bottom: 24px; }
.cw-suggestions button { font-size: 12px; color: #383832; background: white; border: 2px solid #383832; padding: 10px 16px; cursor: pointer; font-weight: 700; text-transform: uppercase; font-family: 'Space Grotesk', sans-serif; box-shadow: 2px 2px 0 #383832; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cw-suggestions button:hover { background: #007518; color: white; border-color: #383832; }

/* Input */
.cw-input-area { padding: 16px 24px; background: #f6f4e9; border-top: 3px solid #383832; width: 100%; flex-shrink: 0; }
.cw-input-row { display: flex; gap: 8px; align-items: flex-end; max-width: 900px; margin: 0 auto; }
.cw-input-row textarea { flex: 1; padding: 12px 16px; border: 2px solid #383832; font-size: 14px; font-family: 'Space Grotesk', sans-serif; resize: none; outline: none; min-height: 24px; max-height: 120px; line-height: 1.4; background: white; color: #383832; font-weight: 700; border-radius: 0 !important; }
.cw-input-row textarea:focus { border-color: #007518; }
.cw-input-row button { width: 44px; height: 44px; background: #00fc40; border: 2px solid #383832; color: #383832; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 3px 3px 0px 0px #383832; }
.cw-input-row button:active { transform: translate(2px,2px); box-shadow: 1px 1px 0px 0px #383832; }
.cw-input-row button:disabled { opacity: 0.4; cursor: not-allowed; }

/* Footer */
.cw-footer { text-align: center; padding: 8px; font-size: 10px; color: #65655e; font-weight: 700; text-transform: uppercase; border-top: 2px solid #383832; width: 100%; flex-shrink: 0; }

/* Session badge */
.cw-session-badge { display: flex; justify-content: center; margin-bottom: 16px; }
.cw-session-badge span { background: #ebe8dd; font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 900; padding: 4px 12px; color: #65655e; }

/* PDF Panel */
.cw-pdf-overlay { display: none; width: 50%; background: #feffd6; border-left: 3px solid #383832; flex-direction: column; overflow: hidden; }
.cw-pdf-overlay.cw-open { display: flex; }
@keyframes cwSlideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
.cw-pdf-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: #383832; border-bottom: 2px solid #383832; }
.cw-pdf-title { font-size: 13px; font-weight: 900; color: #feffd6; display: flex; align-items: center; gap: 6px; text-transform: uppercase; }
.cw-pdf-title .material-symbols-outlined { font-size: 18px; color: #00fc40; }
.cw-pdf-close { width: 32px; height: 32px; border: 1px solid #feffd6; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #feffd6; }
.cw-pdf-close:hover { background: rgba(254,255,214,0.1); }
.cw-pdf-dl { padding: 6px 12px; background: #00fc40; border: 2px solid #feffd6; color: #383832; font-size: 10px; font-weight: 900; cursor: pointer; font-family: 'Space Grotesk', sans-serif; text-transform: uppercase; display: none; }
.cw-pdf-pages { flex: 1; overflow-y: auto; padding: 16px; }
.cw-pdf-page { background: white; overflow: hidden; margin-bottom: 12px; border: 2px solid #383832; box-shadow: 3px 3px 0px 0px #383832; }
.cw-pdf-page-label { font-size: 10px; font-weight: 900; color: #feffd6; padding: 6px 12px; background: #383832; text-transform: uppercase; }
.cw-pdf-page img { width: 100%; display: block; }

@keyframes cwSpin { to { transform: rotate(360deg); } }
.cw-loading { animation: cwSpin 1s linear infinite; }

/* Mobile responsive */
@media (max-width: 768px) {
    .cw-header { padding: 10px 16px; gap: 8px; }
    .cw-header-name { font-size: 14px; }
    .cw-header-badge { display: none; }
    .cw-header-actions button { padding: 4px 8px; font-size: 9px; }
    .cw-messages { padding: 16px 12px; }
    .cw-msg { max-width: 95%; }
    .cw-msg-user { max-width: 85%; }
    .cw-msg-avatar { width: 28px; height: 28px; }
    .cw-msg-avatar .material-symbols-outlined { font-size: 14px; }
    .cw-msg-user .cw-bubble, .cw-msg-bot .cw-bubble { padding: 10px 14px; font-size: 13px; }
    .cw-thinking-box { max-width: 95%; padding: 10px 14px; }
    .cw-input-area { padding: 12px 12px; }
    .cw-input-row textarea { padding: 10px 12px; font-size: 13px; }
    .cw-input-row button { width: 40px; height: 40px; }
    .cw-welcome { padding: 30px 12px 12px; }
    .cw-welcome h2 { font-size: 18px; }
    .cw-starter-grid { grid-template-columns: 1fr; gap: 8px; }
    .cw-suggestions button { font-size: 11px; padding: 8px 12px; max-width: 260px; }
    .cw-ref-thumb { width: 110px; }
    .cw-ref-thumb img { height: 120px; }
    .cw-source-badge { font-size: 10px; padding: 4px 8px; }
    .cw-pdf-overlay { width: 100% !important; position: absolute !important; top: 0; right: 0; bottom: 0; z-index: 10; }
    .cw-root { width: 100% !important; }
    .cw-footer { font-size: 9px; }
}
`;

let styleInjected = false;
function injectCSS() {
    if (styleInjected) return;
    const el = document.createElement('style');
    el.textContent = CSS;
    document.head.appendChild(el);
    styleInjected = true;
}

/* ── Widget State ─────────────────────────────────────────────────────────── */
const STATE = {
    logoUrl: '',
    mode: 'public',
    chatApi: '',
    feedbackApi: '',
    tenantId: '',
    adminApi: '',
    agentName: 'Document Agent',
    allDocs: [],
    container: null,
    messagesEl: null,
    inputEl: null,
    sendBtn: null,
    pdfPanel: null,
    loading: false,
    chatStarted: false,
    currentSopId: '',
    lastSources: [],
    history: [],  // last N Q&A pairs for multi-turn context
    escalation: null,  // {team, email, phone, url, chat, hours, sla, priority, message, always}
};

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function getTime() {
    return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
}

function esc(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function resolveSopId(rawId) {
    const clean = rawId.replace(/\.pdf$/i, '').trim();
    // Build pool: sources first, then allDocs
    const pool = STATE.lastSources.length
        ? STATE.lastSources
        : STATE.allDocs.map(d => ({ sop_id: d.sop_id, doc_name: d.title, page_count: d.page_count }));
    // 1. Exact match
    for (const s of pool) { if (s.sop_id === rawId || s.sop_id === clean) return s; }
    // 2. Case-insensitive
    const lower = clean.toLowerCase();
    for (const s of pool) { if (s.sop_id.toLowerCase() === lower) return s; }
    // 3. Normalize O/0 ambiguity (LLM often confuses letter O and digit 0)
    const norm = str => str.toLowerCase().replace(/[o0]/g, '0');
    const normClean = norm(clean);
    for (const s of pool) { if (norm(s.sop_id) === normClean) return s; }
    // 4. Fuzzy: substring match
    for (const s of pool) { const sl = s.sop_id.toLowerCase(); if (sl.includes(lower) || lower.includes(sl)) return s; }
    // 5. Single source fallback
    if (pool.length === 1) return pool[0];
    return null;
}

function md(text) {
    return text
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/^###\s+(.+)$/gm,'<h3 style="font-size:14px;font-weight:900;text-transform:uppercase;margin:12px 0 4px;color:#383832">$1</h3>')
        .replace(/^##\s+(.+)$/gm,'<h2 style="font-size:16px;font-weight:900;text-transform:uppercase;margin:16px 0 6px;color:#383832">$1</h2>')
        .replace(/\*\*(.+?)\*\*/g,'<strong style="font-weight:900">$1</strong>')
        .replace(/\*(.+?)\*/g,'<em>$1</em>')
        .replace(/`(.+?)`/g,'<code style="background:#ebe8dd;padding:1px 5px;font-size:12px">$1</code>')
        .replace(/^\*\s+(.+)$/gm,'<li>$1</li>')
        .replace(/^\-\s+(.+)$/gm,'<li>$1</li>')
        .replace(/((?:<li>.*<\/li>\s*)+)/g,'<ul style="padding-left:16px;margin:6px 0">$1</ul>')
        .replace(/\[REF:([^\]:]+):(\d+[^\]]*)\]/g, function(m, docId, pg) {
            STATE.currentSopId = docId;
            return '<sup class="cw-cite-ref" onclick="ChatWidget.openPdf(\''+docId+'\','+parseInt(pg)+')">[p'+pg+']</sup>';
        })
        .replace(/\[IMG:(\d+):(\d+)\]/g, function(m, pg, idx) {
            const sid = STATE.currentSopId || '';
            if (!sid) return '<div class="cw-screenshot"><div class="cw-screenshot-label">Screenshot page '+pg+'</div></div>';
            return '<div class="cw-screenshot">'
                + '<img src="/api/t/'+STATE.tenantId+'/images/'+sid+'/p'+pg+'_img'+idx+'.png" onerror="this.parentElement.innerHTML=\'<div class=cw-screenshot-label>Screenshot not available (p'+pg+':'+idx+')</div>\'">'
                + '<div class="cw-screenshot-label"><span class="material-symbols-outlined" style="font-size:12px">image</span> PAGE '+pg+' · SCREENSHOT '+idx
                + ' <span style="cursor:pointer;color:#00fc40;margin-left:auto" onclick="ChatWidget.openPdf(\''+sid+'\','+pg+')">VIEW PAGE &rarr;</span></div>'
                + '</div>';
        })
        .replace(/\n\n/g,'<div style="margin:6px 0"></div>').replace(/\n/g,'<br>')
        .replace(/<script[^>]*>.*?<\/script>/gi,'');
}

/* ── Build HTML ───────────────────────────────────────────────────────────── */
function buildHTML() {
    const name = STATE.agentName;
    const logoSrc = STATE.logoUrl || '/static/logo.svg';
    const logoHtml = `<img src="${esc(logoSrc)}" alt="Logo" style="width:36px;height:36px;object-fit:contain;display:block">`;
    return `
<div class="cw-root" id="cw-root">
    <div class="cw-header">
        <div class="cw-header-icon" id="cw-header-logo">${logoHtml}</div>
        <span class="cw-header-name" id="cw-agent-name">${esc(name)}</span>
        <span class="cw-header-badge">RAG AGENT</span>
        <div class="cw-header-actions">
            <button onclick="ChatWidget.exportChat()"><span class="material-symbols-outlined" style="font-size:14px">download</span> EXPORT</button>
            <button onclick="ChatWidget.exportPdf()"><span class="material-symbols-outlined" style="font-size:14px">picture_as_pdf</span> PDF</button>
            <button onclick="ChatWidget.clearChat()"><span class="material-symbols-outlined" style="font-size:14px">delete</span> NEW SESSION</button>
        </div>
    </div>
    <div class="cw-messages" id="cw-messages">
        <div class="cw-messages-inner" id="cw-messages-inner">
            <div class="cw-welcome">
                <h2 id="cw-welcome-title">${esc(name)}</h2>
                <p>Ask about any document, procedure, or policy. I'll find the answer with citations.</p>
                <div id="cw-starter-cards"></div>
            </div>
        </div>
    </div>
    <button class="cw-scroll-btn" id="cw-scroll-btn" onclick="document.getElementById('cw-messages').scrollTop=document.getElementById('cw-messages').scrollHeight"><span class="material-symbols-outlined" style="font-size:20px">keyboard_arrow_down</span></button>
    <div class="cw-input-area">
        <div class="cw-input-row">
            <textarea id="cw-input" rows="1" placeholder="Ask a question..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();ChatWidget.send();}"></textarea>
            <button onclick="ChatWidget.send()" id="cw-send-btn"><span class="material-symbols-outlined">send</span></button>
        </div>
    </div>
    <div class="cw-footer" id="cw-footer">${esc(name)} can make mistakes. Verify critical information.</div>
</div>
<div class="cw-pdf-overlay" id="cw-pdf-panel">
    <div class="cw-pdf-header">
        <span class="cw-pdf-title"><span class="material-symbols-outlined">description</span><span id="cw-pdf-title-text">Document</span></span>
        <div style="display:flex;gap:8px;align-items:center">
            <button class="cw-pdf-dl" id="cw-pdf-dl" title="Download DOCX">Download DOCX</button>
            <button class="cw-pdf-close" onclick="ChatWidget.closePdf()"><span class="material-symbols-outlined" style="font-size:20px">close</span></button>
        </div>
    </div>
    <div class="cw-pdf-pages" id="cw-pdf-content"></div>
</div>`;
}

/* ── Persistence ──────────────────────────────────────────────────────────── */
function _storageKey() { return 'cw_chat_' + STATE.tenantId; }
function saveMessages() {
    try {
        const inner = document.getElementById('cw-messages-inner');
        if (inner && STATE.chatStarted) {
            localStorage.setItem(_storageKey(), JSON.stringify({
                html: inner.innerHTML,
                history: STATE.history,
                ts: Date.now(),
            }));
        }
    } catch {}
}
function restoreMessages() {
    try {
        const saved = localStorage.getItem(_storageKey());
        if (!saved) return false;
        const data = JSON.parse(saved);
        // Expire after 1 hour
        if (Date.now() - data.ts > 3600000) { localStorage.removeItem(_storageKey()); return false; }
        const inner = document.getElementById('cw-messages-inner');
        if (inner && data.html) {
            inner.innerHTML = data.html;
            STATE.history = data.history || [];
            STATE.chatStarted = true;
            STATE.messagesEl.scrollTop = STATE.messagesEl.scrollHeight;
            return true;
        }
    } catch {}
    return false;
}

/* ── Core Functions ───────────────────────────────────────────────────────── */

function clearChat() {
    STATE.chatStarted = false;
    STATE.lastSources = [];
    STATE.currentSopId = '';
    STATE.history = [];
    try { localStorage.removeItem(_storageKey()); } catch {}
    const inner = document.getElementById('cw-messages-inner');
    if (inner) {
        const name = STATE.agentName;
        inner.innerHTML = `<div class="cw-welcome"><h2 id="cw-welcome-title">${esc(name)}</h2><p>Ask about any document, procedure, or policy. I'll find the answer with citations.</p><div id="cw-starter-cards"></div></div>`;
        // Reload starter cards
        if (STATE.tenantId) {
            fetch('/api/t/' + STATE.tenantId + '/admin/starter-questions?limit=4').then(r => r.ok ? r.json() : []).then(questions => {
                const sc = document.getElementById('cw-starter-cards');
                if (!sc || !questions.length) return;
                const icons = ['chat_bubble', 'help', 'search', 'description'];
                sc.className = 'cw-starter-grid';
                sc.innerHTML = questions.slice(0, 4).map((q, i) => {
                    const safeQ = q.question.replace(/'/g, '&#39;').replace(/"/g, '&quot;');
                    return '<div class="cw-starter-card" onclick="ChatWidget.askStarter(\'' + safeQ.replace(/\\/g,'\\\\') + '\')">'
                        + '<div class="cw-starter-icon"><span class="material-symbols-outlined">' + icons[i % 4] + '</span></div>'
                        + '<div class="cw-starter-q">' + esc(q.question) + '</div>'
                        + '<div class="cw-starter-src">' + esc(q.title || q.sop_id) + '</div></div>';
                }).join('');
            }).catch(() => {});
        }
    }
}

function addSuggestions(suggestions) {
    if (!suggestions || !suggestions.length) return;
    const inner = document.getElementById('cw-messages-inner');
    const div = document.createElement('div');
    div.className = 'cw-suggestions';
    suggestions.forEach(s => {
        const btn = document.createElement('button');
        btn.textContent = s;
        btn.onclick = () => { STATE.inputEl.value = s; sendMsg(); div.remove(); };
        div.appendChild(btn);
    });
    inner.appendChild(div);
    STATE.messagesEl.scrollTop = STATE.messagesEl.scrollHeight;
}

async function sendMsg() {
    const q = STATE.inputEl.value.trim();
    if (!q || STATE.loading) return;
    STATE.inputEl.value = '';
    STATE.loading = true;
    STATE.sendBtn.disabled = true;

    const inner = document.getElementById('cw-messages-inner');

    // Session badge
    if (!STATE.chatStarted) {
        STATE.chatStarted = true;
        const welcome = inner.querySelector('.cw-welcome');
        if (welcome) welcome.remove();
        inner.insertAdjacentHTML('beforeend', `<div class="cw-session-badge"><span>SESSION STARTED: ${getTime()}</span></div>`);
    }

    // User message
    const userTime = getTime();
    inner.insertAdjacentHTML('beforeend', `<div class="cw-msg cw-msg-user">
        <div class="cw-msg-avatar"><span class="material-symbols-outlined" style="color:#006f7c">person</span></div>
        <div class="cw-msg-body">
            <div class="cw-bubble">${esc(q)}</div>
            <span class="cw-msg-time">${userTime} · Read</span>
        </div>
    </div>`);

    // Bot thinking
    const typingId = 'cw-typing-' + Date.now();
    inner.insertAdjacentHTML('beforeend', `<div id="${typingId}" class="cw-msg cw-msg-bot">
        <div class="cw-msg-avatar"><span class="material-symbols-outlined" style="color:#007518;font-variation-settings:'FILL' 1">smart_toy</span></div>
        <div class="cw-msg-body">
            <div class="cw-thinking-box">
                <div class="cw-thinking-header">
                    <span class="cw-thinking-badge">RAG ANALYZING</span>
                    <div class="cw-thinking-dots"><span></span><span></span><span></span></div>
                </div>
                <div class="cw-think-steps"></div>
            </div>
            <div class="cw-bubble" style="display:none"></div>
            <span class="cw-msg-time" style="display:none"></span>
        </div>
    </div>`);
    STATE.messagesEl.scrollTop = STATE.messagesEl.scrollHeight;

    const typingEl = document.getElementById(typingId);
    const stepsEl = typingEl.querySelector('.cw-think-steps');
    const thinkBox = typingEl.querySelector('.cw-thinking-box');
    const bubbleEl = typingEl.querySelector('.cw-bubble');
    const timeEl = typingEl.querySelector('.cw-msg-time');

    function addStep(msg, detail) {
        const prev = stepsEl.lastElementChild;
        if (prev) {
            const icon = prev.querySelector('.material-symbols-outlined');
            if (icon) { icon.textContent = 'check_circle'; icon.classList.remove('cw-loading'); icon.style.color = '#007518'; }
        }
        const s = document.createElement('div');
        s.className = 'cw-think-step';
        s.innerHTML = '<span class="material-symbols-outlined cw-loading" style="font-size:14px;color:#006f7c">progress_activity</span>'
            + '<span class="cw-step-text">' + esc(msg) + '</span>'
            + (detail ? '<span class="cw-step-detail">' + esc(detail) + '</span>' : '');
        stepsEl.appendChild(s);
        STATE.messagesEl.scrollTop = STATE.messagesEl.scrollHeight;
    }

    let answer = '', suggestions = [], sources = [], model = '', imageMap = {}, queryId = 0;

    try {
        const res = await fetch(STATE.chatApi, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: q, history: STATE.history.slice(-5) }),
        });
        if (!res.ok) throw new Error('Server returned ' + res.status);
        if (!res.body) throw new Error('No response body');
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', ev = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (line.startsWith('event: ')) ev = line.slice(7).trim();
                else if (line.startsWith('data: ')) {
                    try {
                        const d = JSON.parse(line.slice(6));
                        if (ev === 'status') {
                            addStep(d.message, d.detail || '');
                        } else if (ev === 'token') {
                            thinkBox.style.display = 'none';
                            bubbleEl.style.display = 'block';
                            answer += d.token;
                            bubbleEl.innerHTML = md(answer);
                            STATE.messagesEl.scrollTop = STATE.messagesEl.scrollHeight;
                        } else if (ev === 'answer_done') {
                            queryId = d.query_id || 0;
                        } else if (ev === 'sources') {
                            sources = d.sources || [];
                            model = d.model || '';
                            STATE.lastSources = sources;
                            if (sources.length) STATE.currentSopId = sources[0].sop_id || '';
                            if (answer) bubbleEl.innerHTML = md(answer);
                        } else if (ev === 'images') {
                            imageMap = d.image_map || {};
                            if (answer) {
                                let rendered = md(answer);
                                for (const [key, img] of Object.entries(imageMap)) {
                                    const imgTag = '<div class="cw-screenshot"><img src="'+img.url+'" onerror="this.parentElement.innerHTML=\'<div class=cw-screenshot-label>Screenshot not available</div>\'"><div class="cw-screenshot-label"><span class="material-symbols-outlined" style="font-size:12px">image</span> PAGE '+img.page+' · SCREENSHOT '+img.index+'</div></div>';
                                    rendered = rendered.replace(new RegExp('\\[IMG:'+img.page+':'+img.index+'\\]','g'), imgTag);
                                }
                                bubbleEl.innerHTML = rendered;
                            }
                        } else if (ev === 'suggestions') {
                            suggestions = d.suggestions || [];
                        }
                    } catch {} ev = '';
                }
            }
        }
    } catch (e) {
        thinkBox.style.display = 'none';
        bubbleEl.style.display = 'block';
        bubbleEl.innerHTML = 'Error: ' + esc(e.message);
    }

    // Finalize
    typingEl.id = '';

    // Sources row
    let extra = '';
    if (sources.length > 0) {
        extra += '<div class="cw-sources-row"><span class="cw-label">SOURCES:</span>';
        sources.forEach(s => {
            const pg = parseInt(s.pages) || 1;
            const safeSid = esc(s.sop_id).replace(/'/g, "\\'");
            extra += `<span class="cw-source-badge" onclick="ChatWidget.openPdf('${safeSid}',${pg})"><span class="material-symbols-outlined">description</span>${esc(s.sop_id)}${s.pages ? ' p' + esc(String(s.pages)) : ''}</span>`;
        });
        if (model) extra += `<span class="cw-model-badge">${esc(model)}</span>`;
        extra += '</div>';
    }

    // Referenced page thumbnails — extract cited pages from [REF:doc:page] tags
    const citedPages = [];
    const citeSeen = new Set();
    const citeRegex = /\[REF:([^\]:]+):(\d+[^\]]*)\]/g;
    let citeMatch;
    while ((citeMatch = citeRegex.exec(answer)) !== null) {
        const docId = citeMatch[1];
        const pageNums = citeMatch[2].split(/[,\s]+/).map(n => parseInt(n)).filter(n => n > 0);
        const resolvedDoc = resolveSopId(docId);
        const realDocId = resolvedDoc ? resolvedDoc.sop_id : docId.replace(/\.pdf$/i, '').toLowerCase();
        for (const pg of pageNums) {
            const key = realDocId + ':' + pg;
            if (!citeSeen.has(key)) {
                citeSeen.add(key);
                citedPages.push({ sop_id: realDocId, page: pg });
            }
        }
    }
    // Also add from sources if they have page numbers
    if (!citedPages.length && sources.length) {
        sources.forEach(s => {
            const pg = parseInt(s.pages) || 1;
            const key = s.sop_id + ':' + pg;
            if (!citeSeen.has(key)) { citeSeen.add(key); citedPages.push({ sop_id: s.sop_id, page: pg }); }
        });
    }
    if (citedPages.length > 0) {
        const imgBaseUrl = '/api/t/' + STATE.tenantId + '/admin/sops/';
        extra += '<div class="cw-ref-pages"><div class="cw-ref-pages-title">Referenced Pages</div><div class="cw-ref-pages-grid">';
        citedPages.slice(0, 6).forEach(cp => {
            extra += `<div class="cw-ref-thumb" onclick="ChatWidget.openPdf('${cp.sop_id}',${cp.page})">
                <img loading="lazy" src="${imgBaseUrl}${cp.sop_id}/pages/${cp.page}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22140%22 height=%22150%22><rect fill=%22%23ebe8dd%22 width=%22140%22 height=%22150%22/><text x=%2270%22 y=%2280%22 text-anchor=%22middle%22 fill=%22%2365655e%22 font-size=%2212%22>No preview</text></svg>'">
                <div class="cw-ref-thumb-label"><span>P${cp.page}</span><span class="cw-view">VIEW →</span></div>
            </div>`;
        });
        extra += '</div></div>';
    }

    // Feedback + copy
    if (queryId) {
        extra += `<div class="cw-feedback-row"><div style="display:flex;align-items:center;gap:4px">`;
        extra += `<span class="cw-fb-label">HELPFUL?</span>`;
        extra += `<button class="cw-fb-btn" onclick="ChatWidget.feedback(this,'up',${queryId})"><span class="material-symbols-outlined" style="font-size:16px">thumb_up</span></button>`;
        extra += `<button class="cw-fb-btn" onclick="ChatWidget.feedback(this,'down',${queryId})"><span class="material-symbols-outlined" style="font-size:16px">thumb_down</span></button>`;
        extra += `</div>`;
        extra += `<button class="cw-copy-btn" onclick="ChatWidget.copy(this)"><span class="material-symbols-outlined" style="font-size:14px">content_copy</span> COPY</button>`;
        extra += `</div>`;
    }
    // Escalation card — show when agent can't find answer (or always if configured)
    const escCfg = STATE.escalation;
    if (escCfg && (escCfg.team || escCfg.email || escCfg.url)) {
        const notFoundPhrases = ["not found", "couldn't find", "don't have", "no match", "not in our", "not available", "not documented", "no information", "not covered", "don't have information"];
        const isNotFound = notFoundPhrases.some(p => answer.toLowerCase().includes(p));
        if (isNotFound || escCfg.always) {
            extra += `<div class="cw-escalation">`;
            extra += `<div class="cw-escalation-title"><span class="material-symbols-outlined" style="font-size:16px">support_agent</span>${esc(escCfg.message || 'Need more help?')}</div>`;
            extra += `<div class="cw-escalation-grid">`;
            if (escCfg.email) extra += `<div class="cw-escalation-item"><span class="material-symbols-outlined" style="font-size:16px">mail</span><a href="mailto:${esc(escCfg.email)}">${esc(escCfg.email)}</a></div>`;
            if (escCfg.phone) extra += `<div class="cw-escalation-item"><span class="material-symbols-outlined" style="font-size:16px">call</span>${esc(escCfg.phone)}</div>`;
            if (escCfg.url) extra += `<div class="cw-escalation-item"><a href="${esc(escCfg.url)}" target="_blank" style="display:flex;align-items:center;gap:4px;padding:4px 12px;background:#00fc40;color:#383832;border:2px solid #383832;text-decoration:none;font-size:11px;font-weight:900;text-transform:uppercase"><span class="material-symbols-outlined" style="font-size:14px">confirmation_number</span>RAISE TICKET</a></div>`;
            if (escCfg.chat) extra += `<div class="cw-escalation-item"><a href="${esc(escCfg.chat)}" target="_blank" style="display:flex;align-items:center;gap:4px;padding:4px 12px;background:#383832;color:#feffd6;border:2px solid #383832;text-decoration:none;font-size:11px;font-weight:900;text-transform:uppercase"><span class="material-symbols-outlined" style="font-size:14px">chat</span>OPEN CHAT</a></div>`;
            extra += `</div>`;
            const meta = [];
            if (escCfg.team) meta.push(esc(escCfg.team));
            if (escCfg.hours) meta.push(esc(escCfg.hours));
            if (escCfg.sla) meta.push('Response: ' + esc(escCfg.sla));
            if (escCfg.priority) meta.push(esc(escCfg.priority));
            if (meta.length) extra += `<div class="cw-escalation-meta">${meta.map(m => '<span>' + m + '</span>').join('')}</div>`;
            extra += `</div>`;
        }
    }

    if (extra) bubbleEl.innerHTML += extra;

    // Timestamp
    timeEl.style.display = 'block';
    timeEl.textContent = getTime() + ' · Agent';

    // Hide thinking box
    if (thinkBox.style.display !== 'none') thinkBox.style.display = 'none';

    // Save to history for multi-turn context
    if (answer) STATE.history.push({ role: 'user', content: q }, { role: 'assistant', content: answer.substring(0, 500) });

    addSuggestions(suggestions);
    STATE.loading = false;
    STATE.sendBtn.disabled = false;
    STATE.inputEl.focus();
    saveMessages();
}

function sendFeedback(btn, type, qId) {
    const row = btn.closest('.cw-feedback-row');
    row.querySelectorAll('.cw-fb-btn').forEach(b => { b.classList.remove('cw-active-up','cw-active-down'); });
    btn.classList.add(type === 'up' ? 'cw-active-up' : 'cw-active-down');

    if (type === 'up') {
        // Instant save — no popup
        fetch(STATE.feedbackApi, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query_id: qId || 0, feedback: 'up' }),
        }).catch(()=>{});
        return;
    }

    // Thumbs down — show reason popup
    const existing = row.parentElement.querySelector('.cw-fb-popup');
    if (existing) { existing.remove(); return; } // toggle off

    const popup = document.createElement('div');
    popup.className = 'cw-fb-popup';
    popup.innerHTML = `
        <div class="cw-fb-popup-title">What went wrong?</div>
        <div class="cw-fb-reasons">
            <button class="cw-fb-reason" data-r="Wrong answer">Wrong answer</button>
            <button class="cw-fb-reason" data-r="Missing information">Missing info</button>
            <button class="cw-fb-reason" data-r="Wrong document referenced">Wrong document</button>
            <button class="cw-fb-reason" data-r="Too vague">Too vague</button>
        </div>
        <textarea rows="2" placeholder="Add details (optional)..."></textarea>
        <button class="cw-fb-submit">SUBMIT FEEDBACK</button>
    `;
    row.parentElement.appendChild(popup);

    let selectedReason = '';
    popup.querySelectorAll('.cw-fb-reason').forEach(r => {
        r.onclick = () => {
            popup.querySelectorAll('.cw-fb-reason').forEach(x => x.classList.remove('cw-selected'));
            r.classList.add('cw-selected');
            selectedReason = r.dataset.r;
        };
    });

    popup.querySelector('.cw-fb-submit').onclick = () => {
        const details = popup.querySelector('textarea').value.trim();
        const comment = [selectedReason, details].filter(Boolean).join(': ');
        fetch(STATE.feedbackApi, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query_id: qId || 0, feedback: 'down', comment: comment }),
        }).catch(()=>{});
        popup.innerHTML = '<div style="font-size:10px;font-weight:900;color:#007518;text-transform:uppercase;padding:4px 0">FEEDBACK SUBMITTED</div>';
        setTimeout(() => popup.remove(), 2000);
    };
}

function copyText(btn) {
    const bubble = btn.closest('.cw-bubble');
    if (bubble) {
        // Clone bubble, remove sources/feedback/thumbnails, copy only answer text
        const clone = bubble.cloneNode(true);
        clone.querySelectorAll('.cw-sources-row, .cw-feedback-row, .cw-ref-pages, .cw-fb-popup').forEach(el => el.remove());
        navigator.clipboard.writeText(clone.innerText.trim());
    }
    btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px">check</span> COPIED';
    setTimeout(() => { btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px">content_copy</span> COPY'; }, 2000);
}

function openPdf(sopId, page) {
    const panel = document.getElementById('cw-pdf-panel');
    const resolved = resolveSopId(sopId);
    // sop_ids in DB are typically lowercase; LLM may write uppercase
    const realId = resolved ? resolved.sop_id : sopId.replace(/\.pdf$/i, '').toLowerCase();
    const docName = resolved ? (resolved.doc_name || resolved.title || resolved.sop_id) : realId;
    const pageCount = resolved ? (parseInt(resolved.page_count) || 10) : 10;

    document.getElementById('cw-pdf-title-text').textContent = docName;
    panel.classList.add('cw-open');
    document.getElementById('cw-root').style.width = '50%';

    // DOCX download button (admin mode with allDocs)
    const dlBtn = document.getElementById('cw-pdf-dl');
    const doc = STATE.allDocs.find(d => d.sop_id === realId);
    if (doc && doc.sop_score > 0 && STATE.adminApi) {
        dlBtn.style.display = 'inline-flex';
        dlBtn.onclick = () => window.open(STATE.adminApi + '/sops/' + realId + '/download/docx', '_blank');
    } else {
        dlBtn.style.display = 'none';
    }

    const imgBase = '/api/t/' + STATE.tenantId + '/admin/sops/' + realId + '/pages/';
    console.log('[ChatWidget] openPdf:', { sopId, realId, resolved: !!resolved, pageCount, tenantId: STATE.tenantId, imgBase });
    const content = document.getElementById('cw-pdf-content');

    // Fetch page 1 first to get the real page count from X-Total-Pages header
    const cacheBust = Date.now();
    fetch(imgBase + '1?t=' + cacheBust).then(resp => {
        const totalFromHeader = parseInt(resp.headers.get('X-Total-Pages'));
        const realPageCount = (totalFromHeader > 0) ? totalFromHeader : pageCount;
        console.log('[ChatWidget] openPdf realPageCount:', { fromHeader: totalFromHeader, fallback: pageCount, using: realPageCount });
        _renderPdfPages(content, imgBase, cacheBust, realPageCount, page);
    }).catch(() => {
        _renderPdfPages(content, imgBase, cacheBust, pageCount, page);
    });
}

function _renderPdfPages(content, imgBase, cacheBust, pageCount, page) {
    let html = '';
    for (let p = 1; p <= Math.min(pageCount, 30); p++) {
        const isRef = p === page;
        // Eager-load pages near the target so scroll position is accurate
        const nearTarget = Math.abs(p - page) <= 3;
        const loadAttr = nearTarget ? '' : ' loading="lazy"';
        html += `<div class="cw-pdf-page" id="cw-pdf-p-${p}" style="min-height:200px;${isRef?'border:3px solid #007518':''}">
            <div class="cw-pdf-page-label" style="${isRef?'background:#007518':''}">PAGE ${p}${isRef?' ← REFERENCED':''}</div>
            <img${loadAttr} src="${imgBase}${p}?t=${cacheBust}" onload="this.parentElement.style.minHeight='auto'" onerror="this.style.display='none';this.parentElement.style.minHeight='auto';this.nextElementSibling&&(this.nextElementSibling.style.display='block')" style="width:100%;display:block">
            <div style="display:none;padding:20px;text-align:center;color:#65655e;font-size:11px">Failed to load page ${p}</div>
        </div>`;
    }
    content.innerHTML = html;
    // Wait for near-target images to load before scrolling
    if (page > 1) {
        const targetEl = document.getElementById('cw-pdf-p-' + page);
        if (targetEl) {
            const img = targetEl.querySelector('img');
            const doScroll = () => targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            if (img && img.complete) { setTimeout(doScroll, 50); }
            else if (img) { img.addEventListener('load', doScroll, { once: true }); setTimeout(doScroll, 800); }
            else { setTimeout(doScroll, 200); }
        }
    }
}

function exportChatPdf() {
    const inner = document.getElementById('cw-messages-inner');
    if (!inner) return;
    const win = window.open('', '_blank');
    win.document.write(`<!DOCTYPE html><html><head>
        <title>Chat Export - ${STATE.agentName}</title>
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700;900&display=swap" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; border-radius: 0 !important; }
            body { font-family: 'Space Grotesk', sans-serif; background: white; color: #383832; padding: 40px; }
            img { max-width: 400px; height: auto; }
            @media print { body { padding: 20px; } }
        </style>
    </head><body>
        <h1 style="font-size:18px;font-weight:900;text-transform:uppercase;margin-bottom:20px">${STATE.agentName} — Chat Export</h1>
        ${inner.innerHTML}
    </body></html>`);
    win.document.close();
    setTimeout(() => { win.print(); }, 500);
}

function closePdf() {
    document.getElementById('cw-pdf-panel').classList.remove('cw-open');
    document.getElementById('cw-root').style.width = '100%';
    // Scroll chat to bottom after panel closes
    setTimeout(() => { if (STATE.messagesEl) STATE.messagesEl.scrollTop = STATE.messagesEl.scrollHeight; }, 300);
}

/* ── Public API ───────────────────────────────────────────────────────────── */
window.ChatWidget = {
    init: function(opts) {
        injectCSS();

        STATE.mode = opts.mode || 'public';
        STATE.chatApi = opts.chatApi || '/api/chat';
        STATE.feedbackApi = opts.feedbackApi || '/api/chat/feedback';
        STATE.tenantId = opts.tenantId || '';
        STATE.adminApi = opts.adminApi || '';
        STATE.agentName = opts.agentName || 'Document Agent';
        STATE.logoUrl = opts.logoUrl || '';
        STATE.allDocs = opts.allDocs || [];
        STATE.escalation = opts.escalation || null;

        const container = opts.container;
        container.style.display = 'flex';
        container.style.flexDirection = 'row';
        container.innerHTML = buildHTML();

        STATE.container = container;
        STATE.messagesEl = document.getElementById('cw-messages');
        STATE.inputEl = document.getElementById('cw-input');
        STATE.sendBtn = document.getElementById('cw-send-btn');
        STATE.pdfPanel = document.getElementById('cw-pdf-panel');

        // Auto-resize textarea
        STATE.inputEl.addEventListener('input', () => {
            STATE.inputEl.style.height = 'auto';
            STATE.inputEl.style.height = Math.min(STATE.inputEl.scrollHeight, 120) + 'px';
        });

        // Restore previous session
        const hasRestoredSession = restoreMessages();

        // Load starter question cards from trained Q&A pairs
        // Only show when welcome screen is visible (no restored conversation)
        if (STATE.tenantId && !hasRestoredSession) {
            const starterUrl = '/api/t/' + STATE.tenantId + '/admin/starter-questions?limit=4';
            fetch(starterUrl).then(r => r.ok ? r.json() : []).then(questions => {
                const container = document.getElementById('cw-starter-cards');
                if (!container || !questions.length) return;
                const icons = ['chat_bubble', 'help', 'search', 'description'];
                container.className = 'cw-starter-grid';
                container.innerHTML = questions.slice(0, 4).map((q, i) => {
                    const safeQ = q.question.replace(/'/g, '&#39;').replace(/"/g, '&quot;');
                    return '<div class="cw-starter-card" onclick="ChatWidget.askStarter(\'' + safeQ.replace(/\\/g,'\\\\') + '\')">'
                        + '<div class="cw-starter-icon"><span class="material-symbols-outlined">' + icons[i % 4] + '</span></div>'
                        + '<div class="cw-starter-q">' + esc(q.question) + '</div>'
                        + '<div class="cw-starter-src">' + esc(q.title || q.sop_id) + '</div>'
                        + '</div>';
                }).join('');
            }).catch(() => {});
        }

        // Scroll-to-bottom button visibility
        // Click on empty chat area closes PDF panel (but not on citations/badges/buttons)
        STATE.messagesEl.addEventListener('click', (e) => {
            const panel = document.getElementById('cw-pdf-panel');
            if (!panel || !panel.classList.contains('cw-open')) return;
            // Don't close if clicking on interactive elements that open PDF
            const tag = e.target.tagName;
            const cl = e.target.className || '';
            if (e.target.closest('.cw-cite-ref, .cw-source-badge, .cw-ref-thumb, .cw-screenshot, .cw-ref-pages, [onclick*="openPdf"]')) return;
            if (tag === 'SUP' || tag === 'SPAN' || tag === 'IMG') return;
            closePdf();
        });

        STATE.messagesEl.addEventListener('scroll', () => {
            const el = STATE.messagesEl;
            const btn = document.getElementById('cw-scroll-btn');
            if (btn) btn.style.display = (el.scrollHeight - el.scrollTop - el.clientHeight > 200) ? 'flex' : 'none';
        });

        // Only fetch agent name if not already provided via opts
        if (STATE.agentName === 'Document Agent') {
            fetch('/api/super/agent-config').then(r => {
                if (!r.ok) return null;
                return r.json();
            }).then(c => {
                if (!c || !c.name) return;
                STATE.agentName = c.name;
                const el = document.getElementById('cw-agent-name');
                if (el) el.textContent = c.name;
                const wt = document.getElementById('cw-welcome-title');
                if (wt) wt.textContent = c.name;
                const ft = document.getElementById('cw-footer');
                if (ft) ft.textContent = c.name + ' can make mistakes. Verify critical information.';
            }).catch(()=>{});
        }
    },

    send: sendMsg,
    askStarter: function(q) { STATE.inputEl.value = q; sendMsg(); },
    clearChat: clearChat,
    exportChat: function() {
        const lines = [];
        lines.push('Chat Export — ' + STATE.agentName);
        lines.push('Date: ' + new Date().toLocaleString());
        lines.push(''.padEnd(50, '─'));
        STATE.history.forEach(h => {
            if (h.role === 'user') lines.push('\n[YOU] ' + h.content);
            else lines.push('\n[AGENT] ' + h.content);
        });
        if (!STATE.history.length) { lines.push('\nNo messages to export.'); }
        const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'chat-export-' + new Date().toISOString().slice(0,10) + '.txt';
        a.click();
        URL.revokeObjectURL(a.href);
    },
    exportPdf: exportChatPdf,
    openPdf: openPdf,
    closePdf: closePdf,
    feedback: sendFeedback,
    copy: copyText,

    // Allow admin to update allDocs dynamically
    setDocs: function(docs) { STATE.allDocs = docs; },
    setAgentName: function(name) {
        STATE.agentName = name;
        const el = document.getElementById('cw-agent-name');
        if (el) el.textContent = name;
        const ft = document.getElementById('cw-footer');
        if (ft) ft.textContent = name + ' can make mistakes. Verify critical information.';
    },
};

})();
