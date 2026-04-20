export function getStyles(color: string): string {
  return `
    #itsm-widget-root * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }

    #itsm-fab {
      position: fixed; bottom: 24px; right: 24px; z-index: 99999;
      width: 60px; height: 60px; border-radius: 50%;
      background: ${color}; color: #fff; border: none; cursor: pointer;
      box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      font-size: 26px; display: flex; align-items: center; justify-content: center;
      transition: transform 0.2s, box-shadow 0.2s;
    }
    #itsm-fab:hover { transform: scale(1.08); box-shadow: 0 6px 24px rgba(0,0,0,0.3); }

    #itsm-panel {
      position: fixed; bottom: 96px; right: 24px; z-index: 99998;
      width: 420px; height: 620px; max-height: calc(100vh - 120px);
      background: #fff; border-radius: 16px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.15);
      display: none; flex-direction: column; overflow: hidden;
    }
    #itsm-panel.open { display: flex; }

    @media (max-width: 480px) {
      #itsm-panel { width: calc(100vw - 16px); right: 8px; bottom: 88px; height: calc(100vh - 100px); }
    }

    /* Header */
    #itsm-header {
      background: ${color}; color: #fff; padding: 16px 20px;
      display: flex; align-items: center; justify-content: space-between;
      flex-shrink: 0;
    }
    #itsm-header-title { font-size: 16px; font-weight: 600; }
    #itsm-header-close {
      background: none; border: none; color: #fff; font-size: 22px;
      cursor: pointer; opacity: 0.8; line-height: 1;
    }
    #itsm-header-close:hover { opacity: 1; }

    /* Messages area */
    #itsm-messages {
      flex: 1; overflow-y: auto; padding: 16px;
      display: flex; flex-direction: column; gap: 12px;
    }

    .itsm-msg {
      max-width: 90%; padding: 10px 14px; border-radius: 12px;
      font-size: 14px; line-height: 1.55; word-wrap: break-word;
    }
    .itsm-msg-user {
      align-self: flex-end; background: ${color}; color: #fff;
      border-bottom-right-radius: 4px;
    }
    .itsm-msg-assistant {
      align-self: flex-start; background: #f1f3f5; color: #212529;
      border-bottom-left-radius: 4px;
    }

    /* Markdown inside assistant messages */
    .itsm-msg-assistant strong { font-weight: 700; }
    .itsm-msg-assistant ul, .itsm-msg-assistant ol { padding-left: 20px; margin: 6px 0; }
    .itsm-msg-assistant li { margin: 3px 0; }
    .itsm-msg-assistant p { margin: 6px 0; }

    /* Screenshots */
    .itsm-screenshot {
      margin: 10px 0; border-radius: 8px; overflow: hidden;
      border: 2px solid #dee2e6; background: #f8f9fa;
    }
    .itsm-screenshot-label {
      background: ${color}; color: #fff; padding: 4px 12px;
      font-size: 11px; font-weight: 600; letter-spacing: 0.3px;
    }
    .itsm-screenshot img {
      width: 100%; display: block; cursor: pointer;
    }
    .itsm-screenshot img:hover { opacity: 0.95; }

    /* Source badges */
    .itsm-sources { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
    .itsm-badge {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 11px; font-weight: 500;
    }
    .itsm-badge-source { background: #e3f2fd; color: #1565c0; }
    .itsm-badge-model { background: #f3e5f5; color: #6a1b9a; }
    .itsm-badge-img { background: #e8f5e9; color: #2e7d32; }

    /* Input area */
    #itsm-input-area {
      display: flex; padding: 12px 16px; border-top: 1px solid #e9ecef;
      background: #fff; flex-shrink: 0; gap: 8px;
    }
    #itsm-input {
      flex: 1; border: 1px solid #dee2e6; border-radius: 8px;
      padding: 10px 14px; font-size: 14px; outline: none;
      resize: none; height: 42px; line-height: 1.4;
    }
    #itsm-input:focus { border-color: ${color}; box-shadow: 0 0 0 2px ${color}22; }
    #itsm-send {
      background: ${color}; color: #fff; border: none; border-radius: 8px;
      width: 42px; cursor: pointer; font-size: 18px; flex-shrink: 0;
    }
    #itsm-send:hover { opacity: 0.9; }
    #itsm-send:disabled { opacity: 0.5; cursor: not-allowed; }

    /* Typing indicator */
    .itsm-typing { display: flex; gap: 4px; padding: 8px 14px; }
    .itsm-typing-dot {
      width: 8px; height: 8px; border-radius: 50%; background: #adb5bd;
      animation: itsm-bounce 1.4s infinite ease-in-out both;
    }
    .itsm-typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .itsm-typing-dot:nth-child(2) { animation-delay: -0.16s; }
    @keyframes itsm-bounce {
      0%, 80%, 100% { transform: scale(0); }
      40% { transform: scale(1); }
    }

    /* Image lightbox */
    #itsm-lightbox {
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(0,0,0,0.85); z-index: 999999;
      display: none; align-items: center; justify-content: center;
      cursor: pointer;
    }
    #itsm-lightbox.open { display: flex; }
    #itsm-lightbox img { max-width: 95%; max-height: 95%; border-radius: 8px; }
  `;
}
