import type { CSSProperties } from "react";

import type { CalibrationBucket } from "@/lib/forecastsTypes";

export interface ResolutionForCalibration {
  probability_yes: number | null;
  market_outcome: string | null;
  brier_score?: number | null;
}

interface CalibrationPoint extends CalibrationBucket {
  bucket: number;
}

interface CalibrationChartProps {
  buckets: CalibrationBucket[];
}

const WIDTH = 720;
const HEIGHT = 360;
const MARGIN = { top: 24, right: 32, bottom: 52, left: 58 };
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom;

const cardStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.035)",
  border: "1px solid var(--forecasts-border)",
  borderRadius: "8px",
  padding: "1rem",
};

const titleStyle: CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.35rem",
  margin: 0,
};

const captionStyle: CSSProperties = {
  color: "var(--forecasts-parchment-dim)",
  fontSize: "0.82rem",
  lineHeight: 1.5,
  margin: "0.35rem 0 0",
};

function roundTenth(value: number): number {
  return Math.round(value * 10) / 10;
}

export function bucketForProbability(probabilityYes: number): number {
  if (!Number.isFinite(probabilityYes)) return 0;
  const clamped = Math.min(Math.max(probabilityYes, 0), 1);
  const floored = Math.floor(clamped * 10 + 1e-10) / 10;
  return roundTenth(Math.min(floored, 0.9));
}

export function normalizeCalibrationBucket(bucket: number): number {
  if (!Number.isFinite(bucket)) return 0;
  return bucketForProbability(bucket);
}

export function buildCalibrationBucketsFromResolutions(
  rows: ResolutionForCalibration[],
): CalibrationBucket[] {
  const groups = new Map<
    number,
    {
      briers: number[];
      probabilities: number[];
      resolvedCount: number;
      yesCount: number;
    }
  >();

  for (const row of rows) {
    const outcome = row.market_outcome?.toUpperCase();
    if (outcome !== "YES" && outcome !== "NO") continue;
    if (row.probability_yes === null || !Number.isFinite(row.probability_yes)) continue;

    const bucket = bucketForProbability(row.probability_yes);
    const group =
      groups.get(bucket) ??
      {
        briers: [],
        probabilities: [],
        resolvedCount: 0,
        yesCount: 0,
      };

    group.resolvedCount += 1;
    group.yesCount += outcome === "YES" ? 1 : 0;
    group.probabilities.push(row.probability_yes);
    if (row.brier_score !== null && row.brier_score !== undefined && Number.isFinite(row.brier_score)) {
      group.briers.push(row.brier_score);
    }
    groups.set(bucket, group);
  }

  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([bucket, group]) => ({
      bucket,
      prediction_count: group.resolvedCount,
      resolved_count: group.resolvedCount,
      mean_probability_yes:
        group.probabilities.length > 0
          ? group.probabilities.reduce((sum, value) => sum + value, 0) / group.probabilities.length
          : null,
      empirical_yes_rate:
        group.resolvedCount > 0 ? group.yesCount / group.resolvedCount : null,
      mean_brier:
        group.briers.length > 0
          ? group.briers.reduce((sum, value) => sum + value, 0) / group.briers.length
          : null,
    }));
}

