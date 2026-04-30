import type { CSSProperties } from "react";

import type { CalibrationBucket } from "@/lib/forecastsTypes";

import { calibrationPointsForDisplay } from "./CalibrationChart";

interface DistributionHistogramProps {
  buckets: CalibrationBucket[];
}

const cardStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.035)",
  border: "1px solid var(--forecasts-border)",
  borderRadius: "8px",
  padding: "1rem",
};

const titleStyle: CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.2rem",
  margin: 0,
};

function formatBucket(bucket: number): string {
  const start = Math.round(bucket * 100);
  const end = Math.round(Math.min(bucket + 0.1, 1) * 100);
  return `${start}-${end}%`;
}

export default function DistributionHistogram({ buckets }: DistributionHistogramProps) {
  const points = calibrationPointsForDisplay(buckets);
  const maxCount = Math.max(0, ...points.map((point) => point.prediction_count));
  const lookup = new Map(points.map((point) => [point.bucket, point.prediction_count]));
  const allBuckets = Array.from({ length: 10 }, (_, index) => index / 10);

  return (
    <section aria-labelledby="distribution-heading" style={cardStyle}>
      <h2 id="distribution-heading" style={titleStyle}>
        Probability distribution
      </h2>
      <p style={{ color: "var(--forecasts-parchment-dim)", fontSize: "0.82rem", margin: "0.35rem 0 0" }}>
        Count of resolved predictions in each probability bucket. A spike around 50% is a calibration smell test.
      </p>
      {maxCount === 0 ? (
        <div
          role="status"
          style={{
            border: "1px dashed var(--forecasts-border)",
            borderRadius: "6px",
            color: "var(--forecasts-parchment-dim)",
            marginTop: "0.85rem",
            padding: "1.1rem",
          }}
        >
          No resolved bucket distribution yet.
        </div>
      ) : (
        <div
          aria-label="Prediction counts by probability bucket"
          style={{
            alignItems: "end",
            display: "grid",
            gap: "0.5rem",
            gridTemplateColumns: "repeat(10, minmax(28px, 1fr))",
            height: "190px",
            marginTop: "1rem",
          }}
        >
          {allBuckets.map((bucket) => {
            const count = lookup.get(bucket) ?? 0;
            const height = count > 0 ? Math.max(8, (count / maxCount) * 150) : 2;
            return (
              <div
                key={bucket}
                style={{
                  alignItems: "center",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.35rem",
                  justifyContent: "end",
                  minWidth: 0,
                }}
              >
                <span
                  style={{
                    color: "var(--forecasts-parchment-dim)",
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: "0.68rem",
                  }}
                >
                  {count}
                </span>
                <div
                  title={`${formatBucket(bucket)}: ${count} predictions`}
                  style={{
                    background:
                      bucket >= 0.4 && bucket < 0.6
                        ? "var(--forecasts-cool-gold)"
                        : "var(--forecasts-prob-yes)",
                    borderRadius: "4px 4px 0 0",
                    height,
                    opacity: count > 0 ? 0.82 : 0.28,
                    width: "100%",
                  }}
                />
                <span
                  style={{
                    color: "var(--forecasts-muted)",
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: "0.62rem",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    width: "100%",
                  }}
                >
                  {Math.round(bucket * 100)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
