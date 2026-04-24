/**
 * Canonical vocabulary for `Upload.status`.
 *
 * The four original values — `pending | processing | ingested | failed`
 * — are load-bearing strings from the init migration. Everything that
 * ever wrote to `Upload.status` (the POST /api/upload handler, the
 * trigger-processing dispatcher, every branch of
 * noosphere/codex_bridge.py, the library filter dropdown) agrees on
 * them. DO NOT rename.
 *
 * The two new values (`extracting`, `awaiting_ingest`) were added in
 * Wave 1 so founders can see which stage of the pipeline their upload
 * is in:
 *
 *   pending          → queued, the local noosphere runner hasn't
 *                      picked it up yet
 *   extracting       → transcribing audio / extracting PDF text; no
 *                      LLM calls in this stage
 *   awaiting_ingest  → text is ready, about to hand off to claim
 *                      extraction
 *   processing       → claim extraction in progress (may call the LLM)
 *   ingested         → conclusions written to the Codex
 *   failed           → see `errorMessage`; retryable from the dashboard
 *
 * The legacy `queued_offline` value (older self-hosted flow where no
 * GitHub Actions dispatch was configured) is intentionally NOT in the
 * list — it's equivalent to `pending` for display purposes and gets
 * treated as such via {@link normalizeStatus}.
 */

export const UPLOAD_STATUSES = [
  "pending",
  "extracting",
  "awaiting_ingest",
  "processing",
  "ingested",
  "failed",
] as const;
export type UploadStatus = (typeof UPLOAD_STATUSES)[number];

export const STATUS_LABEL: Record<UploadStatus, string> = {
  pending: "queued",
  extracting: "extracting text",
  awaiting_ingest: "awaiting ingest",
  processing: "extracting claims",
  ingested: "ingested",
  failed: "failed",
};

export const STATUS_COLOR: Record<UploadStatus, string> = {
  // Muted parchment — the row has arrived but the pipeline hasn't
  // touched it yet. Using a CSS var so the pill adapts to theme swaps.
  pending: "var(--parchment-dim, #8a8675)",
  // Amber family — active, non-terminal, all three stages share the
  // colour so the founder reads "the pipeline is working" without
  // tracking which specific stage we're in.
  extracting: "var(--amber, #c9944a)",
  awaiting_ingest: "var(--amber, #c9944a)",
  processing: "var(--amber, #c9944a)",
  // Moss green — terminal success.
  ingested: "#497a3d",
  // Ember red — terminal failure; matches the existing --ember token.
  failed: "var(--ember, #b33a2a)",
};

export const STATUS_TOOLTIP: Record<UploadStatus, string> = {
  pending: "Waiting for the local noosphere runner to pick this up.",
  extracting: "Transcribing audio or extracting PDF text. No LLM calls yet.",
  awaiting_ingest: "Text is ready; waiting for claim extraction to start.",
  processing: "Claim extraction in progress (may call the LLM).",
  ingested: "Conclusions have been written to your Codex.",
  failed: "Processing failed. See the error detail and retry.",
};

/**
 * Non-terminal statuses animate in the UI so the founder has a visible
 * "pipeline is alive" cue. Excludes `pending` because a row can sit in
 * `pending` for a while (GitHub Actions queue depth, local runner
 * cadence) and a pulse there would imply more activity than is
 * actually happening.
 */
export const PULSING_STATUSES: ReadonlySet<UploadStatus> = new Set<UploadStatus>([
  "extracting",
  "awaiting_ingest",
  "processing",
]);

export function isUploadStatus(s: string): s is UploadStatus {
  return (UPLOAD_STATUSES as readonly string[]).includes(s);
}

/**
 * Map legacy / unknown status strings to a known UploadStatus. Anything
 * not in the canonical list falls back to `pending` so the badge still
 * renders (the founder sees "queued" rather than a raw / blank pill).
 */
export function normalizeStatus(raw: string | null | undefined): UploadStatus {
  if (!raw) return "pending";
  if (isUploadStatus(raw)) return raw;
  if (raw === "queued_offline") return "pending";
  return "pending";
}
