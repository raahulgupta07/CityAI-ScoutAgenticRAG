export interface Stats {
  total_indexed: number;
  errors: number;
  departments: number;
  total_pages: number;
  pages_with_images: number;
}

export interface SOPSummary {
  sop_id: string;
  doc_name: string;
  doc_description: string;
  department: string;
  page_count: number;
  total_extracted_images?: number;
}

export interface SOPDetail extends SOPSummary {
  doc_id: string;
  file_path: string;
  category_id: string;
  pages_with_images: number[];
  extracted_images: Record<string, ImageEntry[]>;
  search_keywords: string[];
  qa_pairs: string[];
  compliance: {
    quality_score: number;
    is_expired: boolean;
    missing_sections: string[];
    recommendations: string[];
  } | null;
  page_contents: Array<{
    page_number: number;
    text_content: string;
    vision_content: string;
    enhanced_content: string;
    is_enhanced: boolean;
  }>;
}

export interface ImageEntry {
  index: number;
  path: string;
  url: string;
  width: number;
  height: number;
}

export interface Source {
  sop_id: string;
  doc_name: string;
  pages: string;
  department: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  images?: Record<string, any>;
  sources?: Source[];
  model?: string;
}

export interface AppSettings {
  llm: {
    provider: string;
    api_key: string;
    base_url: string;
    index_model: string;
    router_model: string;
    retrieve_model: string;
    answer_model: string;
  };
  widget: {
    title: string;
    primary_color: string;
    logo_url: string;
    welcome_message: string;
    max_images: number;
    allowed_domains: string[];
  };
}
