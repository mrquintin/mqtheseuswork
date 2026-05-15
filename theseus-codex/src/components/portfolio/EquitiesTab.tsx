"use client";

import type { CSSProperties } from "react";

import type {
  EquityCurvePoint,
  EquityOpenPosition,
  EquityRecentSignal,
  EquitySurface,
  MapeBucket,
} from "./types";

const sectionStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 6,
  background: "rgba(232, 225, 211, 0.035)",
  padding: "1rem",
};

const titleStyle: CSSProperties = {
  color: "var(--amber)",
  fontFamily: "'Cinzel', serif",
  fontSize: "1.05rem",
  letterSpacing: "0.06em",
  margin: 0,
};

const subtitleStyle: CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.66rem",
  letterSpacing: "0.1em",
  margin: "0.15rem 0 0.6rem",
};

const hintStyle: CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.78rem",
  margin: "0.6rem 0 0",
};

const thStyle: CSSProperties = {
  borderBottom: "1px solid rgba(232, 225, 211, 0.14)",
  color: "var(--amber-dim)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.6rem",
  letterSpacing: "0.16em",
  padding: "0.5rem 0.4rem",
  textAlign: "left",
  textTransform: "uppercase",
};

const tdStyle: CSSProperties = {
  borderBottom: "1px solid rgba(232, 225, 211, 0.08)",
  color: "var(--parchment)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.78rem",
  padding: "0.45rem 0.4rem",
};

function fmtUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "n/a";
  const formatted = new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(Math.abs(value));
  if (value < 0) return `-${formatted}`;
  if (value > 0) return `+${formatted}`;
  return formatted;
}

function fmtPct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

export type EquitiesTabProps = {
  surface: EquitySurface;
  onSelectPosition?: (positionId: string) => void;
};

export default function EquitiesTab({
  surface,
  onSelectPosition,
}: EquitiesTabProps) {
  return (
    <div data-testid="portfolio-equities-tab" style={{ display: "grid", gap: "1rem" }}>
      <OpenPositions
        rows={surface.openPositions}
        onSelectPosition={onSelectPosition}
      />
      <RecentSignals rows={surface.recentSignals} />
      <PaperPnlCurve rows={surface.paperPnlCurve} />
      <MapeChart rows={surface.targetPriceMape} />
    </div>
  );
}

