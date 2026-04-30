import type { Metadata } from "next";

import { getPortfolioBets, getPortfolioCalibration, getPortfolioSummary, listForecasts } from "@/lib/forecastsApi";
import type { PublicForecast } from "@/lib/forecastsTypes";
import { SITE } from "@/lib/site";

import type { PortfolioBet } from "./BetLogTable";
import { rollingBrierPointsFromResolutions, type BrierTimePoint } from "./BrierTimeChart";
import PortfolioShell, { type PortfolioSummaryWithLive } from "./PortfolioShell";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const title = "Theseus — Forecasts portfolio";
  const description = "Public paper-bet performance, calibration, and trading posture for Theseus forecasts.";

  return {
    title,
    description,
    openGraph: {
      description,
      siteName: "Theseus Codex",
      title,
      type: "website",
      url: `${SITE}/forecasts/portfolio`,
    },
    twitter: {
      card: "summary",
      description,
      title,
    },
  };
}

type SearchParams = Record<string, string | string[] | undefined>;

const emptySummary: PortfolioSummaryWithLive = {
  organization_id: "unknown",
  paper_balance_usd: 0,
  paper_pnl_curve: [],
  calibration: [],
  mean_brier_90d: null,
  total_bets: 0,
  kill_switch_engaged: false,
  kill_switch_reason: null,
  updated_at: null,
};

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

async function getRecentPortfolioBets(limit = 200): Promise<PortfolioBet[]> {
  const out: PortfolioBet[] = [];
  let offset = 0;
  while (out.length < limit) {
    const batchLimit = Math.min(50, limit - out.length);
    const response = await getPortfolioBets({ limit: batchLimit, offset });
    out.push(...response.items);
    if (response.next_offset === null || response.items.length === 0) break;
    offset = response.next_offset;
  }
  return out;
}

async function getResolvedForecastsForBrier(): Promise<PublicForecast[]> {
  const response = await listForecasts({ limit: 50, status: "RESOLVED" });
  return response.items;
}

function explicitBrierPoints(summary: PortfolioSummaryWithLive): BrierTimePoint[] {
  const raw = summary.brierCurve ?? summary.brier_curve;
  return Array.isArray(raw) ? raw : [];
}

function brierPointsFromForecasts(forecasts: PublicForecast[]): BrierTimePoint[] {
  return rollingBrierPointsFromResolutions(
    forecasts.map((forecast) => ({
      brier_score: forecast.resolution?.brier_score ?? null,
      resolved_at: forecast.resolution?.resolved_at ?? null,
    })),
  );
}

export default async function ForecastsPortfolioPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const since = firstParam(sp.since);

  const [summaryResult, calibrationResult, betsResult, resolvedForecastsResult] = await Promise.allSettled([
    getPortfolioSummary(),
    getPortfolioCalibration(),
    getRecentPortfolioBets(200),
    getResolvedForecastsForBrier(),
  ]);

  const summary =
    summaryResult.status === "fulfilled" ? (summaryResult.value as PortfolioSummaryWithLive) : emptySummary;
  const calibration =
    calibrationResult.status === "fulfilled" ? calibrationResult.value.items : summary.calibration;
  const bets = betsResult.status === "fulfilled" ? betsResult.value : [];
  const explicitPoints = explicitBrierPoints(summary);
  const brierPoints =
    explicitPoints.length > 0
      ? explicitPoints
      : resolvedForecastsResult.status === "fulfilled"
        ? brierPointsFromForecasts(resolvedForecastsResult.value)
        : [];
  const errors = [
    summaryResult.status === "rejected" ? "summary" : null,
    calibrationResult.status === "rejected" ? "calibration" : null,
    betsResult.status === "rejected" ? "bets" : null,
    resolvedForecastsResult.status === "rejected" ? "brier forecasts" : null,
  ].filter(Boolean);

  if (errors.length > 0) {
    console.error("forecasts_portfolio_fetch_failed", errors);
  }

  return (
    <PortfolioShell
      bets={bets}
      brierPoints={brierPoints}
      calibration={calibration}
      fetchError={errors.length > 0 ? errors.join(", ") : null}
      since={since}
      summary={summary}
    />
  );
}
