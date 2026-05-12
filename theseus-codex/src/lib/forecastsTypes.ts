export type IsoDateString = string;

export interface PublicMarket {
  id: string;
  organization_id: string;
  source: string;
  external_id: string;
  title: string;
  description: string | null;
  resolution_criteria: string | null;
  category: string | null;
  current_yes_price: number | null;
  current_no_price: number | null;
  volume: number | null;
  open_time: IsoDateString | null;
  close_time: IsoDateString | null;
  resolved_at: IsoDateString | null;
  resolved_outcome: string | null;
  raw_payload: Record<string, unknown>;
  status: string;
  created_at: IsoDateString;
  updated_at: IsoDateString;
}

export interface PublicForecastCitation {
  id: string;
  prediction_id: string;
  source_type: string;
  source_id: string;
  quoted_span: string;
  support_label: string;
  retrieval_score: number | null;
  is_revoked: boolean;
}

export interface PublicResolution {
  id: string;
  prediction_id: string;
  market_outcome: string;
  brier_score: number | null;
  log_loss: number | null;
  calibration_bucket: number | null;
  resolved_at: IsoDateString;
  justification: string;
  created_at: IsoDateString;
}

export interface PublicForecast {
  id: string;
  market_id: string;
  organization_id: string;
  probability_yes: number | null;
  confidence_low: number | null;
  confidence_high: number | null;
  headline: string;
  reasoning: string;
  status: string;
  abstention_reason: string | null;
  topic_hint: string | null;
  model_name: string;
  live_authorized_at: IsoDateString | null;
  created_at: IsoDateString;
  updated_at: IsoDateString;
  revoked_sources_count: number;
  market: PublicMarket | null;
  citations: PublicForecastCitation[];
  resolution: PublicResolution | null;
}

export interface PublicForecastSource {
  id: string;
  prediction_id: string;
  source_type: string;
  source_id: string;
  source_text: string;
  quoted_span: string;
  support_label: string;
  retrieval_score: number | null;
  is_revoked: boolean;
  revoked_reason: string | null;
  canonical_path: string | null;
}

export interface PublicBet {
  id: string;
  prediction_id: string;
  mode: string;
  exchange: string;
  side: string;
  stake_usd: number;
  entry_price: number;
  exit_price: number | null;
  status: string;
  settlement_pnl_usd: number | null;
  created_at: IsoDateString;
  settled_at: IsoDateString | null;
}

export interface PublicFollowupMessage {
  id: string;
  role: string;
  content: string;
  citations: Record<string, unknown>[];
  created_at: IsoDateString;
}

export interface PortfolioPoint {
  ts: IsoDateString;
  paper_balance_usd: number;
  paper_pnl_usd: number;
}

export interface CalibrationBucket {
  bucket: number;
  prediction_count: number;
  resolved_count: number;
  mean_probability_yes: number | null;
  empirical_yes_rate: number | null;
  mean_brier: number | null;
}

export interface PortfolioSummary {
  organization_id: string;
  paper_balance_usd: number;
  paper_pnl_curve: PortfolioPoint[];
  calibration: CalibrationBucket[];
  mean_brier_90d: number | null;
  total_bets: number;
  kill_switch_engaged: boolean;
  kill_switch_reason: string | null;
  updated_at: IsoDateString | null;
}

export interface OperatorBet extends PublicBet {
  organization_id: string;
  external_order_id: string | null;
  client_order_id: string | null;
  live_authorized_at: IsoDateString | null;
  confirmed_at: IsoDateString | null;
  submitted_at: IsoDateString | null;
}

export interface OperatorKillSwitchState {
  organization_id: string;
  kill_switch_engaged: boolean;
  kill_switch_reason: string | null;
  updated_at: IsoDateString | null;
}

export interface ForecastListResponse {
  items: PublicForecast[];
}

export interface MarketListResponse {
  items: PublicMarket[];
}

export interface CalibrationResponse {
  items: CalibrationBucket[];
}

export interface BetsResponse {
  items: PublicBet[];
  next_offset: number | null;
}

export interface OperatorLiveBetsResponse {
  items: OperatorBet[];
  next_offset: number | null;
}

export interface OperatorEnvVarStatus {
  name: string;
  present: boolean;
  alternate?: string;
}

export interface OperatorExchangeSetup {
  configured: boolean;
  required_env_vars: OperatorEnvVarStatus[];
  optional_env_vars: OperatorEnvVarStatus[];
}

export interface OperatorRiskLimits {
  max_stake_usd: number;
  max_daily_loss_usd: number;
  kill_switch_auto_threshold_usd: number | null;
  max_stake_configured: boolean;
  max_daily_loss_configured: boolean;
}

export interface OperatorSchedulerStatus {
  status_path: string;
  present: boolean;
  fresh: boolean;
  age_seconds: number | null;
  max_age_seconds: number;
  last_ingest_ts: string | null;
  last_generate_ts: string | null;
  last_live_submission_ts: string | null;
  error: string | null;
}

export interface OperatorKillSwitchStatus {
  engaged: boolean;
  reason: string | null;
  updated_at: string | null;
  daily_loss_usd: number;
  live_balance_usd: number;
}