function OpenPositions({
  rows,
  onSelectPosition,
}: {
  rows: EquityOpenPosition[];
  onSelectPosition?: (positionId: string) => void;
}) {
  return (
    <section
      aria-labelledby="equities-open-positions"
      data-testid="equities-open-positions"
      style={sectionStyle}
    >
      <h2 id="equities-open-positions" style={titleStyle}>
        Open equity positions
      </h2>
      <p className="mono" style={subtitleStyle}>
        paper cash-account positions sized off published signals
      </p>
      {rows.length === 0 ? (
        <p style={hintStyle}>
          No open equity positions. Once the algorithm publishes a non-neutral
          signal that clears every safety gate, the paper trade will appear
          here.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={thStyle}>Symbol</th>
                <th style={thStyle}>Direction</th>
                <th style={thStyle}>Side</th>
                <th style={thStyle}>Qty</th>
                <th style={thStyle}>Entry</th>
                <th style={thStyle}>Unrealized</th>
                <th style={thStyle}>Trace</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.positionId}>
                  <td style={tdStyle}>
                    <strong style={{ color: "var(--parchment)" }}>
                      {row.instrumentSymbol}
                    </strong>
                    {row.instrumentName ? (
                      <div
                        className="mono"
                        style={{ color: "var(--parchment-dim)", fontSize: "0.62rem" }}
                      >
                        {row.instrumentName}
                      </div>
                    ) : null}
                  </td>
                  <td style={tdStyle}>{row.direction}</td>
                  <td style={tdStyle}>{row.side}</td>
                  <td style={tdStyle}>{row.qty.toFixed(2)}</td>
                  <td style={tdStyle}>{fmtUsd(row.entryPrice)}</td>
                  <td style={tdStyle}>{fmtUsd(row.unrealizedPnlUsd)}</td>
                  <td style={tdStyle}>
                    <button
                      data-testid="equities-open-trace"
                      onClick={() => onSelectPosition?.(row.positionId)}
                      style={traceButtonStyle}
                      type="button"
                    >
                      Open trace
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RecentSignals({ rows }: { rows: EquityRecentSignal[] }) {
  return (
    <section
      aria-labelledby="equities-recent-signals"
      data-testid="equities-recent-signals"
      style={sectionStyle}
    >
      <h2 id="equities-recent-signals" style={titleStyle}>
        Recent equity signals
      </h2>
      <p className="mono" style={subtitleStyle}>
        published BULLISH / BEARISH / NEUTRAL calls and abstentions
      </p>
      {rows.length === 0 ? (
        <p style={hintStyle}>No equity signals yet.</p>
      ) : (
        <ul style={{ display: "grid", gap: "0.5rem", listStyle: "none", margin: 0, padding: 0 }}>
          {rows.map((row) => (
            <li
              key={row.signalId}
              style={{
                border: "1px solid rgba(232, 225, 211, 0.1)",
                borderRadius: 4,
                display: "grid",
                gap: "0.2rem",
                padding: "0.6rem 0.7rem",
              }}
            >
              <header style={{ display: "flex", gap: "0.5rem", justifyContent: "space-between" }}>
                <strong style={{ color: "var(--parchment)" }}>
                  {row.instrumentSymbol} · {row.direction}
                </strong>
                <span
                  className="mono"
                  style={{ color: "var(--parchment-dim)", fontSize: "0.66rem" }}
                >
                  {row.status} · horizon {row.horizonDays}d
                </span>
              </header>
              <span style={{ color: "var(--parchment)" }}>{row.headline}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PaperPnlCurve({ rows }: { rows: EquityCurvePoint[] }) {
  return (
    <section
      aria-labelledby="equities-paper-pnl"
      data-testid="equities-paper-pnl-curve"
      style={sectionStyle}
    >
      <h2 id="equities-paper-pnl" style={titleStyle}>
        Paper P&amp;L (equities)
      </h2>
      <p className="mono" style={subtitleStyle}>
        cumulative realised P&amp;L on closed equity positions
      </p>
      {rows.length === 0 ? (
        <p style={hintStyle}>No closed equity positions yet.</p>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={thStyle}>Closed at</th>
              <th style={thStyle}>Cumulative P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.ts}>
                <td style={tdStyle}>{row.ts}</td>
                <td style={tdStyle}>{fmtUsd(row.paperPnlUsd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function MapeChart({ rows }: { rows: MapeBucket[] }) {
  const populated = rows.some((b) => b.n > 0);
  return (
    <section
      aria-labelledby="equities-mape"
      data-testid="equities-mape"
      style={sectionStyle}
    >
      <h2 id="equities-mape" style={titleStyle}>
        Target-price MAPE
      </h2>
      <p className="mono" style={subtitleStyle}>
        mean absolute % error of target-midpoint vs. realised exit price,
        bucketed by horizon
      </p>
      {!populated ? (
        <p style={hintStyle}>
          No resolved signals with target prices yet — MAPE will populate as
          equity signals close out.
        </p>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={thStyle}>Horizon</th>
              <th style={thStyle}>n</th>
              <th style={thStyle}>MAPE</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.horizonLabel}>
                <td style={tdStyle}>{row.horizonLabel}</td>
                <td style={tdStyle}>{row.n}</td>
                <td style={tdStyle}>{fmtPct(row.meanAbsolutePctError)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const traceButtonStyle: CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(205, 151, 67, 0.45)",
  borderRadius: 4,
  color: "var(--amber)",
  cursor: "pointer",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.66rem",
  padding: "0.3rem 0.6rem",
};
