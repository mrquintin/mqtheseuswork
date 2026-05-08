// Helpers for rendering the source-credibility ledger in the UI.
//
// The numbers here mirror noosphere/noosphere/literature/source_priors.py
// — when the Python side is the source of truth, this file's role is
// only display formatting and tiny derivations (mean from alpha/beta,
// label for a 0–100 strip). The credibility payload itself is computed
// server-side and shipped to the front end via display_payload().

export const MIN_UPDATES_FOR_CONFIDENT_DISPLAY = 5;

export interface SourceCredibilityPayload {
  source_id: string;
  source_type: string;
  alpha: number;
  beta: number;
  /// Posterior mean in [0, 1].
  mean: number;
  /// Posterior mean × 100, rounded to one decimal.
  score_100: number;
  /// Total updates observed (confirmations + failures).
  n_updates: number;
  n_confirmations: number;
  n_failures: number;
  /// True once n_updates >= MIN_UPDATES_FOR_CONFIDENT_DISPLAY.
  confident: boolean;
  min_updates_for_confidence: number;
  last_updated_at: string | null;
}

const SCORE_BANDS: Array<{ max: number; label: string; color: string }> = [
  { max: 25, label: "very low", color: "#5b1414" },
  { max: 45, label: "low", color: "#5b3414" },
  { max: 60, label: "neutral", color: "#3a3a3a" },
  { max: 75, label: "decent", color: "#244a24" },
  { max: 100.0001, label: "strong", color: "#1f5b1f" },
];

export function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

export function meanFromBeta(alpha: number, beta: number): number {
  if (!Number.isFinite(alpha) || !Number.isFinite(beta)) return 0;
  const total = alpha + beta;
  if (total <= 0) return 0;
  return clamp01(alpha / total);
}

export function score100From(payload: SourceCredibilityPayload): number {
  if (Number.isFinite(payload.score_100)) return payload.score_100;
  return Math.round(meanFromBeta(payload.alpha, payload.beta) * 1000) / 10;
}

export function scoreBandLabel(score100: number): string {
  for (const band of SCORE_BANDS) {
    if (score100 < band.max) return band.label;
  }
  return SCORE_BANDS[SCORE_BANDS.length - 1].label;
}

export function scoreBandColor(score100: number): string {
  for (const band of SCORE_BANDS) {
    if (score100 < band.max) return band.color;
  }
  return SCORE_BANDS[SCORE_BANDS.length - 1].color;
}

export function summaryLine(payload: SourceCredibilityPayload): string {
  const parts: string[] = [];
  parts.push(`${payload.n_updates} updates`);
  parts.push(`${payload.n_confirmations}+ confirmations`);
  parts.push(`${payload.n_failures}- failures`);
  return parts.join(" · ");
}

export function unconfidentCaveat(payload: SourceCredibilityPayload): string {
  return `n=${payload.n_updates} updates (need ${
    payload.min_updates_for_confidence
  } before treating this as a confident credibility number)`;
}

/// Friendly display name for a source-type slug from the Python side.
export function sourceTypeLabel(slug: string): string {
  switch (slug) {
    case "peer_reviewed_paper":
      return "Peer-reviewed paper";
    case "conference_paper":
      return "Conference paper";
    case "preprint":
      return "Preprint";
    case "government_data":
      return "Government data";
    case "firm_podcast":
      return "Firm podcast";
    case "firm_conclusion":
      return "Firm conclusion";
    case "news_major":
      return "News (major)";
    case "news_tabloid":
      return "News (tabloid)";
    case "x_post":
      return "X post";
    case "blog_self_pub":
      return "Self-published blog";
    case "personal_correspondence":
      return "Personal correspondence";
    default:
      return "Unknown source type";
  }
}

/// Coerces a partial server payload into the full shape, filling in
/// derived fields if they're missing. Defensive — we never want a
/// missing field to crash the popover render.
export function normalizeCredibilityPayload(
  raw: Partial<SourceCredibilityPayload> | null | undefined,
): SourceCredibilityPayload | null {
  if (!raw) return null;
  if (typeof raw.source_id !== "string" || !raw.source_id) return null;
  const alpha = Number(raw.alpha ?? 0);
  const beta = Number(raw.beta ?? 0);
  const mean = Number.isFinite(raw.mean) ? Number(raw.mean) : meanFromBeta(alpha, beta);
  const score_100 = Number.isFinite(raw.score_100)
    ? Number(raw.score_100)
    : Math.round(mean * 1000) / 10;
  const n_updates = Number.isInteger(raw.n_updates) ? Number(raw.n_updates) : 0;
  const n_confirmations = Number.isInteger(raw.n_confirmations)
    ? Number(raw.n_confirmations)
    : 0;
  const n_failures = Number.isInteger(raw.n_failures) ? Number(raw.n_failures) : 0;
  const min_updates_for_confidence = Number.isInteger(raw.min_updates_for_confidence)
    ? Number(raw.min_updates_for_confidence)
    : MIN_UPDATES_FOR_CONFIDENT_DISPLAY;
  const confident =
    typeof raw.confident === "boolean"
      ? raw.confident
      : n_updates >= min_updates_for_confidence;
  return {
    source_id: raw.source_id,
    source_type: typeof raw.source_type === "string" ? raw.source_type : "unknown",
    alpha,
    beta,
    mean: clamp01(mean),
    score_100,
    n_updates,
    n_confirmations,
    n_failures,
    confident,
    min_updates_for_confidence,
    last_updated_at:
      typeof raw.last_updated_at === "string" ? raw.last_updated_at : null,
  };
}
