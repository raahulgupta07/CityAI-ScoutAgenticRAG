import type { ImageMap, Source } from "./types";

/**
 * Convert markdown-like text with [IMG:page:index] tags into HTML.
 * Renders screenshots inline with each step.
 */
export function renderAnswer(text: string, imageMap: ImageMap, apiUrl: string): string {
  // Split by [IMG:page:index] tags
  const parts = text.split(/\[IMG:(\d+):(\d+)\]/);
  let html = "";
  const shown = new Set<string>();

  for (let i = 0; i < parts.length; i++) {
    if (i % 3 === 0) {
      // Text block — convert markdown to HTML
      html += markdownToHtml(parts[i]);
    } else if (i % 3 === 1 && i + 1 < parts.length) {
      // page number
      const page = parts[i];
      const index = parts[i + 1];
      const key = `${page}_${index}`;

      if (!shown.has(key)) {
        shown.add(key);
        const img = imageMap[key];
        if (img) {
          const imgUrl = img.url.startsWith("http") ? img.url : `${apiUrl}${img.url}`;
          html += `
            <div class="itsm-screenshot">
              <div class="itsm-screenshot-label">📸 ${img.sop_id} — Page ${img.page}, Screenshot ${img.index}</div>
              <img src="${imgUrl}" alt="Document screenshot" onclick="document.getElementById('itsm-lightbox').querySelector('img').src='${imgUrl}';document.getElementById('itsm-lightbox').classList.add('open');" />
            </div>`;
        }
      }
      i++; // skip index part
    }
  }

  return html;
}

/**
 * Minimal markdown → HTML converter.
 */
function markdownToHtml(text: string): string {
  if (!text.trim()) return "";

  let html = escapeHtml(text);

  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic: *text*
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Inline code: `text`
  html = html.replace(/`(.+?)`/g, '<code style="background:#f1f3f5;padding:1px 4px;border-radius:3px;font-size:0.9em;">$1</code>');

  // Unordered list items: * text or - text
  html = html.replace(/^[\*\-]\s+(.+)$/gm, "<li>$1</li>");

  // Ordered list items: 1. text
  html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");

  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*<\/li>\s*)+)/g, "<ul>$1</ul>");

  // Line breaks (double newline = paragraph)
  html = html.replace(/\n\n/g, "</p><p>");
  html = html.replace(/\n/g, "<br>");

  // Wrap in paragraph
  html = `<p>${html}</p>`;

  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, "");

  return html;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Render source badges.
 */
export function renderSources(sources: Source[], model: string, imageCount: number): string {
  let html = '<div class="itsm-sources">';

  for (const s of sources) {
    html += `<span class="itsm-badge itsm-badge-source">${s.sop_id} (p${s.pages || "?"})</span>`;
  }

  if (imageCount > 0) {
    html += `<span class="itsm-badge itsm-badge-img">${imageCount} screenshot(s)</span>`;
  }

  if (model) {
    html += `<span class="itsm-badge itsm-badge-model">${model}</span>`;
  }

  html += "</div>";
  return html;
}

/**
 * Render typing indicator.
 */
export function renderTyping(): string {
  return `
    <div class="itsm-msg itsm-msg-assistant itsm-typing">
      <div class="itsm-typing-dot"></div>
      <div class="itsm-typing-dot"></div>
      <div class="itsm-typing-dot"></div>
    </div>`;
}
