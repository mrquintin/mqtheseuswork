import type { ForecastBetSide, ForecastSource } from "@prisma/client";

import { db } from "@/lib/db";

export type TracePrinciple = {
  conclusionId: string;
  weight: number;
  snippet: string;
};

export type TraceGateResult = {
  gateName: string;
  passed: boolean;
  reason: string;
};

export type PortfolioMode = "PAPER" | "LIVE" | "GATE-BLOCKED";

export type PortfolioModeState = {
  mode: PortfolioMode;
  liveTradingEnabled: boolean;
  failedGates: TraceGateResult[];
};

export type PortfolioKpis = {
  openPositions: number;
  realizedPaperPnl: number;
  unrealizedPaperPnl: number;
  runningBrier: number | null;
  hitRate: number | null;
};

export type PortfolioPositionRow = {
  betId: string;
  predictionId: string;
  mode: string;
  marketTitle: string;
  marketUrl: string | null;
  side: string;
  sizeUsd: number;
  avgPrice: number;
  currentImpliedProb: number | null;
  drivingPrinciples: TracePrinciple[];
  gateResults: TraceGateResult[];
  lastUpdated: Date;
};

export type ResolvedPositionRow = {
  betId: string;
  predictionId: string;
  marketTitle: string;
  marketUrl: string | null;
  outcome: string;
  ourSide: string;
  pnlUsd: number | null;
  reasoningHref: string;
  resolvedAt: Date | null;
};

export type PipelineCandidateRow = {
  marketId: string;
  marketTitle: string;
  marketUrl: string | null;
  source: string;
  category: string | null;
  drivingPrinciples: TracePrinciple[];
  gateResults: TraceGateResult[];
  gateState: string;
  lastUpdated: Date;
};

export type WatchedMarketRow = {
  id: string;
  source: string;
  url: string;
  externalId: string | null;
  status: string;
  createdAt: Date;
  lastConsideredAt: Date | null;
};

export type WatchingState = {
  polymarketCategories: string[];
  kalshiCategories: string[];
  scannedThisWeek: number;
  watchedMarkets: WatchedMarketRow[];
};

export type ForecastPortfolioSurface = {
  mode: PortfolioModeState;
  kpis: PortfolioKpis;
  openPositions: PortfolioPositionRow[];
  recentlyResolved: ResolvedPositionRow[];
  pipeline: PipelineCandidateRow[];
  watching: WatchingState;
};

type JsonRecord = Record<string, unknown>;

