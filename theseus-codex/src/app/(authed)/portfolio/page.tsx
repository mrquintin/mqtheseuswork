import type { Metadata } from "next";

import ForecastPortfolioView from "@/app/(authed)/forecasts/portfolio/ForecastPortfolioView";
import { addWatchedMarket } from "@/app/(authed)/forecasts/portfolio/actions";
import PortfolioShell from "@/components/portfolio/PortfolioShell";
import type {
  EquitySurface,
  LivePillState,
  UnifiedOverview,
} from "@/components/portfolio/types";
import type { BinaryOutcome, DirectionalSample } from "@/lib/calibration";
import { getForecastPortfolioSurface } from "@/lib/forecastPortfolioData";
import { SITE } from "@/lib/site";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Theseus — Firm portfolio",
  description:
    "Unified portfolio: prediction-market and equity positions, calibration, kill-switch state, and the principles driving open positions.",
  openGraph: {
    description:
      "Unified portfolio: prediction-market and equity positions, calibration, kill-switch state, and the principles driving open positions.",
    siteName: "Theseus Codex",
    title: "Theseus — Firm portfolio",
    type: "website",
    url: `${SITE}/portfolio`,
  },
};

function pillState(envVar: string, authorized: boolean): LivePillState {
  const enabled = (process.env[envVar] || "").trim().toLowerCase() === "true";
  if (!enabled) return "DISABLED";
  if (!authorized) return "ENABLED-AWAITING-AUTH";
  return "ENABLED";
}

function forecastsAuthorized(): boolean {
  return Boolean(
    (process.env.POLYMARKET_PRIVATE_KEY || "").trim() ||
      (process.env.KALSHI_API_KEY_ID || "").trim(),
  );
}

function equitiesAuthorized(): boolean {
  return Boolean(
    (process.env.ALPACA_API_KEY_ID || process.env.ALPACA_KEY_ID || "").trim() ||
      (process.env.ROBINHOOD_USERNAME || "").trim(),
  );
}

function emptyEquitySurface(organizationId: string): EquitySurface {
  return {
    organizationId,
    paperBalanceUsd: 0,
    totals: {
      openPositions: 0,
      realizedPaperPnlUsd: 0,
      unrealizedPaperPnlUsd: 0,
    },
    liveStatus: {
      forecasts: pillState("FORECASTS_LIVE_TRADING_ENABLED", forecastsAuthorized()),
      equities: pillState("EQUITIES_LIVE_TRADING_ENABLED", equitiesAuthorized()),
    },
    killSwitchEngaged: false,
    killSwitchReason: null,
    openPositions: [],
    recentSignals: [],
    paperPnlCurve: [],
    targetPriceMape: [],
  };
}

export default async function UnifiedPortfolioPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const forecastSurface = await getForecastPortfolioSurface(tenant.organizationId);

  const liveStatus = {
    forecasts: pillState("FORECASTS_LIVE_TRADING_ENABLED", forecastsAuthorized()),
    equities: pillState("EQUITIES_LIVE_TRADING_ENABLED", equitiesAuthorized()),
  };

  const overview: UnifiedOverview = {
    organizationId: tenant.organizationId,
    netPaperPnlUsd:
      forecastSurface.kpis.realizedPaperPnl + forecastSurface.kpis.unrealizedPaperPnl,
    netPaperPnlCurve: [],
    forecasts: {
      openPositions: forecastSurface.kpis.openPositions,
      realizedPaperPnlUsd: forecastSurface.kpis.realizedPaperPnl,
      unrealizedPaperPnlUsd: forecastSurface.kpis.unrealizedPaperPnl,
    },
    equities: {
      openPositions: 0,
      realizedPaperPnlUsd: 0,
      unrealizedPaperPnlUsd: 0,
    },
    killSwitchEngaged: forecastSurface.mode.failedGates.some(
      (gate) => gate.gateName === "kill_switch_clear",
    ),
    killSwitchReason:
      forecastSurface.mode.failedGates.find(
        (gate) => gate.gateName === "kill_switch_clear",
      )?.reason ?? null,
    liveStatus,
    activePrinciples: collectActivePrinciples(forecastSurface),
  };

  // Binary and directional samples are populated by the API-side surface
  // (Brier-bucketed calibration on the forecasts side, three-class
  // hit-rate on the equities side). The unified page renders the curves
  // honestly: when neither track has resolutions yet, the cards say so.
  const binaryOutcomes: BinaryOutcome[] = [];
  const directionalSamples: DirectionalSample[] = [];

  return (
    <PortfolioShell
      binaryOutcomes={binaryOutcomes}
      directionalSamples={directionalSamples}
      equitySurface={emptyEquitySurface(tenant.organizationId)}
      overview={overview}
      predictionMarketsContent={
        <ForecastPortfolioView
          addWatchedMarketAction={addWatchedMarket}
          surface={forecastSurface}
        />
      }
    />
  );
}

function collectActivePrinciples(surface: {
  openPositions: { drivingPrinciples: { conclusionId: string; weight: number; snippet: string }[] }[];
}): UnifiedOverview["activePrinciples"] {
  const tally = new Map<
    string,
    { snippet: string; weightSum: number; count: number }
  >();
  for (const position of surface.openPositions) {
    for (const principle of position.drivingPrinciples) {
      const cid = principle.conclusionId;
      const row = tally.get(cid) ?? { snippet: principle.snippet, weightSum: 0, count: 0 };
      row.weightSum += principle.weight;
      row.count += 1;
      if (!row.snippet && principle.snippet) row.snippet = principle.snippet;
      tally.set(cid, row);
    }
  }
  return Array.from(tally.entries())
    .sort(
      ([, a], [, b]) => b.count - a.count || b.weightSum - a.weightSum,
    )
    .slice(0, 5)
    .map(([conclusionId, row]) => ({
      conclusionId,
      snippet: row.snippet,
      weight: row.weightSum / Math.max(row.count, 1),
      positionCount: row.count,
    }));
}
