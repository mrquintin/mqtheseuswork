export interface CheckResultOut {
  check_name: string;
  passed: boolean;
  detail: string;
  ledger_entry_id: string | null;
}

export interface RigorVerdictOut {
  verdict: string;
  checks_run: CheckResultOut[];
  conditions: string[];
  reviewed_by: Record<string, string>[];
  ledger_entry_id: string;
}

export interface RigorSubmissionOut {
  submission_id: string;
  kind: string;
  payload_ref: string;
  author: Record<string, string>;
  intended_venue: string;
}

export interface RigorResponse {
  submissions: RigorSubmissionOut[];
  verdicts: RigorVerdictOut[];
}

export interface FounderOverrideOut {
  override_id: string;
  submission_id: string;
  founder_id: string;
  overridden_checks: string[];
  justification: string;
  ledger_entry_id: string;
}

export interface OverridesResponse {
  overrides: FounderOverrideOut[];
}

export interface DecayPolicyOut {
  policy_id: string;
  policy_kind: string;
  params: Record<string, unknown>;
}

export interface RevalidationOut {
  object_id: string;
  outcome: string;
  prior_tier: string;
  new_tier: string;
  ledger_entry_id: string;
}

export interface DecayResponse {
  policies: DecayPolicyOut[];
  recent_revalidations: RevalidationOut[];
}
