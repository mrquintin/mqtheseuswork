"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import {
  bucketBinary,
  directionalAccuracyByClass,
  type BinaryOutcome,
  type DirectionalSample,
} from "@/lib/calibration";

import type {
  ActivePrinciple,
  UnifiedOverview,
} from "./types";

const sectionStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 6,
  background: "rgba(232, 225, 211, 0.035)",
  padding: "1rem",
};

const labelStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.6rem",
  letterSpacing: "0.15em",
  margin: 0,
  textTransform: "uppercase",
};

function fmtUsd(value: number): string {
  const out = new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(Math.abs(value));
  return value < 0 ? `-${out}` : value > 0 ? `+${out}` : out;
}

function fmtPct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

export type OverviewTabProps = {
  overview: UnifiedOverview;
  binaryOutcomes: BinaryOutcome[];
  directionalSamples: DirectionalSample[];
};

export default function OverviewTab({
  overview,
  binaryOutcomes,
  directionalSamples,
}: OverviewTabProps) {
  const calibrationBuckets = bucketBinary(binaryOutcomes);
  const directionalByClass = directionalAccuracyByClass(directionalSamples);
  return (
    <div
      data-testid="portfolio-overview-tab"
      style={{ display: "grid", gap: "1rem" }}
    >
      <NetCurve overview={overview} />
      <div
        style={{
          display: "grid",
          gap: "1rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
        }}
      >
        <CalibrationCard buckets={calibrationBuckets} />
        <DirectionalCard buckets={directionalByClass} />
      </div>
      <PositionCounts overview={overview} />
      <ActivePrinciplesRail principles={overview.activePrinciples} />
    </div>
  );
}

