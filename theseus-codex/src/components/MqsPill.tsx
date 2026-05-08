import Link from "next/link";

import type { MqsRecord } from "@/lib/methodologyProfiles";

/**
 * Public composite-only pill. No evidence, no sub-scores — by design. Readers
 * who want the full breakdown follow the link to the methodology page.
 *
 * Render decisions about freshness and whether the conclusion is published
 * happen upstream; this component just renders.
 */
export default function MqsPill({ mqs }: { mqs: MqsRecord }) {
  const pct = Math.round(Math.max(0, Math.min(1, mqs.composite)) * 100);

  return (
    <Link
      aria-label={`Methodology Quality Score ${pct}% — what this means`}
      className="mono public-mqs-pill"
      href="/methodology#mqs"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.25rem 0.65rem",
        border: "1px solid var(--gold-dim)",
        borderRadius: 999,
        textDecoration: "none",
        color: "var(--gold)",
        fontSize: "0.65rem",
        letterSpacing: "0.18em",
        textTransform: "uppercase",
      }}
    >
      <span>MQS</span>
      <span style={{ color: "var(--parchment)" }}>{pct}%</span>
    </Link>
  );
}