export interface OperatorSetupReadiness {
  monitoring_active: boolean;
  ready_for_live_candidates: boolean;
  ready_for_live_orders: boolean;
  blockers: string[];
}

export type DecisionAction =
  | "ABSTAIN"
  | "WATCH"
  | "PAPER_TRADE"
  | "LIVE_CANDIDATE"
  | "REDUCE"
  | "EXIT"
  | "HEDGE";

export interface DecisionMetric {
  name: string;
  value: number;
  rangeLow: number;
  rangeHigh: number;
  method: string;
  lowConfidence: boolean;
  detail: string;
}

export interface DecisionRule {
  name: string;
  kind: "veto" | "threshold" | "bucket" | "combiner" | string;
  fired: boolean;
  passed: boolean;
  detail: string;
}

export type FrameVerdict =
  | "SUPPORT"
  | "WATCH"
  | "ABSTAIN"
  | "REDUCE"
  | "EXIT"
  | "HEDGE"
  | "HARD_STOP";

export interface DecisionFrame {
  name: string;
  verdict: FrameVerdict;
  assumptionsStable: boolean;
  confidence: number;
  sidePreference: "YES" | "NO" | null;
  metricsConsulted: string[];
  reasons: string[];
  failureModes: string[];
  detail: string;
}

export interface DecisionSynthesis {
  action: FrameVerdict | string;
  side: "YES" | "NO" | null;
  agreement: number;
  supportingFrames: string[];
  blockingFrames: string[];
  abstainingFrames: string[];
  watchFrames: string[];
  hardStopFrames: string[];
  unstableFrames: string[];
  reasons: string[];
  synthesisVersion: string;
}

export interface TransferRecommendation {
  principleId: string;
  canonicalStatement: string;
  stance: string;
  confidence: number;
  closestCaseIds: string[];
  reasons: string[];
}

export interface AnalogicalTransferReport {
  queryCaseId: string;
  bestPrincipleId: string | null;
  bestStance: string;
  recommendations: TransferRecommendation[];
  traceVersion: string;
}

export interface DecisionTrace {
  action: DecisionAction;
  side: "YES" | "NO" | null;
  confidence: number;
  stakeRecommendationUsd: number | null;
  metrics: DecisionMetric[];
  rules: DecisionRule[];
  reasons: string[];
  traceVersion: string;
  firmProbabilityYes: number | null;
  marketYesPrice: number | null;
  edge: number | null;
  rationale: string | null;
  frames: DecisionFrame[];
  synthesis: DecisionSynthesis | null;
  analogicalTransfer: AnalogicalTransferReport | null;
}

export const DECISION_ACTIONS: DecisionAction[] = [
  "ABSTAIN",
  "WATCH",
  "PAPER_TRADE",
  "LIVE_CANDIDATE",
  "REDUCE",
  "EXIT",
  "HEDGE",
];

export const DECISION_ACTION_BLURBS: Record<DecisionAction, string> = {
  ABSTAIN: "The algorithm refuses to take a view on this market.",
  WATCH: "Surface to operator; do not stake.",
  PAPER_TRADE: "Paper fill recorded; live capital untouched.",
  LIVE_CANDIDATE: "Eligible for operator confirmation under safety gates.",
  REDUCE: "Existing position: cut size by a named fraction.",
  EXIT: "Existing position: close out.",
  HEDGE: "Open offsetting exposure named in the trace.",
};

export const METRIC_DEFINITIONS: Record<string, string> = {
  market_mispricing_edge:
    "Signed: firm_yes_probability − market_yes_price. Drives the side and the edge-magnitude bucket.",
  calibration_adjusted_confidence:
    "Confidence (1 − interval width) mapped through per-domain calibration when available.",
  source_domain_locality:
    "Fraction of cited sources whose domain overlaps the market category.",
  contradiction_pressure:
    "Fraction of citations whose support_label is CONTRARY. High → veto.",
  liquidity_cost_feasibility:
    "1 − fraction of stake consumed by spread/depth/fees at the venue.",
  temporal_decay_pressure:
    "Weighted age of load-bearing citations vs market time-to-resolution.",
  thesis_resonance:
    "Degree to which the resolved-YES world is entailed by the active principles (planned).",
  premise_support_density:
    "Fraction of premises resolving to verbatim-quoted, surviving citations (planned).",
  causal_chain_completeness:
    "Fraction of cause→effect edges supported by direct/indirect citations (planned).",
  adversarial_fragility:
    "Drop in thesis_resonance under adversarial perturbations (planned).",
};

export interface OperatorSetupStatus {
  organization_id: string;
  trading_mode: "PAPER_ONLY" | "LIVE_DISABLED_NO_CREDENTIALS" | "LIVE_ENABLED_AWAITING_AUTHORIZATION" | string;
  live_trading_enabled: boolean;
  exchanges: {
    polymarket: OperatorExchangeSetup;
    kalshi: OperatorExchangeSetup;
  };
  risk_limits: OperatorRiskLimits;
  scheduler: OperatorSchedulerStatus;
  kill_switch: OperatorKillSwitchStatus;
  readiness: OperatorSetupReadiness;
  checked_at: string;
}
