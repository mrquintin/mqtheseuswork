/**
 * Round-17 prompt 44 — open-critique pilot configuration.
 *
 * The pilot opens the existing `Challenge this conclusion` channel to a
 * named set of outside reviewers via per-reviewer pre-shared links.
 * Each link carries a single-purpose token that resolves to a reviewer
 * slug; the submit route stamps the resulting `CritiqueSubmission` row
 * with the pilot tag and the reviewer slug. During the pilot window,
 * the founder queue routes pilot rows to the top of the queue.
 *
 * No token here grants any side-effect that needs CSRF or session
 * protection — the token only stamps two metadata fields on a
 * critique that the public form would otherwise have produced. The
 * standard rate limit and validation still apply.
 *
 * Reviewer tokens are configured via the
 * `THESEUS_CRITIQUE_PILOT_REVIEWERS` env var as a comma-separated list
 * of `slug:token` pairs. The pilot window is configured via
 * `THESEUS_CRITIQUE_PILOT_WINDOW` as `<startISO>..<endISO>`.
 *
 * Defaults are intentionally empty — the pilot is dark until the
 * founder switches it on.
 */

export const PILOT_TAG = "round17_pilot_2026Q2";

export type PilotReviewer = {
  slug: string;
  token: string;
};

export type PilotWindow = {
  /** ISO-8601 inclusive start, or null if no window configured. */
  startsAt: Date | null;
  /** ISO-8601 inclusive end, or null if no window configured. */
  endsAt: Date | null;
};

export type PilotConfig = {
  tag: string;
  window: PilotWindow;
  reviewers: PilotReviewer[];
};

/**
 * Parse the per-reviewer token list. Format:
 *   "slug-a:token-a,slug-b:token-b"
 * Whitespace is tolerated; blank entries are skipped.
 */
export function parseReviewers(raw: string | undefined): PilotReviewer[] {
  if (!raw) return [];
  const out: PilotReviewer[] = [];
  for (const part of raw.split(",")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const colon = trimmed.indexOf(":");
    if (colon <= 0) continue;
    const slug = trimmed.slice(0, colon).trim();
    const token = trimmed.slice(colon + 1).trim();
    if (!slug || !token) continue;
    out.push({ slug, token });
  }
  return out;
}

/**
 * Parse the pilot window. Format: "<startISO>..<endISO>". Either side
 * may be empty (open-ended). A missing or unparseable window returns
 * a fully open window — the pilot is considered active whenever any
 * reviewer is configured.
 */
export function parseWindow(raw: string | undefined): PilotWindow {
  if (!raw) return { startsAt: null, endsAt: null };
  const sep = raw.indexOf("..");
  if (sep < 0) return { startsAt: null, endsAt: null };
  const startStr = raw.slice(0, sep).trim();
  const endStr = raw.slice(sep + 2).trim();
  const startsAt = startStr ? new Date(startStr) : null;
  const endsAt = endStr ? new Date(endStr) : null;
  return {
    startsAt: startsAt && !Number.isNaN(startsAt.getTime()) ? startsAt : null,
    endsAt: endsAt && !Number.isNaN(endsAt.getTime()) ? endsAt : null,
  };
}

/** Build the runtime pilot config from the current environment. */
export function loadPilotConfig(env: NodeJS.ProcessEnv = process.env): PilotConfig {
  return {
    tag: PILOT_TAG,
    window: parseWindow(env.THESEUS_CRITIQUE_PILOT_WINDOW),
    reviewers: parseReviewers(env.THESEUS_CRITIQUE_PILOT_REVIEWERS),
  };
}

/**
 * Resolve a per-reviewer token to its reviewer slug. Returns null if
 * the token does not match any configured reviewer — callers MUST
 * treat the submission as non-pilot in that case (no silent
 * promotion).
 */
export function resolveReviewerSlug(
  config: PilotConfig,
  token: string | null | undefined,
): string | null {
  if (!token) return null;
  const t = token.trim();
  if (!t) return null;
  for (const r of config.reviewers) {
    if (r.token === t) return r.slug;
  }
  return null;
}

/**
 * Is the pilot window currently open? An empty window (both sides
 * null) is treated as open so the pilot toggles by reviewer
 * configuration alone, not by window editing in the common case.
 */
export function isPilotWindowOpen(window: PilotWindow, now: Date = new Date()): boolean {
  if (window.startsAt && now < window.startsAt) return false;
  if (window.endsAt && now > window.endsAt) return false;
  return true;
}

/**
 * The pilot must not cherry-pick favorable findings. Every pilot
 * submission, including rejected ones, is part of the pilot record.
 * Helper used by the debrief to enumerate "what came in" without
 * filtering by status.
 */
export type PilotSubmissionLite = {
  status: string;
  severityLabel: string;
  pilotReviewerSlug: string;
  hallOfFameConsent: boolean;
};

export function pilotAcceptRate(rows: PilotSubmissionLite[]): number {
  if (rows.length === 0) return 0;
  let accepted = 0;
  for (const r of rows) {
    if (r.status === "accepted") accepted += 1;
  }
  return accepted / rows.length;
}

export function pilotSeverityDistribution(
  rows: PilotSubmissionLite[],
): Record<"low" | "medium" | "high" | "unscored", number> {
  const out = { low: 0, medium: 0, high: 0, unscored: 0 };
  for (const r of rows) {
    if (r.status !== "accepted") continue;
    if (r.severityLabel === "low") out.low += 1;
    else if (r.severityLabel === "medium") out.medium += 1;
    else if (r.severityLabel === "high") out.high += 1;
    else out.unscored += 1;
  }
  return out;
}