export function calibrationPointsForDisplay(buckets: CalibrationBucket[]): CalibrationPoint[] {
  const merged = new Map<
    number,
    {
      meanBrierWeighted: number;
      meanBrierWeight: number;
      meanProbabilityWeighted: number;
      meanProbabilityWeight: number;
      predictionCount: number;
      resolvedCount: number;
      yesCount: number;
    }
  >();

  for (const bucket of buckets) {
    const normalizedBucket = normalizeCalibrationBucket(bucket.bucket);
    const existing =
      merged.get(normalizedBucket) ??
      {
        meanBrierWeighted: 0,
        meanBrierWeight: 0,
        meanProbabilityWeighted: 0,
        meanProbabilityWeight: 0,
        predictionCount: 0,
        resolvedCount: 0,
        yesCount: 0,
      };
    const resolvedCount = Math.max(0, bucket.resolved_count || 0);
    existing.predictionCount += Math.max(0, bucket.prediction_count || 0);
    existing.resolvedCount += resolvedCount;

    if (bucket.empirical_yes_rate !== null && Number.isFinite(bucket.empirical_yes_rate)) {
      existing.yesCount += bucket.empirical_yes_rate * resolvedCount;
    }
    if (bucket.mean_probability_yes !== null && Number.isFinite(bucket.mean_probability_yes)) {
      existing.meanProbabilityWeighted += bucket.mean_probability_yes * Math.max(resolvedCount, 1);
      existing.meanProbabilityWeight += Math.max(resolvedCount, 1);
    }
    if (bucket.mean_brier !== null && Number.isFinite(bucket.mean_brier)) {
      existing.meanBrierWeighted += bucket.mean_brier * Math.max(resolvedCount, 1);
      existing.meanBrierWeight += Math.max(resolvedCount, 1);
    }
    merged.set(normalizedBucket, existing);
  }

  return [...merged.entries()]
    .sort(([a], [b]) => a - b)
    .map(([bucket, group]) => ({
      bucket,
      prediction_count: group.predictionCount,
      resolved_count: group.resolvedCount,
      mean_probability_yes:
        group.meanProbabilityWeight > 0 ? group.meanProbabilityWeighted / group.meanProbabilityWeight : null,
      empirical_yes_rate: group.resolvedCount > 0 ? group.yesCount / group.resolvedCount : null,
      mean_brier: group.meanBrierWeight > 0 ? group.meanBrierWeighted / group.meanBrierWeight : null,
    }));
}

function xForProbability(value: number): number {
  return MARGIN.left + value * PLOT_WIDTH;
}

function yForRate(value: number): number {
  return MARGIN.top + (1 - value) * PLOT_HEIGHT;
}

function formatPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return `${Math.round(value * 100)}%`;
}

function dotRadius(resolvedCount: number, maxResolvedCount: number): number {
  if (resolvedCount <= 0 || maxResolvedCount <= 0) return 4;
  return 5 + Math.sqrt(resolvedCount / maxResolvedCount) * 11;
}