function NetCurve({ overview }: { overview: UnifiedOverview }) {
  const curve = overview.netPaperPnlCurve;
  const min =
    curve.length === 0 ? 0 : Math.min(...curve.map((p) => p.paperPnlUsd), 0);
  const max =
    curve.length === 0 ? 0 : Math.max(...curve.map((p) => p.paperPnlUsd), 0);
  const range = max - min || 1;
  const width = 600;
  const height = 110;
  const points = curve.map((p, i) => {
    const x =
      curve.length === 1 ? width / 2 : (i / (curve.length - 1)) * width;
    const y = height - ((p.paperPnlUsd - min) / range) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <section
      aria-labelledby="overview-net-curve"
      data-testid="overview-net-curve"
      style={sectionStyle}
    >
      <h2 id="overview-net-curve" style={titleStyle}>
        Net paper P&amp;L
      </h2>
      <p className="mono" style={subtitleStyle}>
        cumulative across prediction markets + equities
      </p>
      <div style={{ alignItems: "baseline", display: "flex", gap: "1rem" }}>
        <strong
          style={{
            // R-022: P&L uses the firm palette — `--success` muted olive
            // for positive, `--ember` for negative, `--parchment-dim` for
            // zero. SaaS-bright green/red is reserved for nothing here.
            color:
              overview.netPaperPnlUsd > 0
                ? "var(--success)"
                : overview.netPaperPnlUsd < 0
                  ? "var(--ember)"
                  : "var(--parchment-dim)",
            fontSize: "1.6rem",
            fontFeatureSettings: '"tnum" 1',
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {fmtUsd(overview.netPaperPnlUsd)}
        </strong>
        <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.74rem" }}>
          {curve.length} fills
        </span>
      </div>
      {curve.length === 0 ? (
        <p style={hintStyle}>No paper fills yet across either track.</p>
      ) : (
        <svg
          aria-hidden="true"
          role="img"
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
        >
          <polyline
            fill="none"
            points={points.join(" ")}
            stroke="var(--amber, #cd9743)"
            strokeWidth={1.4}
          />
        </svg>
      )}
    </section>
  );
}

function CalibrationCard({
  buckets,
}: {
  buckets: ReturnType<typeof bucketBinary>;
}) {
  const nonEmpty = buckets.filter((b) => b.resolvedCount > 0);
  return (
    <section
      aria-labelledby="overview-calibration"
      data-testid="overview-calibration-plot"
      style={sectionStyle}
    >
      <h2 id="overview-calibration" style={titleStyle}>
        Prediction-market calibration
      </h2>
      <p className="mono" style={subtitleStyle}>
        Brier-bucketed reliability curve
      </p>
      {nonEmpty.length === 0 ? (
        <p style={hintStyle}>No resolved binary forecasts yet.</p>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={thStyle}>Bucket</th>
              <th style={thStyle}>n</th>
              <th style={thStyle}>Mean p(YES)</th>
              <th style={thStyle}>Empirical YES rate</th>
              <th style={thStyle}>Brier</th>
            </tr>
          </thead>
          <tbody>
            {nonEmpty.map((b) => (
              <tr key={b.bucket}>
                <td style={tdStyle}>{b.bucket.toFixed(2)}</td>
                <td style={tdStyle}>{b.resolvedCount}</td>
                <td style={tdStyle}>{fmtPct(b.meanProbabilityYes)}</td>
                <td style={tdStyle}>{fmtPct(b.empiricalYesRate)}</td>
                <td style={tdStyle}>
                  {b.meanBrier === null ? "n/a" : b.meanBrier.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function DirectionalCard({
  buckets,
}: {
  buckets: ReturnType<typeof directionalAccuracyByClass>;
}) {
  const populated = buckets.some((b) => b.total > 0);
  return (
    <section
      aria-labelledby="overview-directional"
      data-testid="overview-directional-plot"
      style={sectionStyle}
    >
      <h2 id="overview-directional" style={titleStyle}>
        Equity directional accuracy
      </h2>
      <p className="mono" style={subtitleStyle}>
        BULLISH / BEARISH / NEUTRAL signals vs. realised move
      </p>
      {!populated ? (
        <p style={hintStyle}>No resolved equity signals yet.</p>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={thStyle}>Call</th>
              <th style={thStyle}>n</th>
              <th style={thStyle}>Correct</th>
              <th style={thStyle}>Hit rate</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => (
              <tr key={b.predicted}>
                <td style={tdStyle}>{b.predicted}</td>
                <td style={tdStyle}>{b.total}</td>
                <td style={tdStyle}>{b.correct}</td>
                <td style={tdStyle}>{fmtPct(b.accuracy)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function PositionCounts({ overview }: { overview: UnifiedOverview }) {
  return (
    <section
      aria-labelledby="overview-position-counts"
      data-testid="overview-position-counts"
      style={sectionStyle}
    >
      <h2 id="overview-position-counts" style={titleStyle}>
        Active positions by asset class
      </h2>
      <div
        style={{
          display: "grid",
          gap: "0.75rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          marginTop: "0.6rem",
        }}
      >
        <Stat
          label="Prediction markets"
          value={overview.forecasts.openPositions}
        />
        <Stat label="Equities" value={overview.equities.openPositions} />
        <Stat
          label="Realized P&L (forecasts)"
          value={fmtUsd(overview.forecasts.realizedPaperPnlUsd)}
        />
        <Stat
          label="Realized P&L (equities)"
          value={fmtUsd(overview.equities.realizedPaperPnlUsd)}
        />
      </div>
    </section>
  );
}

function ActivePrinciplesRail({
  principles,
}: {
  principles: ActivePrinciple[];
}) {
  return (
    <section
      aria-labelledby="overview-active-principles"
      data-testid="overview-active-principles"
      style={sectionStyle}
    >
      <h2 id="overview-active-principles" style={titleStyle}>
        Active principles
      </h2>
      <p className="mono" style={subtitleStyle}>
        principles supporting at least one open position
      </p>
      {principles.length === 0 ? (
        <p style={hintStyle}>
          No open positions yet — once the algorithm sizes a paper trade, the
          principles it leaned on appear here.
        </p>
      ) : (
        <ol style={{ display: "grid", gap: "0.45rem", listStyle: "none", margin: 0, padding: 0 }}>
          {principles.map((p) => (
            <li key={p.conclusionId}>
              <Link
                data-testid="overview-principle-link"
                href={`/principles/${p.conclusionId}`}
                style={{
                  color: "var(--amber)",
                  display: "grid",
                  gap: "0.15rem",
                  textDecoration: "none",
                }}
              >
                <span className="mono" style={{ fontSize: "0.66rem" }}>
                  [C:{p.conclusionId.slice(0, 8)}] supports {p.positionCount} open{" "}
                  {p.positionCount === 1 ? "position" : "positions"}
                </span>
                <span style={{ color: "var(--parchment)" }}>
                  {p.snippet || "(no snippet)"}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ display: "grid", gap: "0.2rem" }}>
      <span style={labelStyle}>{label}</span>
      <strong style={{ color: "var(--parchment)", fontSize: "1.2rem" }}>
        {value}
      </strong>
    </div>
  );
}

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
