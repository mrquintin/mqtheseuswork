import type { MqsRecord } from "@/lib/methodologyProfiles";
import { Pill } from "@/components/design";
import { color } from "@/lib/design/tokens";

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
    <Pill
      aria-label={`Methodology Quality Score ${pct}% — what this means`}
      className="public-mqs-pill"
      href="/methodology#mqs"
      tone="accent"
    >
      <span>MQS</span>
      <span style={{ color: color.parchment }}>{pct}%</span>
    </Pill>
  );
}
