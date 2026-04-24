// Wire-format mirror of current_events_api/current_events_api/schemas.py.
// Field names are snake_case to match the FastAPI payloads verbatim.

export type Stance = "agrees" | "disagrees" | "complicates" | "insufficient";

export interface PublicCitation {
  source_kind: "conclusion" | "claim";
  source_id: string;
  quoted_span: string;
  relevance_score: number;
}

export interface PublicOpinion {
  id: string;
  event_id: string;
  event_source_url: string;
  event_author_handle: string;
  event_captured_at: string; // ISO 8601
  topic_hint: string | null;
  stance: Stance;
  confidence: number;
  headline: string;
  body_markdown: string;
  uncertainty_notes: string[];
  generated_at: string;
  citations: PublicCitation[];
  revoked: boolean;
}

export interface PublicSource {
  source_kind: "conclusion" | "claim";
  source_id: string;
  full_text: string;
  topic_hint: string | null;
  origin: string | null;
  permalink: string | null;
}

export interface PublicFollowupMessage {
  id: string;
  role: "user" | "assistant" | "system";
  created_at: string;
  content: string;
  citations: PublicCitation[];
  refused: boolean;
  refusal_reason: string | null;
}

export interface PaginatedOpinions {
  items: PublicOpinion[];
  next_cursor: string | null;
}
