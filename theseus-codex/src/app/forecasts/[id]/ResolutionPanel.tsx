import type { CSSProperties } from "react";

import type {
  CalibrationBucket,
  PublicMarket,
  PublicResolution,
} from "@/lib/forecastsTypes";

interface ResolutionPanelProps {
  calibration?: CalibrationBucket[] | null;
  market: PublicMarket | null;
  resolution: PublicResolution | null;
}

const panelBaseStyle: CSSProperties = {
  border: "1px solid var(--forecasts-border)",
  borderRadius: "6px",
  marginTop: "1.2rem",
  padding: "1rem",
};

const metaStyle: CSSProperties = {
  color: "var(--forecasts-parchment-dim)",
  display: "flex",
  flexWrap: "wrap",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.78rem",
  gap: "0.75rem",
  marginTop: "0.65rem",
};

function sourceLabel(source: string | null | undefined): string {
  const normalized = source?.trim().toUpperCase();
  if (normalized === "POLYMARKET") return "Polymarket";
  if (normalized === "KALSHI") return "Kalshi";
  return normalized ? normalized.toLowerCase() : "Market";
}

function dateLabel(iso: string): string {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function scoreLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

function bucketLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return value.toFixed(1);
}

function outcomeColor(outcome: string): string {
  const normalized = outcome.trim().toUpperCase();
  if (normalized === "YES") return "var(--forecasts-prob-yes)";
  if (normalized === "NO") return "var(--forecasts-prob-no)";
  return "var(--forecasts-muted)";
}

function matchingBucket(
  calibration: CalibrationBucket[] | null | undefined,
  bucket: number | null,
): CalibrationBucket | null {
  if (!calibration || bucket === null || !Number.isFinite(bucket)) return null;
  return (
    calibration.find((item) => Math.abs(item.bucket - bucket) < 0.0001) ?? null
  );
}

function bucketSummary(bucket: CalibrationBucket | null, bucketValue: number | null): string {
  const label = bucketLabel(bucketValue);
  if (!bucket || bucket.empirical_yes_rate === null) {
    return `Calibration so far in ${label} bucket: unavailable`;
  }

  return `Calibration so far in ${label} bucket: ${Math.round(
    bucket.empirical_yes_rate * 100,
  )}% YES (n=${bucket.resolved_count})`;
}

export default function ResolutionPanel({
  calibration,
  market,
  resolution,
}: ResolutionPanelProps) {
  if (!resolution) return null;

  const outcome = resolution.market_outcome.trim().toUpperCase();
  const color = outcomeColor(outcome);
  const marketName = sourceLabel(market?.source);

  if (outcome === "CANCELLED" || outcome === "AMBIGUOUS") {
    return (
      <section
        aria-label="Resolution"
        style={{
          ...panelBaseStyle,
          background: "rgba(232, 225, 211, 0.035)",
          borderColor: "var(--forecasts-muted)",
        }}
      >
        <h2
          style={{
            color,
            fontFamily: "'Cinzel', serif",
            fontSize: "0.98rem",
            letterSpacing: "0.08em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          Withdrawn — {marketName} {outcome.toLowerCase()}{" "}
          {dateLabel(resolution.resolved_at)}
        </h2>
        <p
          style={{
            color: "var(--forecasts-parchment-dim)",
            lineHeight: 1.55,
            margin: "0.75rem 0 0",
          }}
        >
          Prediction withdrawn from calibration because the external market did
          not settle to YES or NO.
        </p>
        <p
          style={{
            color: "var(--forecasts-parchment)",
            lineHeight: 1.55,
            margin: "0.65rem 0 0",
          }}
        >
          <strong>Justification:</strong> {resolution.justification}
        </p>
      </section>
    );
  }

  const bucket = matchingBucket(calibration, resolution.calibration_bucket);

  return (
    <section
      aria-label="Resolution"
      style={{
        ...panelBaseStyle,
        background: `color-mix(in srgb, ${color} 10%, transparent)`,
        borderColor: color,
      }}
    >
      <h2
        style={{
          color,
          fontFamily: "'Cinzel', serif",
          fontSize: "0.98rem",
          letterSpacing: "0.08em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        Resolved {outcome} — {marketName} settled {dateLabel(resolution.resolved_at)}
      </h2>

      <div style={metaStyle}>
        <span>Brier: {scoreLabel(resolution.brier_score)}</span>
        <span>Log-loss: {scoreLabel(resolution.log_loss)}</span>
        <span>Bucket: {bucketLabel(resolution.calibration_bucket)}</span>
      </div>

      <p
        style={{
          color: "var(--forecasts-parchment-dim)",
          fontSize: "0.9rem",
          margin: "0.75rem 0 0",
        }}
      >
        {bucketSummary(bucket, resolution.calibration_bucket)}
      </p>

      <p
        style={{
          color: "var(--forecasts-parchment)",
          lineHeight: 1.55,
          margin: "0.65rem 0 0",
        }}
      >
        <strong>Justification:</strong> {resolution.justification}
      </p>
    </section>
  );
}
