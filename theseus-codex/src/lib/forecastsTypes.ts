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
