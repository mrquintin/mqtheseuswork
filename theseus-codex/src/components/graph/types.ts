export type NodeKind =
  | "CONCEPT"
  | "PERSON"
  | "SOURCE"
  | "TOPIC"
  | "PRINCIPLE"
  | "ALGORITHM"
  | "MEMO";

export type EdgeKind =
  | "DERIVED_FROM"
  | "INVOKES"
  | "CONTRADICTS"
  | "SUPPORTS"
  | "APPLIES_TO"
  | "PREDICTS"
  | "CITES"
  | "MENTIONS";

export type GraphNode = {
  id: string;
  kind: NodeKind;
  ref: string;
  label: string;
  attrs: Record<string, unknown>;
  provenance: string;
};

export type GraphEdge = {
  id: string;
  src: string;
  dst: string;
  kind: EdgeKind;
  weight: number;
  attrs: Record<string, unknown>;
};

export type GraphSnapshotMeta = {
  id: string;
  snapshot_at: string | null;
  version: string;
  node_count: number;
  edge_count: number;
};

export type GraphResponse = {
  ok: boolean;
  organization_id?: string;
  snapshot: GraphSnapshotMeta | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type SourceCitation = {
  ref: string;
  kind: string;
  title: string;
  excerpt: string;
};

export type EdgeReasoning = {
  question_implied: string;
  short_answer: string;
  reasoning_chain: string[];
  citations: SourceCitation[];
  confidence_low: number;
  confidence_high: number;
  generated_at: string;
  weak_connection: boolean;
};
