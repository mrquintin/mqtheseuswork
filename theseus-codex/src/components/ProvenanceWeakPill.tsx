"use client";

import type { CSSProperties } from "react";

export type ProvenanceWeakPillVariant = "marker" | "label";

interface ProvenanceWeakPillProps {
  /**
   * `marker` (default) — a compact amber pill sized to sit next to the
   * thin gutter bar, so a reader scanning the left margin can find the
   * firm's weakest sentences without reading each one.
   * `label` — the same signal spelled out as a "weak evidence" text
   * pill for the provenance panel header.
   */
  variant?: ProvenanceWeakPillVariant;
  /** Optional debug id used by tests to scope queries. */
  testId?: string;
}

const AMBER = "var(--currents-amber, #d69c3f)";
const AMBER_DEEP = "var(--currents-amber-deep, #6b4f23)";

const markerStyle: CSSProperties = {
  background: AMBER,
  borderRadius: "999px",
  display: "block",
  flex: "none",
  height: "5px",
  // A short pill, not a dot — wide enough to read as a deliberate
  // marker in the margin without crowding the 2px bar beside it.
  width: "11px",
};

const labelStyle: CSSProperties = {
  alignItems: "center",
  background: "rgba(214, 156, 63, 0.14)",
  border: `1px solid ${AMBER_DEEP}`,
  borderRadius: "999px",
  color: AMBER,
  display: "inline-flex",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.62rem",
  gap: "0.35rem",
  letterSpacing: "0.09em",
  lineHeight: 1,
  padding: "0.22rem 0.55rem",
  textTransform: "uppercase",
  whiteSpace: "nowrap",
};

/**
 * "Weak evidence" pill. The gutter renders the compact `marker`
 * variant on every sentence whose provenance falls below the firm's
 * publish-worthy threshold; the panel renders the `label` variant.
 *
 * The pill is a redundant *visual* channel — the textual "weak
 * evidence" wording always lives in the gutter button's aria-label and
 * the panel summary — so the marker carries `aria-hidden` and never
 * becomes the sole carrier of meaning.
 */
export default function ProvenanceWeakPill({
  variant = "marker",
  testId,
}: ProvenanceWeakPillProps) {
  if (variant === "marker") {
    return (
      <span
        aria-hidden="true"
        data-testid={testId ?? "provenance-weak-pill"}
        data-variant="marker"
        style={markerStyle}
        title="Weak evidence — below the firm's publish-worthy bar"
      />
    );
  }

  return (
    <span
      data-testid={testId ?? "provenance-weak-pill"}
      data-variant="label"
      style={labelStyle}
    >
      <span aria-hidden="true">●</span>
      weak evidence
    </span>
  );
}
