export interface WidgetConfig {
  api: string;
  title?: string;
  color?: string;
  welcome?: string;
  position?: "bottom-right" | "bottom-left";
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  images?: ImageMap;
  sources?: Source[];
  model?: string;
}

export interface Source {
  sop_id: string;
  doc_name?: string;
  pages?: string;
  department?: string;
}

export interface ImageEntry {
  page: number;
  index: number;
  sop_id: string;
  url: string;
  width: number;
  height: number;
}

export type ImageMap = Record<string, ImageEntry>;
