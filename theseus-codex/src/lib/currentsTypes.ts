export type IsoDateString = string;

export interface PublicCurrentEvent {
  id: string;
  source: string;
  external_id: string;
  author_handle: string | null;
  text: string;
  url: string | null;
  captured_at: IsoDateString;
  observed_at: IsoDateString;
  topic_hint: string | null;
}

export interface PublicCitation {
  id: string;
  source_kind: string;
  source_id: string;
  quoted_span: string;
  retrieval_score: number;
  is_revoked: boolean;
}

export interface PublicOpinion {
  id: string;
  organization_id: string;
  event_id: string;
  stance: string;
  confidence: number;
  headline: string;
  body_markdown: string;
  uncertainty_notes: string[];
  topic_hint: string | null;
  model_name: string;
  generated_at: IsoDateString;
  revoked_at: IsoDateString | null;
  abstention_reason: string | null;
  revoked_sources_count: number;
  event: PublicCurrentEvent | null;
  citations: PublicCitation[];
}

export interface PublicSource {
  id: string;
  opinion_id: string;
  source_kind: string;
  source_id: string;
  source_text: string;
  quoted_span: string;
  retrieval_score: number;
  is_revoked: boolean;
  revoked_reason: string | null;
  canonical_path: string | null;
}

export interface PublicFollowupMessage {
  id: string;
  role: string;
  content: string;
  citations: Record<string, unknown>[];
  created_at: IsoDateString;
}