function csvEnv(name: string): string[] {
  return (process.env[name] ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function decimalNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: unknown): number {
  return decimalNumber(value) ?? 0;
}

function jsonRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function jsonArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function normalizeTracePrinciples(value: unknown): TracePrinciple[] {
  return jsonArray(value)
    .map((item) => jsonRecord(item))
    .map((item) => ({
      conclusionId: String(item.conclusionId ?? item.conclusion_id ?? ""),
      snippet: String(item.snippet ?? ""),
      weight: decimalNumber(item.weight) ?? 0,
    }))
    .filter((item) => item.conclusionId.length > 0);
}

export function normalizeGateResults(value: unknown): TraceGateResult[] {
  return jsonArray(value)
    .map((item) => jsonRecord(item))
    .map((item) => ({
      gateName: String(item.gateName ?? item.gate_name ?? ""),
      passed: Boolean(item.passed),
      reason: String(item.reason ?? ""),
    }))
    .filter((item) => item.gateName.length > 0);
}

function liveTradingEnabled(): boolean {
  return process.env.FORECASTS_LIVE_TRADING_ENABLED?.trim().toLowerCase() === "true";
}

function modeState(args: {
  killSwitchEngaged: boolean;
  killSwitchReason: string | null;
}): PortfolioModeState {
  if (!liveTradingEnabled()) {
    return { mode: "PAPER", liveTradingEnabled: false, failedGates: [] };
  }

  const failedGates: TraceGateResult[] = [];
  const hasPolymarket = Boolean(process.env.POLYMARKET_PRIVATE_KEY?.trim());
  const hasKalshi = Boolean(
    process.env.KALSHI_API_KEY_ID?.trim() &&
      (process.env.KALSHI_API_PRIVATE_KEY?.trim() ||
        process.env.KALSHI_PRIVATE_KEY_PEM?.trim()),
  );

  if (!hasPolymarket && !hasKalshi) {
    failedGates.push({
      gateName: "exchange_credentials_configured",
      passed: false,
      reason: "no live exchange credentials are configured",
    });
  }

  if (args.killSwitchEngaged) {
    failedGates.push({
      gateName: "kill_switch_clear",
      passed: false,
      reason: args.killSwitchReason || "portfolio kill switch is engaged",
    });
  }

  return {
    mode: failedGates.length > 0 ? "GATE-BLOCKED" : "LIVE",
    liveTradingEnabled: true,
    failedGates,
  };
}

function marketUrl(market: {
  externalId: string;
  rawPayload: unknown;
  source: ForecastSource | string;
}): string | null {
  const raw = jsonRecord(market.rawPayload);
  for (const key of ["url", "market_url", "source_url"]) {
    const value = raw[key];
    if (typeof value === "string" && /^https?:\/\//.test(value)) return value;
  }
  if (!market.externalId) return null;
  if (String(market.source) === "POLYMARKET") {
    return `https://polymarket.com/event/${market.externalId}`;
  }
  if (String(market.source) === "KALSHI") {
    return `https://kalshi.com/markets/${market.externalId}`;
  }
  return null;
}

function currentSidePrice(
  market: { currentYesPrice: unknown; currentNoPrice: unknown } | null,
  side: ForecastBetSide | string,
): number | null {
  if (!market) return null;
  return String(side) === "NO"
    ? decimalNumber(market.currentNoPrice)
    : decimalNumber(market.currentYesPrice);
}

function paperUnrealizedPnl(bet: {
  entryPrice: unknown;
  mode: string;
  side: ForecastBetSide | string;
  stakeUsd: unknown;
  status: string;
  prediction: { market: { currentYesPrice: unknown; currentNoPrice: unknown } | null } | null;
}): number {
  if (bet.mode !== "PAPER" || bet.status !== "FILLED") return 0;
  const entry = decimalNumber(bet.entryPrice);
  const current = currentSidePrice(bet.prediction?.market ?? null, bet.side);
  const stake = money(bet.stakeUsd);
  if (!entry || !current || stake <= 0) return 0;
  const shares = stake / entry;
  return shares * current - stake;
}

function gateState(gates: TraceGateResult[]): string {
  const failed = gates.find((gate) => !gate.passed);
  if (failed) return `would fail ${failed.gateName}: ${failed.reason}`;
  return "paper-ready";
}

export async function getForecastPortfolioSurface(
  organizationId: string,
): Promise<ForecastPortfolioSurface> {
  const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);

  const [
    portfolioState,
    openBets,
    settledPaperBets,
    resolvedRows,
    openMarkets,
    scannedThisWeek,
    watchedMarkets,
  ] = await Promise.all([
    db.forecastPortfolioState.findUnique({ where: { organizationId } }),
    db.forecastBet.findMany({
      where: {
        organizationId,
        status: { in: ["PENDING", "AUTHORIZED", "CONFIRMED", "SUBMITTED", "FILLED"] },
      },
      include: {
        prediction: {
          include: {
            market: true,
            trace: true,
          },
        },
      },
      orderBy: { createdAt: "desc" },
      take: 100,
    }),
    db.forecastBet.findMany({
      where: {
        organizationId,
        mode: "PAPER",
        status: "SETTLED",
      },
      orderBy: { settledAt: "desc" },
      take: 200,
    }),
    db.forecastBet.findMany({
      where: {
        organizationId,
        status: "SETTLED",
      },
      include: {
        prediction: {
          include: {
            market: true,
            resolution: true,
          },
        },
      },
      orderBy: { settledAt: "desc" },
      take: 25,
    }),
    db.forecastMarket.findMany({
      where: {
        organizationId,
        status: "OPEN",
      },
      include: {
        predictions: {
          include: { trace: true },
          orderBy: { createdAt: "desc" },
          take: 1,
        },
      },
      orderBy: { updatedAt: "desc" },
      take: 30,
    }),
    db.forecastMarket.count({
      where: {
        organizationId,
        updatedAt: { gte: weekAgo },
      },
    }),
    db.watchedMarket.findMany({
      where: { organizationId },
      orderBy: { createdAt: "desc" },
      take: 50,
    }),
  ]);

  const realizedPaperPnl = settledPaperBets.reduce(
    (sum, bet) => sum + money(bet.settlementPnlUsd),
    0,
  );
  const wins = settledPaperBets.filter((bet) => money(bet.settlementPnlUsd) > 0).length;
  const brierScores = resolvedRows
    .map((bet) => bet.prediction?.resolution?.brierScore)
    .map(decimalNumber)
    .filter((value): value is number => value !== null);

  return {
    mode: modeState({
      killSwitchEngaged: Boolean(portfolioState?.killSwitchEngaged),
      killSwitchReason: portfolioState?.killSwitchReason ?? null,
    }),
    kpis: {
      hitRate: settledPaperBets.length > 0 ? wins / settledPaperBets.length : null,
      openPositions: openBets.length,
      realizedPaperPnl,
      runningBrier:
        brierScores.length > 0
          ? brierScores.reduce((sum, value) => sum + value, 0) / brierScores.length
          : portfolioState?.meanBrier90d ?? null,
      unrealizedPaperPnl: openBets.reduce((sum, bet) => sum + paperUnrealizedPnl(bet), 0),
    },
    openPositions: openBets.map((bet) => {
      const prediction = bet.prediction;
      const market = prediction?.market ?? null;
      const trace = prediction?.trace ?? null;
      return {
        avgPrice: money(bet.entryPrice),
        betId: bet.id,
        currentImpliedProb: currentSidePrice(market, bet.side),
        drivingPrinciples: normalizeTracePrinciples(trace?.principlesUsed),
        gateResults: normalizeGateResults(trace?.gateResults),
        lastUpdated: prediction?.updatedAt ?? bet.createdAt,
        marketTitle: market?.title ?? trace?.marketTitle ?? prediction?.headline ?? "Unknown market",
        marketUrl: market ? marketUrl(market) : null,
        mode: bet.mode,
        predictionId: bet.predictionId,
        side: bet.side,
        sizeUsd: money(bet.stakeUsd),
      };
    }),
    pipeline: openMarkets.map((market) => {
      const prediction = market.predictions[0] ?? null;
      const trace = prediction?.trace ?? null;
      const gates = normalizeGateResults(trace?.gateResults);
      const gateResults =
        gates.length > 0
          ? gates
          : [
              {
                gateName: "retrieval_queue",
                passed: true,
                reason: "awaiting the next forecast generator cycle",
              },
            ];
      return {
        category: market.category,
        drivingPrinciples: normalizeTracePrinciples(trace?.principlesUsed),
        gateResults,
        gateState: gateState(gateResults),
        lastUpdated: market.updatedAt,
        marketId: market.id,
        marketTitle: market.title,
        marketUrl: marketUrl(market),
        source: market.source,
      };
    }),
    recentlyResolved: resolvedRows.map((bet) => {
      const prediction = bet.prediction;
      const market = prediction?.market ?? null;
      return {
        betId: bet.id,
        marketTitle: market?.title ?? prediction?.headline ?? "Unknown market",
        marketUrl: market ? marketUrl(market) : null,
        outcome: prediction?.resolution?.marketOutcome ?? "UNKNOWN",
        ourSide: bet.side,
        pnlUsd: decimalNumber(bet.settlementPnlUsd),
        predictionId: bet.predictionId,
        reasoningHref: `/forecasts/${bet.predictionId}`,
        resolvedAt: prediction?.resolution?.resolvedAt ?? bet.settledAt,
      };
    }),
    watching: {
      kalshiCategories: csvEnv("FORECASTS_KALSHI_CATEGORIES"),
      polymarketCategories: csvEnv("FORECASTS_POLYMARKET_CATEGORIES"),
      scannedThisWeek,
      watchedMarkets: watchedMarkets.map((row) => ({
        createdAt: row.createdAt,
        externalId: row.externalId,
        id: row.id,
        lastConsideredAt: row.lastConsideredAt,
        source: row.source,
        status: row.status,
        url: row.url,
      })),
    },
  };
}
