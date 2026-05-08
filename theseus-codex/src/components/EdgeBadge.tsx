import Link from "next/link";

import {
  formatEdgeBadgeLabel,
  forecastWorkspaceHref,
  type EdgeReport,
} from "@/lib/edgeApi";

/**
 * Founder-only badge surfacing a Currents opinion ↔ market edge.
 *
 * Rendered exclusively from the ``/founder-currents`` route. Never imported
 * by the public Currents surfaces, by contract. The component itself does
 * not enforce that — the public page simply does not pass edge data.
 */

export interface EdgeBadgeProps {
  edge: EdgeReport;
  opinionHeadline?: string;
}

const wrapperStyle: React.CSSProperties = {
  background: "rgba(212, 160, 23, 0.08)",
  border: "1px solid var(--currents-gold, #d4a017)",
  borderRadius: "6px",
  display: "flex",
  flexWrap: "wrap",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.78rem",
  gap: "0.6rem",
  justifyContent: "space-between",
  margin: "0.6rem 0",
  padding: "0.6rem 0.75rem",
};

const labelStyle: React.CSSProperties = {
  color: "var(--currents-parchment, #e8e1d3)",
  letterSpacing: "0.02em",
  lineHeight: 1.45,
};

const ctaStyle: React.CSSProperties = {
  color: "var(--currents-gold, #d4a017)",
  textDecoration: "none",
  whiteSpace: "nowrap",
};

const lowLiquidityStyle: React.CSSProperties = {
  color: "var(--currents-amber, #c9881a)",
  fontSize: "0.72rem",
  marginTop: "0.25rem",
};

export default function EdgeBadge({ edge, opinionHeadline }: EdgeBadgeProps) {
  const label = formatEdgeBadgeLabel(edge);
  const workspaceHref = forecastWorkspaceHref(edge);

  const ctaText = edge.suggested_stake_usd
    ? `Open forecast workspace · suggested $${edge.suggested_stake_usd.toFixed(2)} on ${edge.side}`
    : "Open forecast workspace";

  return (
    <aside
      aria-label={
        opinionHeadline
          ? `Edge available for ${opinionHeadline}`
          : "Edge available"
      }
      style={wrapperStyle}
    >
      <div>
        <div style={labelStyle}>{label}</div>
        {edge.low_liquidity ? (
          <div style={lowLiquidityStyle}>
            Low liquidity — surfacing edge only; size suggestion withheld.
          </div>
        ) : null}
      </div>
      <Link href={workspaceHref} style={ctaStyle}>
        {ctaText} →
      </Link>
    </aside>
  );
}
