export interface MethodSummary {
  method_id: string;
  name: string;
  version: string;
  method_type: string;
  status: string;
  description: string;
  owner: string;
  created_at: string;
}

export interface MethodsListResponse {
  methods: MethodSummary[];
}

export interface MethodDetailResponse {
  method_id: string;
  name: string;
  version: string;
  method_type: string;
  status: string;
  description: string;
  rationale: string;
  owner: string;
  nondeterministic: boolean;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  preconditions: string[];
  postconditions: string[];
  dependencies: string[][];
  created_at: string;
}

export interface MethodDocResponse {
  name: string;
  version: string;
  description: string;
  rationale: string;
  preconditions: string[];
  postconditions: string[];
}

export interface EvalCardResponse {
  name: string;
  version: string;
  method_type: string;
  nondeterministic: boolean;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  dependencies: string[][];
  status: string;
}
