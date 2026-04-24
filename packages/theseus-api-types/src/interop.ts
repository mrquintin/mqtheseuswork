export interface MIPSummary {
  name: string;
  version: string;
  license: string;
  content_hash: string;
  method_count: number;
}

export interface InteropListResponse {
  packages: MIPSummary[];
}

export interface MethodRefOut {
  name: string;
  version: string;
}

export interface MIPDetailResponse {
  name: string;
  version: string;
  methods: MethodRefOut[];
  cascade_edge_schema: Record<string, unknown>;
  gate_check_schema: Record<string, unknown>;
  license: string;
  content_hash: string;
  signature: string;
}
