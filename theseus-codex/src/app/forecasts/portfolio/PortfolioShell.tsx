import Link from "next/link";
import type { CSSProperties } from "react";

import type { CalibrationBucket, PortfolioSummary } from "@/lib/forecastsTypes";

import BetLogTable, { type PortfolioBet, paperBetsOnly } from "./BetLogTable";
import BrierTimeChart, { type BrierTimePoint } from "./BrierTimeChart";
import CalibrationChart from "./CalibrationChart";
import DistributionHistogram from "./DistributionHistogram";
import PaperPnLChart from "./PaperPnLChart";
import StatusStrip from "./StatusStrip";

export type PortfolioSummaryWithLive = PortfolioSummary & {
  brierCurve?: BrierTimePoint[];
  brier_curve?: BrierTimePoint[];
  liveTradingAuthorized?: boolean | null;
  liveTradingEnabled?: boolean;
  liveTradingStatus?: string | null;
  live_trading_authorized?: boolean | null;
  live_trading_enabled?: boolean;
  live_trading_status?: string | null;
  total_resolved?: number;
};

export interface PortfolioShellProps {
  bets: PortfolioBet[];
  brierPoints: BrierTimePoint[];
  calibration: CalibrationBucket[];
  fetchError?: string | null;
  nextSince?: string | null;
  since?: string | null;
  summary: PortfolioSummaryWithLive;
}

const pageGridStyle: CSSProperties = {
  display: "grid",
  gap: "1rem",
};

function optionalBool(...values: Array<boolean | null | undefined>): boolean | undefined {
  for (const value of values) {
    if (typeof value === "boolean") return value;
  }
  return undefined;
}

function optionalString(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function liveTradingEnabled(summary: PortfolioSummaryWithLive): boolean {
  return Boolean(optionalBool(summary.liveTradingEnabled, summary.live_trading_enabled));
}

function liveTradingAuthorized(summary: PortfolioSummaryWithLive): boolean | null | undefined {
  return optionalBool(summary.liveTradingAuthorized, summary.live_trading_authorized);
}

function liveTradingStatus(summary: PortfolioSummaryWithLive): string | null {
  return optionalString(summary.liveTradingStatus, summary.live_trading_status);
}

function resolvedCount(summary: PortfolioSummaryWithLive, calibration: CalibrationBucket[]): number {
  if (typeof summary.total_resolved === "number" && Number.isFinite(summary.total_resolved)) {
    return summary.total_resolved;
  }
  return calibration.reduce((sum, bucket) => sum + Math.max(0, bucket.resolved_count || 0), 0);
}

function summarySubtitle(summary: PortfolioSummaryWithLive, calibration: CalibrationBucket[], bets: PortfolioBet[]): string {
  const resolved = resolvedCount(summary, calibration);
  const settledPaperBets = paperBetsOnly(bets).filter((bet) => bet.settlement_pnl_usd !== null);
  const wins = settledPaperBets.filter((bet) => (bet.settlement_pnl_usd ?? 0) > 0).length;
  const accuracy =
    settledPaperBets.length > 0 ? `${Math.round((wins / settledPaperBets.length) * 100)}% accuracy on bets` : "no settled paper bets";
  return `Since first prediction | ${resolved} resolved | ${wins} wins | ${accuracy}`;
}

function filterBetsBySince(bets: PortfolioBet[], since: string | null): PortfolioBet[] {
  if (!since) return bets.slice(0, 200);
  const cursor = Date.parse(since);
  if (!Number.isFinite(cursor)) return bets.slice(0, 200);
  return bets.filter((bet) => Date.parse(bet.created_at) < cursor).slice(0, 200);
}

function nextSinceFor(bets: PortfolioBet[]): string | null {
  if (bets.length < 200) return null;
  return bets[bets.length - 1].created_at;
}

function LiveBetsTab() {
  return (
    <Link
      href="/forecasts/operator"
      style={{
        border: "1px solid var(--forecasts-cool-gold)",
        borderRadius: "999px",
        color: "var(--forecasts-cool-gold)",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "0.72rem",
        padding: "0.42rem 0.72rem",
        textDecoration: "none",
        textTransform: "uppercase",
      }}
    >
      Live bets | founder login
    </Link>
  );
}

export default function PortfolioShell({
  bets,
  brierPoints,
  calibration,
  fetchError,
  nextSince,
  since,
  summary,
}: PortfolioShellProps) {
  const displayBets = filterBetsBySince(bets, since ?? null);
  const nextSinceValue = nextSince ?? nextSinceFor(displayBets);
  const liveEnabled = liveTradingEnabled(summary);

  return (
    <main style={pageGridStyle}>
      <section
        style={{
          alignItems: "start",
          display: "flex",
          flexWrap: "wrap",
          gap: "1rem",
          justifyContent: "space-between",
        }}
      >
        <div>
          <h1
            style={{
              fontFamily: "'EB Garamond', serif",
              fontSize: "2rem",
              lineHeight: 1,
              margin: 0,
            }}
          >
            Forecasts Portfolio
          </h1>
          <p style={{ color: "var(--forecasts-parchment-dim)", lineHeight: 1.5, margin: "0.45rem 0 0" }}>
            {summarySubtitle(summary, calibration, bets)}
          </p>
        </div>
        <div
          aria-label="Portfolio modes"
          style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.5rem" }}
        >
          <span
            style={{
              background: "rgba(232, 225, 211, 0.06)",
              border: "1px solid var(--forecasts-border)",
              borderRadius: "999px",
              color: "var(--forecasts-parchment)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.72rem",
              padding: "0.42rem 0.72rem",
              textTransform: "uppercase",
            }}
          >
            Paper scoreboard
          </span>
          {liveEnabled ? <LiveBetsTab /> : null}
        </div>
      </section>

      {fetchError ? (
        <div
          role="alert"
          style={{
            background: "rgba(185, 92, 92, 0.1)",
            border: "1px solid rgba(185, 92, 92, 0.45)",
            borderRadius: "8px",
            color: "var(--forecasts-parchment)",
            padding: "0.85rem 1rem",
          }}
        >
          Portfolio data fetch was incomplete: {fetchError}
        </div>
      ) : null}

      <StatusStrip
        killSwitchEngaged={summary.kill_switch_engaged}
        killSwitchReason={summary.kill_switch_reason}
        liveTradingAuthorized={liveTradingAuthorized(summary)}
        liveTradingEnabled={liveEnabled}
        liveTradingStatus={liveTradingStatus(summary)}
        updatedAt={summary.updated_at}
      />

      <CalibrationChart buckets={calibration} />
      <BrierTimeChart points={brierPoints} />
      <PaperPnLChart bets={displayBets} points={summary.paper_pnl_curve} />
      <BetLogTable bets={displayBets} nextSince={nextSinceValue} since={since} />
      <DistributionHistogram buckets={calibration} />
    </main>
  );
}
