import type { CSSProperties } from "react";

import type { PortfolioPoint, PublicBet } from "@/lib/forecastsTypes";

interface PaperPnLChartProps {
  bets: PublicBet[];
  points: PortfolioPoint[];
}

export interface LosingStreakRange {
  start: string;
  end: string;
  length: number;
}

const WIDTH = 720;
const HEIGHT = 300;
const MARGIN = { top: 24, right: 28, bottom: 42, left: 64 };
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

function parseTime(ts: string): number {
  const parsed = Date.parse(ts);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDate(ts: string): string {
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatUsd(value: number): string {
  const abs = Math.abs(value);
  const formatted = new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 0,
    style: "currency",
  }).format(abs);
  return value < 0 ? `-${formatted}` : formatted;
}

export function losingStreakRanges(bets: PublicBet[]): LosingStreakRange[] {
  const settled = bets
    .filter(
      (bet) =>
        bet.mode.toUpperCase() === "PAPER" &&
        bet.settlement_pnl_usd !== null &&
        Number.isFinite(bet.settlement_pnl_usd),
    )
    .sort((a, b) => parseTime(a.settled_at || a.created_at) - parseTime(b.settled_at || b.created_at));

  const ranges: LosingStreakRange[] = [];
  let streak: PublicBet[] = [];
  for (const bet of settled) {
    if ((bet.settlement_pnl_usd ?? 0) < 0) {
      streak.push(bet);
      continue;
    }
    if (streak.length >= 3) {
      ranges.push({
        start: streak[0].settled_at || streak[0].created_at,
        end: streak[streak.length - 1].settled_at || streak[streak.length - 1].created_at,
        length: streak.length,
      });
    }
    streak = [];
  }
  if (streak.length >= 3) {
    ranges.push({
      start: streak[0].settled_at || streak[0].created_at,
      end: streak[streak.length - 1].settled_at || streak[streak.length - 1].created_at,
      length: streak.length,
    });
  }
  return ranges;
}

export default function PaperPnLChart({ bets, points }: PaperPnLChartProps) {
  const cleanPoints = points
    .filter((point) => Number.isFinite(point.paper_pnl_usd) && Number.isFinite(parseTime(point.ts)))
    .sort((a, b) => parseTime(a.ts) - parseTime(b.ts));
  const ranges = losingStreakRanges(bets);

  const firstTs = cleanPoints.length > 0 ? parseTime(cleanPoints[0].ts) : 0;
  const lastTs = cleanPoints.length > 0 ? parseTime(cleanPoints[cleanPoints.length - 1].ts) : 0;
  const minPnl = Math.min(0, ...cleanPoints.map((point) => point.paper_pnl_usd));
  const maxPnl = Math.max(0, ...cleanPoints.map((point) => point.paper_pnl_usd));
  const yPad = Math.max(10, (maxPnl - minPnl) * 0.12);
  const yMin = minPnl - yPad;
  const yMax = maxPnl + yPad;
  const ySpan = yMax - yMin || 1;
  const xSpan = lastTs - firstTs || 1;
  const xFor = (ts: string) => MARGIN.left + ((parseTime(ts) - firstTs) / xSpan) * PLOT_WIDTH;
  const yFor = (value: number) => MARGIN.top + ((yMax - value) / ySpan) * PLOT_HEIGHT;
  const path = cleanPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xFor(point.ts).toFixed(2)} ${yFor(point.paper_pnl_usd).toFixed(2)}`)
    .join(" ");

  return (
    <section aria-labelledby="pnl-heading" style={cardStyle}>
      <h2 id="pnl-heading" style={titleStyle}>
        Paper P&amp;L curve
      </h2>
      <p style={{ color: "var(--forecasts-parchment-dim)", fontSize: "0.82rem", margin: "0.35rem 0 0" }}>
        Cumulative public paper-bet settlement P&amp;L. Live trading P&amp;L is not mixed into this curve.
      </p>
      {cleanPoints.length === 0 ? (
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
          No settled paper bets yet.
        </div>
      ) : (
        <div style={{ marginTop: "0.8rem", overflowX: "auto" }}>
          <svg
            aria-label="Cumulative paper P&L"
            role="img"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            style={{ display: "block", minWidth: "600px", width: "100%" }}
          >
            <rect fill="transparent" height={HEIGHT} width={WIDTH} />
            {ranges.map((range) => {
              const x1 = xFor(range.start);
              const x2 = xFor(range.end);
              return (
                <rect
                  key={`${range.start}-${range.end}`}
                  fill="rgba(185, 92, 92, 0.14)"
                  height={PLOT_HEIGHT}
                  rx="4"
                  width={Math.max(8, x2 - x1)}
                  x={x1}
                  y={MARGIN.top}
                >
                  <title>{`Losing streak: ${range.length} settled paper bets from ${formatDate(range.start)} to ${formatDate(range.end)}`}</title>
                </rect>
              );
            })}
            {[yMin, 0, yMax].map((tick) => (
              <g key={tick}>
                <line
                  stroke={tick === 0 ? "rgba(232, 225, 211, 0.24)" : "rgba(232, 225, 211, 0.08)"}
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
                  {formatUsd(tick)}
                </text>
              </g>
            ))}
            <path d={path} fill="none" stroke="var(--forecasts-prob-yes)" strokeWidth="2.5" />
            {cleanPoints.map((point, index) => (
              <circle
                key={`${point.ts}-${index}`}
                cx={xFor(point.ts)}
                cy={yFor(point.paper_pnl_usd)}
                fill="var(--forecasts-parchment)"
                r={index === cleanPoints.length - 1 ? 4 : 2.5}
              >
                <title>{`${formatDate(point.ts)}: ${formatUsd(point.paper_pnl_usd)}`}</title>
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
