import type { CSSProperties } from "react";

export interface ResolutionForBrier {
  resolved_at: string | null;
  brier_score: number | null;
}

export interface BrierTimePoint {
  ts: string;
  mean_brier: number;
  sample_count: number;
}

interface BrierTimeChartProps {
  points: BrierTimePoint[];
}

const WIDTH = 720;
const HEIGHT = 280;
const MARGIN = { top: 24, right: 28, bottom: 42, left: 58 };
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
  fontSize: "1.2rem",
  margin: 0,
};

const emptyStyle: CSSProperties = {
  border: "1px dashed var(--forecasts-border)",
  borderRadius: "6px",
  color: "var(--forecasts-parchment-dim)",
  marginTop: "0.85rem",
  padding: "1.1rem",
};

function parseTime(ts: string): number {
  const parsed = Date.parse(ts);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDate(ts: string): string {
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatScore(value: number): string {
  return value.toFixed(3);
}

export function rollingBrierPointsFromResolutions(
  rows: ResolutionForBrier[],
  windowDays = 30,
): BrierTimePoint[] {
  const scored = rows
    .filter(
      (row): row is { resolved_at: string; brier_score: number } =>
        Boolean(row.resolved_at) &&
        row.brier_score !== null &&
        Number.isFinite(row.brier_score) &&
        Number.isFinite(Date.parse(row.resolved_at || "")),
    )
    .sort((a, b) => parseTime(a.resolved_at) - parseTime(b.resolved_at));

  const windowMs = windowDays * 24 * 60 * 60 * 1000;
  return scored.map((row, index) => {
    const currentTs = parseTime(row.resolved_at);
    const windowStart = currentTs - windowMs;
    const windowRows = scored
      .slice(0, index + 1)
      .filter((candidate) => parseTime(candidate.resolved_at) >= windowStart);
    const mean =
      windowRows.reduce((sum, candidate) => sum + candidate.brier_score, 0) / windowRows.length;
    return {
      ts: row.resolved_at,
      mean_brier: mean,
      sample_count: windowRows.length,
    };
  });
}

export default function BrierTimeChart({ points }: BrierTimeChartProps) {
  const cleanPoints = points
    .filter((point) => Number.isFinite(point.mean_brier) && Number.isFinite(parseTime(point.ts)))
    .sort((a, b) => parseTime(a.ts) - parseTime(b.ts));

  const firstTs = cleanPoints.length > 0 ? parseTime(cleanPoints[0].ts) : 0;
  const lastTs = cleanPoints.length > 0 ? parseTime(cleanPoints[cleanPoints.length - 1].ts) : 0;
  const maxBrier = Math.max(0.4, ...cleanPoints.map((point) => point.mean_brier));
  const minBrier = Math.min(0, ...cleanPoints.map((point) => point.mean_brier));
  const ySpan = maxBrier - minBrier || 1;
  const xSpan = lastTs - firstTs || 1;
  const xFor = (ts: string) => MARGIN.left + ((parseTime(ts) - firstTs) / xSpan) * PLOT_WIDTH;
  const yFor = (value: number) => MARGIN.top + ((maxBrier - value) / ySpan) * PLOT_HEIGHT;
  const path = cleanPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xFor(point.ts).toFixed(2)} ${yFor(point.mean_brier).toFixed(2)}`)
    .join(" ");

  return (
    <section aria-labelledby="brier-heading" style={cardStyle}>
      <h2 id="brier-heading" style={titleStyle}>
        Rolling 30-day Brier score
      </h2>
      <p style={{ color: "var(--forecasts-parchment-dim)", fontSize: "0.82rem", margin: "0.35rem 0 0" }}>
        Lower is better. The curve uses resolved forecasts with dated Brier scores.
      </p>
      {cleanPoints.length === 0 ? (
        <div role="status" style={emptyStyle}>
          No resolved Brier observations yet. This chart stays empty instead of inferring time-series data
          from aggregate portfolio fields.
        </div>
      ) : (
        <div style={{ marginTop: "0.8rem", overflowX: "auto" }}>
          <svg
            aria-label="Rolling 30-day mean Brier score"
            role="img"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            style={{ display: "block", minWidth: "600px", width: "100%" }}
          >
            <rect fill="transparent" height={HEIGHT} width={WIDTH} />
            {[0, 0.1, 0.2, 0.3, 0.4].map((tick) => (
              <g key={tick}>
                <line
                  stroke="rgba(232, 225, 211, 0.08)"
                  x1={MARGIN.left}
                  x2={WIDTH - MARGIN.right}
                  y1={yFor(tick)}
                  y2={yFor(tick)}
                />
                <text
                  fill="var(--forecasts-parchment-dim)"
                  fontFamily="'IBM Plex Mono', monospace"
                  fontSize="11"
                  textAnchor="end"
                  x={MARGIN.left - 10}
                  y={yFor(tick) + 4}
                >
                  {tick.toFixed(1)}
                </text>
              </g>
            ))}
            <path d={path} fill="none" stroke="var(--forecasts-cool-gold)" strokeWidth="2.5" />
            {cleanPoints.map((point) => (
              <circle
                key={`${point.ts}-${point.mean_brier}`}
                cx={xFor(point.ts)}
                cy={yFor(point.mean_brier)}
                fill="var(--forecasts-parchment)"
                r="3.5"
              >
                <title>{`${formatDate(point.ts)}: ${formatScore(point.mean_brier)} over ${point.sample_count} resolved`}</title>
              </circle>
            ))}
            <text
              fill="var(--forecasts-parchment-dim)"
              fontFamily="'IBM Plex Mono', monospace"
              fontSize="11"
              textAnchor="start"
              x={MARGIN.left}
              y={HEIGHT - 12}
            >
              {formatDate(cleanPoints[0].ts)}
            </text>
            <text
              fill="var(--forecasts-parchment-dim)"
              fontFamily="'IBM Plex Mono', monospace"
              fontSize="11"
              textAnchor="end"
              x={WIDTH - MARGIN.right}
              y={HEIGHT - 12}
            >
              {formatDate(cleanPoints[cleanPoints.length - 1].ts)}
            </text>
          </svg>
        </div>
      )}
    </section>
  );
}
