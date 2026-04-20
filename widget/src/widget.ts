import type { WidgetConfig, ChatMessage } from "./types";
import { getStyles } from "./styles";
import { sendMessage } from "./chat";
import { renderAnswer, renderSources, renderTyping } from "./renderer";

(function () {
  // ── Read config from script tag ──────────────────────────────────────
  const scriptTag = document.currentScript as HTMLScriptElement | null;
  const config: WidgetConfig = {
    api: scriptTag?.getAttribute("data-api") || window.location.origin,
    title: scriptTag?.getAttribute("data-title") || "Document Assistant",
    color: scriptTag?.getAttribute("data-color") || "#1976d2",
    welcome: scriptTag?.getAttribute("data-welcome") || "Hi! Ask me about any document. I can show you step-by-step guides with screenshots.",
    position: (scriptTag?.getAttribute("data-position") as any) || "bottom-right",
  };

  const messages: ChatMessage[] = [];
  let isOpen = false;
  let isLoading = false;

  // ── Inject styles ────────────────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = getStyles(config.color!);
  document.head.appendChild(style);

  // ── Create DOM ───────────────────────────────────────────────────────
  const root = document.createElement("div");
  root.id = "itsm-widget-root";
  root.innerHTML = `
    <button id="itsm-fab" aria-label="Open chat">💬</button>

    <div id="itsm-panel">
      <div id="itsm-header">
        <span id="itsm-header-title">${config.title}</span>
        <button id="itsm-header-close" aria-label="Close">&times;</button>
      </div>
      <div id="itsm-messages"></div>
      <div id="itsm-input-area">
        <input id="itsm-input" type="text" placeholder="Ask about any document..." autocomplete="off" />
        <button id="itsm-send" aria-label="Send">&#10148;</button>
      </div>
    </div>

    <div id="itsm-lightbox" onclick="this.classList.remove('open')">
      <img src="" alt="Full screenshot" />
    </div>
  `;
  document.body.appendChild(root);

  // ── References ───────────────────────────────────────────────────────
  const fab = document.getElementById("itsm-fab")!;
  const panel = document.getElementById("itsm-panel")!;
  const closeBtn = document.getElementById("itsm-header-close")!;
  const messagesEl = document.getElementById("itsm-messages")!;
  const input = document.getElementById("itsm-input") as HTMLInputElement;
  const sendBtn = document.getElementById("itsm-send") as HTMLButtonElement;

  // ── Toggle panel ─────────────────────────────────────────────────────
  function toggle() {
    isOpen = !isOpen;
    panel.classList.toggle("open", isOpen);
    fab.textContent = isOpen ? "✕" : "💬";
    if (isOpen) {
      input.focus();
      // Show welcome message on first open
      if (messages.length === 0) {
        addMessage("assistant", config.welcome!);
      }
    }
  }

  fab.addEventListener("click", toggle);
  closeBtn.addEventListener("click", toggle);

  // ── Add message to UI ────────────────────────────────────────────────
  function addMessage(role: "user" | "assistant", content: string, images?: any, sources?: any[], model?: string) {
    messages.push({ role, content, images, sources, model });

    const el = document.createElement("div");
    el.className = `itsm-msg itsm-msg-${role}`;

    if (role === "user") {
      el.textContent = content;
    } else {
      let html = "";
      if (images && Object.keys(images).length > 0) {
        html = renderAnswer(content, images, config.api);
      } else {
        // Simple markdown render
        html = renderAnswer(content, {}, config.api);
      }

      if (sources && sources.length > 0) {
        const imgCount = images ? Object.keys(images).length : 0;
        html += renderSources(sources, model || "", imgCount);
      }

      el.innerHTML = html;
    }

    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ── Send question ────────────────────────────────────────────────────
  async function send() {
    const question = input.value.trim();
    if (!question || isLoading) return;

    input.value = "";
    isLoading = true;
    sendBtn.disabled = true;

    // Add user message
    addMessage("user", question);

    // Add typing indicator
    const typingEl = document.createElement("div");
    typingEl.innerHTML = renderTyping();
    typingEl.id = "itsm-typing";
    messagesEl.appendChild(typingEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    await sendMessage(
      config.api,
      question,
      messages,
      // onStatus
      (msg) => {
        const t = document.getElementById("itsm-typing");
        if (t) t.querySelector(".itsm-msg")!.textContent = msg;
      },
      // onComplete
      (result) => {
        // Remove typing indicator
        const t = document.getElementById("itsm-typing");
        if (t) t.remove();

        addMessage("assistant", result.answer, result.imageMap, result.sources, result.model);

        isLoading = false;
        sendBtn.disabled = false;
        input.focus();
      },
      // onError
      (err) => {
        const t = document.getElementById("itsm-typing");
        if (t) t.remove();

        addMessage("assistant", `Sorry, something went wrong: ${err}`);

        isLoading = false;
        sendBtn.disabled = false;
      },
    );
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
})();
