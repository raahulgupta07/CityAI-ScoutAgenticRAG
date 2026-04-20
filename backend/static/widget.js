/**
 * Document Agentic RAG — Embeddable Chat Widget
 * Loads /embed in an iframe popup with all features:
 * streaming, citations, PDF panel, suggestions, feedback
 *
 * Usage:
 *   <script src="https://your-server/widget.js" data-title="Assistant" data-color="#1976d2"></script>
 */
(function() {
  const script = document.currentScript;
  const color = script?.getAttribute('data-color') || '#1a237e';
  const title = script?.getAttribute('data-title') || 'Document Assistant';
  const api = script?.getAttribute('data-api') || '';
  const tenant = script?.getAttribute('data-tenant') || '';
  const chatToken = script?.getAttribute('data-token') || '';
  const position = script?.getAttribute('data-position') || 'bottom-right';

  // Determine embed URL — token > tenant > default
  const base = api || window.location.origin;
  const embedUrl = chatToken ? base + '/c/' + chatToken
    : tenant ? base + '/t/' + tenant + '/embed'
    : base + '/embed';

  // Inject styles
  const style = document.createElement('style');
  style.textContent = `
    #docrag-widget * { box-sizing: border-box; margin: 0; padding: 0; }
    #docrag-fab {
      position: fixed; bottom: 24px; ${position === 'bottom-left' ? 'left: 24px' : 'right: 24px'}; z-index: 99999;
      width: 60px; height: 60px; border-radius: 50%;
      background: ${color}; color: #fff; border: none; cursor: pointer;
      box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      font-size: 28px; display: flex; align-items: center; justify-content: center;
      transition: transform 0.2s, box-shadow 0.2s;
      font-family: -apple-system, sans-serif;
    }
    #docrag-fab:hover { transform: scale(1.08); box-shadow: 0 6px 24px rgba(0,0,0,0.3); }
    #docrag-fab.open { transform: rotate(45deg); }
    #docrag-panel {
      display: none; position: fixed;
      bottom: 96px; ${position === 'bottom-left' ? 'left: 24px' : 'right: 24px'};
      width: 420px; height: 600px;
      z-index: 99998; border-radius: 16px;
      overflow: hidden; box-shadow: 0 8px 40px rgba(0,0,0,0.2);
      background: white; border: 1px solid #e0e0e0;
      flex-direction: column;
      animation: docrag-slideup 0.25s ease-out;
    }
    #docrag-panel.open { display: flex; }
    @media (max-width: 480px) {
      #docrag-panel { width: calc(100vw - 16px); ${position === 'bottom-left' ? 'left: 8px' : 'right: 8px'}; bottom: 88px; height: calc(100vh - 100px); border-radius: 12px; }
    }
    @keyframes docrag-slideup { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    #docrag-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 16px; background: ${color}; color: white;
    }
    #docrag-header-title { font-size: 14px; font-weight: 700; font-family: -apple-system, sans-serif; }
    #docrag-header-close { background: rgba(255,255,255,0.2); border: none; color: white; width: 28px; height: 28px; border-radius: 8px; cursor: pointer; font-size: 16px; display: flex; align-items: center; justify-content: center; }
    #docrag-header-close:hover { background: rgba(255,255,255,0.3); }
    #docrag-iframe { flex: 1; border: none; width: 100%; height: 100%; }
    #docrag-badge { position: fixed; bottom: 90px; ${position === 'bottom-left' ? 'left: 24px' : 'right: 24px'}; z-index: 99997; display: none; }
    #docrag-badge.show { display: block; animation: docrag-slideup 0.3s ease-out; }
    #docrag-badge-inner {
      background: white; border: 1px solid #e0e0e0; border-radius: 12px; padding: 10px 16px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.1); font-size: 13px; color: #333; max-width: 260px;
      font-family: -apple-system, sans-serif; cursor: pointer;
    }
  `;
  document.head.appendChild(style);

  // Create DOM
  const root = document.createElement('div');
  root.id = 'docrag-widget';
  root.innerHTML = `
    <div id="docrag-badge"><div id="docrag-badge-inner">👋 Need help? Ask me anything about our documents.</div></div>
    <button id="docrag-fab" aria-label="Open chat">💬</button>
    <div id="docrag-panel">
      <div id="docrag-header">
        <span id="docrag-header-title">${title}</span>
        <button id="docrag-header-close" aria-label="Close">&times;</button>
      </div>
      <iframe id="docrag-iframe" src="about:blank"></iframe>
    </div>
  `;
  document.body.appendChild(root);

  const fab = document.getElementById('docrag-fab');
  const panel = document.getElementById('docrag-panel');
  const closeBtn = document.getElementById('docrag-header-close');
  const iframe = document.getElementById('docrag-iframe');
  const badge = document.getElementById('docrag-badge');
  let isOpen = false;
  let iframeLoaded = false;

  function toggle() {
    isOpen = !isOpen;
    panel.classList.toggle('open', isOpen);
    fab.classList.toggle('open', isOpen);
    fab.textContent = isOpen ? '+' : '💬';
    badge.classList.remove('show');

    // Lazy-load iframe on first open
    if (isOpen && !iframeLoaded) {
      iframe.src = embedUrl;
      iframeLoaded = true;
    }
  }

  fab.addEventListener('click', toggle);
  closeBtn.addEventListener('click', toggle);
  badge.addEventListener('click', toggle);

  // Show badge after 3 seconds
  setTimeout(() => {
    if (!isOpen) badge.classList.add('show');
    // Auto-hide badge after 8 seconds
    setTimeout(() => badge.classList.remove('show'), 8000);
  }, 3000);
})();