export default function CalibrationChart({ buckets }: CalibrationChartProps) {
  const points = calibrationPointsForDisplay(buckets).filter(
    (bucket) => bucket.resolved_count > 0 && bucket.empirical_yes_rate !== null,
  );
  const maxResolvedCount = Math.max(0, ...points.map((point) => point.resolved_count));

  return (
    <section aria-labelledby="calibration-heading" style={cardStyle}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", justifyContent: "space-between" }}>
        <div>
          <h2 id="calibration-heading" style={titleStyle}>
            How often does p% confident -&gt; actually YES?
          </h2>
          <p style={captionStyle}>
            Reliability diagram. Buckets exclude cancelled markets; dot area scales with resolved sample size.
          </p>
        </div>
        <div
          style={{
            color: "var(--forecasts-muted)",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.72rem",
            textTransform: "uppercase",
          }}
        >
          Source: /v1/portfolio/calibration
        </div>
      </div>

      {points.length === 0 ? (
        <div
          role="status"
          style={{
            border: "1px dashed var(--forecasts-border)",
            borderRadius: "6px",
            color: "var(--forecasts-parchment-dim)",
            marginTop: "1rem",
            padding: "1.25rem",
          }}
        >
          No resolved non-cancelled predictions yet. Calibration will appear after markets settle.
        </div>
      ) : (
        <div style={{ marginTop: "0.8rem", overflowX: "auto" }}>
          <svg
            aria-label="Calibration reliability diagram"
            role="img"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            style={{ display: "block", minWidth: "620px", width: "100%" }}
          >
            <rect fill="transparent" height={HEIGHT} width={WIDTH} />
            {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
              <g key={`y-${tick}`}>
                <line
                  stroke="rgba(232, 225, 211, 0.08)"
                  x1={MARGIN.left}
                  x2={WIDTH - MARGIN.right}
                  y1={yForRate(tick)}
                  y2={yForRate(tick)}
                />
                <text
                  fill="var(--forecasts-parchment-dim)"
                  fontFamily="'IBM Plex Mono', monospace"
                  fontSize="11"
                  textAnchor="end"
                  x={MARGIN.left - 10}
                  y={yForRate(tick) + 4}
                >
                  {formatPercent(tick)}
                </text>
              </g>
            ))}
            {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
              <g key={`x-${tick}`}>
                <line
                  stroke="rgba(232, 225, 211, 0.08)"
                  x1={xForProbability(tick)}
                  x2={xForProbability(tick)}
                  y1={MARGIN.top}
                  y2={HEIGHT - MARGIN.bottom}
                />
                <text
                  fill="var(--forecasts-parchment-dim)"
                  fontFamily="'IBM Plex Mono', monospace"
                  fontSize="11"
                  textAnchor="middle"
                  x={xForProbability(tick)}
                  y={HEIGHT - MARGIN.bottom + 24}
                >
                  {formatPercent(tick)}
                </text>
              </g>
            ))}
            <line
              stroke="rgba(196, 160, 75, 0.5)"
              strokeDasharray="5 5"
              strokeWidth="2"
              x1={xForProbability(0)}
              x2={xForProbability(1)}
              y1={yForRate(0)}
              y2={yForRate(1)}
            />
            <text
              fill="var(--forecasts-muted)"
              fontFamily="'IBM Plex Mono', monospace"
              fontSize="11"
              textAnchor="middle"
              x={MARGIN.left + PLOT_WIDTH / 2}
              y={HEIGHT - 8}
            >
              Predicted YES probability bucket
            </text>
            <text
              fill="var(--forecasts-muted)"
              fontFamily="'IBM Plex Mono', monospace"
              fontSize="11"
              textAnchor="middle"
              transform={`rotate(-90 ${14} ${MARGIN.top + PLOT_HEIGHT / 2})`}
              x={14}
              y={MARGIN.top + PLOT_HEIGHT / 2}
            >
              Empirical YES rate
            </text>
            {points.map((point) => {
              const x = xForProbability(point.bucket + 0.05);
              const y = yForRate(point.empirical_yes_rate ?? 0);
              const label = `${formatPercent(point.bucket)}-${formatPercent(
                Math.min(point.bucket + 0.1, 1),
              )}: ${formatPercent(point.empirical_yes_rate)} YES (n=${point.resolved_count})`;
              return (
                <g key={point.bucket}>
                  <circle
                    cx={x}
                    cy={y}
                    fill="rgba(111, 161, 92, 0.72)"
                    r={dotRadius(point.resolved_count, maxResolvedCount)}
                    stroke="var(--forecasts-parchment)"
                    strokeOpacity="0.8"
                    strokeWidth="1.5"
                  >
                    <title>{label}</title>
                  </circle>
                  <text
                    fill="var(--forecasts-parchment)"
                    fontFamily="'IBM Plex Mono', monospace"
                    fontSize="10"
                    textAnchor="middle"
                    x={x}
                    y={Math.max(MARGIN.top + 12, y - dotRadius(point.resolved_count, maxResolvedCount) - 7)}
                  >
                    {formatPercent(point.empirical_yes_rate)}
                  </text>
                </g>
              );
            })}
          </svg>
          <div
            aria-label="Calibration bucket values"
            style={{
              display: "grid",
              gap: "0.35rem",
              gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
              marginTop: "0.75rem",
            }}
          >
            {points.map((point) => (
              <span
                key={`legend-${point.bucket}`}
                style={{
                  color: "var(--forecasts-parchment-dim)",
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "0.72rem",
                }}
              >
                {formatPercent(point.bucket)}-{formatPercent(Math.min(point.bucket + 0.1, 1))}:{" "}
                {formatPercent(point.empirical_yes_rate)} YES (n={point.resolved_count})
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
