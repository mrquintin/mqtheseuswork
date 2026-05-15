import type { CSSProperties } from "react";
import type { QueueHealth, QueueHealthStatus } from "@/lib/attention";
import { color, fontSize, radius, space, tracking } from "@/lib/design/tokens";

/**
 * Queue-health strip. Each underlying queue gets one chip showing
 * whether its producer emits items faster than the founder triages
 * them. A queue that is "accumulating" has been under-resourced or
 * needs its producer throttled; "draining" is being cleared faster
 * than it fills; "steady" is keeping pace.
 *
 * Presentational only — no interactivity, so it renders fine inside the
 * client `AttentionQueue` without its own `"use client"` boundary. The
 * `QueueHealth[]` is computed server-side by `computeQueueHealth`.
 */

const STATUS_META: Record<
  QueueHealthStatus,
  { label: string; accent: string; glyph: string }
> = {
  accumulating: { label: "accumulating", accent: color.ember, glyph: "▲" },
  steady: { label: "steady", accent: color.parchmentDim, glyph: "■" },
  draining: { label: "draining", accent: color.success, glyph: "▼" },
};

// Worst-first: an accumulating queue should be impossible to miss.
const STATUS_ORDER: Record<QueueHealthStatus, number> = {
  accumulating: 0,
  steady: 1,
  draining: 2,
};

function formatRate(rate: number): string {
  if (!Number.isFinite(rate)) return "∞";
  if (rate === 0) return "0";
  if (rate < 1) return rate.toFixed(1);
  return rate.toFixed(rate < 10 ? 1 : 0);
}

const kickerStyle: CSSProperties = {
  color: color.parchmentDim,
  fontSize: fontSize.micro,
  letterSpacing: tracking.widest,
  textTransform: "uppercase",
};

export default function QueueHealthIndicator({
  health,
}: {
  health: QueueHealth[];
}) {
  if (health.length === 0) return null;

  const ordered = [...health].sort(
    (a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
      b.openCount - a.openCount ||
      a.queueLabel.localeCompare(b.queueLabel),
  );

  return (
    <div
      data-testid="queue-health"
      aria-label="Queue health"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: space.sm,
        marginBottom: space.lg,
      }}
    >
      <span className="mono" style={kickerStyle}>
        Queue health · arrivals vs triage (7d)
      </span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: space.sm }}>
        {ordered.map((queue) => {
          const meta = STATUS_META[queue.status];
          return (
            <span
              key={queue.queue}
              data-testid="queue-health-chip"
              data-queue={queue.queue}
              data-status={queue.status}
              title={
                `${queue.queueLabel}: ${formatRate(queue.arrivalRate)}/day in vs ` +
                `${formatRate(queue.triageRate)}/day triaged · ${queue.openCount} open · ` +
                `${meta.label}`
              }
              style={{
                alignItems: "center",
                border: `1px solid ${meta.accent}`,
                borderRadius: radius.pill,
                color: color.parchment,
                display: "inline-flex",
                fontSize: fontSize.caption,
                gap: space.xs,
                padding: `${space.xs} ${space.md}`,
              }}
            >
              <span aria-hidden="true" style={{ color: meta.accent }}>
                {meta.glyph}
              </span>
              {queue.queueLabel}
              <span className="mono" style={{ color: color.parchmentDim }}>
                {formatRate(queue.arrivalRate)}↑ / {formatRate(queue.triageRate)}↓
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
