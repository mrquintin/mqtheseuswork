export interface CascadeEdgeOut {
  edge_id: string;
  src: string;
  dst: string;
  relation: string;
  method_invocation_id: string;
  confidence: number;
  unresolved: boolean;
  established_at: string;
  retracted_at: string | null;
}

export interface ProvenanceResponse {
  conclusion_id: string;
  edges: CascadeEdgeOut[];
}

export interface CascadeResponse {
  conclusion_id: string;
  upstream: CascadeEdgeOut[];
  downstream: CascadeEdgeOut[];
}

export interface FindingOut {
  severity: string;
  category: string;
  detail: string;
  evidence: string[];
  suggested_action: string;
}

export interface ReviewReportOut {
  report_id: string;
  reviewer: string;
  conclusion_id: string;
  findings: FindingOut[];
  overall_verdict: string;
  confidence: number;
  completed_at: string;
  method_invocation_ids: string[];
}

export interface RebuttalOut {
  finding_id: string;
  form: string;
  rationale: string;
  attached_edit_ref: string | null;
}

export interface PeerReviewResponse {
  conclusion_id: string;
  reviews: ReviewReportOut[];
  rebuttals: RebuttalOut[];
}
