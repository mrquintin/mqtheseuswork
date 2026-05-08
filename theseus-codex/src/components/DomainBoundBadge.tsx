"use client";

/**
 * DomainBoundBadge — surfaces a method's domain-bound verdict for a
 * single conclusion. Three statuses, three palettes:
 *
 *   in_bounds   green   — method is operating in its declared region
 *   edge_case   amber   — operating just outside the in-domain radius;
 *                         MQS caps domainSensitivity but we still ran
 *   out_of_bounds red    — refused; conclusion gated to MQS composite 0
 *
 * The badge is intentionally compact (chip-sized) so it can sit next
 * to a method name in a list. The hover tooltip carries the numeric
 * margin and the bound's reason string so a reviewer can audit the
 * verdict without leaving the page.
 */

import * as React from "react";

export type DomainBoundStatus = "in_bounds" | "edge_case" | "out_of_bounds";

export type DomainBoundVerdict = {
  status: DomainBoundStatus;
  /// Signed margin: positive when in-bounds, negative when out.
  margin: number;
  /// Free-form reason from the bound check (used as hover text).
  reason?: string;
  /// Pin to the AnchorRevision active at run time.
  anchorRevisionId?: string | null;
  matchedTags?: string[];
  embeddingModel?: string | null;
};

const STATUS_LABEL: Record<DomainBoundStatus, string> = {
  in_bounds: "in domain",
  edge_case: "edge",
  out_of_bounds: "out",
};

const STATUS_COLOR: Record<DomainBoundStatus, { fg: string; bg: string; border: string }> = {
  in_bounds: {
    fg: "#1f5c2c",
    bg: "rgba(122, 184, 122, 0.18)",
    border: "rgba(122, 184, 122, 0.55)",
  },
  edge_case: {
    fg: "#7a5210",
    bg: "rgba(212, 160, 23, 0.18)",
    border: "rgba(212, 160, 23, 0.55)",
  },
  out_of_bounds: {
    fg: "#7a1f17",
    bg: "rgba(192, 57, 43, 0.18)",
    border: "rgba(192, 57, 43, 0.55)",
  },
};

function formatMargin(margin: number): string {
  if (!Number.isFinite(margin)) return "—";
  const sign = margin >= 0 ? "+" : "";
  return `${sign}${margin.toFixed(3)}`;
}

function tooltipText(v: DomainBoundVerdict): string {
  const lines: string[] = [];
  lines.push(`status: ${v.status}`);
  lines.push(`margin: ${formatMargin(v.margin)}`);
  if (v.reason) lines.push(v.reason);
  if (v.matchedTags && v.matchedTags.length) {
    lines.push(`tags: ${v.matchedTags.join(", ")}`);
  }
  if (v.anchorRevisionId) lines.push(`anchors: ${v.anchorRevisionId}`);
  if (v.embeddingModel) lines.push(`model: ${v.embeddingModel}`);
  return lines.join("\n");
}

export type DomainBoundBadgeProps = {
  verdict: DomainBoundVerdict;
  /// When true, includes the numeric margin in the visible chip.
  showMargin?: boolean;
  /// Optional inline override.
  style?: React.CSSProperties;
};

export default function DomainBoundBadge({
  verdict,
  showMargin = false,
  style,
}: DomainBoundBadgeProps) {
  const palette = STATUS_COLOR[verdict.status];
  const label = STATUS_LABEL[verdict.status];

  return (
    <span
      role="status"
      aria-label={`Domain bound: ${label}`}
      title={tooltipText(verdict)}
      data-status={verdict.status}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        borderRadius: 12,
        border: `1px solid ${palette.border}`,
        backgroundColor: palette.bg,
        color: palette.fg,
        fontSize: "0.7rem",
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        fontFamily:
          "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        whiteSpace: "nowrap",
        ...(style ?? {}),
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          backgroundColor: palette.fg,
          opacity: 0.85,
        }}
      />
      {label}
      {showMargin ? (
        <span style={{ opacity: 0.7, fontWeight: 400 }}>
          {formatMargin(verdict.margin)}
        </span>
      ) : null}
    </span>
  );
}
