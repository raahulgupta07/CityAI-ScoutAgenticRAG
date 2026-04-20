import type { ChatMessage, ImageMap, Source } from "./types";

export interface ChatResult {
  answer: string;
  sources: Source[];
  imageMap: ImageMap;
  model: string;
}

export async function sendMessage(
  apiUrl: string,
  question: string,
  history: ChatMessage[],
  onStatus: (msg: string) => void,
  onComplete: (result: ChatResult) => void,
  onError: (err: string) => void,
): Promise<void> {
  const body = {
    question,
    history: history.slice(-6).map((m) => ({ role: m.role, content: m.content })),
  };

  try {
    const res = await fetch(`${apiUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      onError(`API error: ${res.status}`);
      return;
    }

    const reader = res.body?.getReader();
    if (!reader) {
      onError("No response stream");
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    let sources: Source[] = [];
    let imageMap: ImageMap = {};
    let model = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let eventType = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const data = line.slice(6);
          try {
            const parsed = JSON.parse(data);

            if (eventType === "status") {
              onStatus(parsed.message || "Processing...");
            } else if (eventType === "answer") {
              answer = parsed.answer || "";
            } else if (eventType === "sources") {
              sources = parsed.sources || [];
              model = parsed.model || "";
            } else if (eventType === "images") {
              imageMap = parsed.image_map || {};
            } else if (eventType === "done") {
              onComplete({ answer, sources, imageMap, model });
            }
          } catch {}
          eventType = "";
        }
      }
    }

    // If done event wasn't sent, complete anyway
    if (answer) {
      onComplete({ answer, sources, imageMap, model });
    }
  } catch (err: any) {
    onError(err.message || "Connection failed");
  }
}
