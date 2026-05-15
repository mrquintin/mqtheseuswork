import Link from "next/link";

import {
  formatEdgeBadgeLabel,
  forecastWorkspaceHref,
  type EdgeReport,
} from "@/lib/edgeApi";
import { Card } from "@/components/design";
import { color, fontSize, space } from "@/lib/design/tokens";

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

export default function EdgeBadge({ edge, opinionHeadline }: EdgeBadgeProps) {
  const label = formatEdgeBadgeLabel(edge);
  const workspaceHref = forecastWorkspaceHref(edge);

  const ctaText = edge.suggested_stake_usd
    ? `Open forecast workspace · suggested $${edge.suggested_stake_usd.toFixed(2)} on ${edge.side}`
    : "Open forecast workspace";

  return (
    <Card
      as="aside"
      tone="accent"
      padding="sm"
      aria-label={
        opinionHeadline
          ? `Edge available for ${opinionHeadline}`
          : "Edge available"
      }
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "space-between",
        gap: space.md,
        margin: `${space.md} 0`,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: fontSize.small,
      }}
    >
      <div>
        <div
          style={{
            color: color.currentsParchment,
            letterSpacing: "0.02em",
            lineHeight: 1.45,
          }}
        >
          {label}
        </div>
        {edge.low_liquidity ? (
          <div
            style={{
              color: color.currentsAmber,
              fontSize: fontSize.meta,
              marginTop: space.xs,
            }}
          >
            Low liquidity — surfacing edge only; size suggestion withheld.
          </div>
        ) : null}
      </div>
      <Link
        href={workspaceHref}
        style={{
          color: color.currentsGold,
          textDecoration: "none",
          whiteSpace: "nowrap",
        }}
      >
        {ctaText} →
      </Link>
    </Card>
  );
}
