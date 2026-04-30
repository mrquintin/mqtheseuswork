import { redirect } from "next/navigation";

import { getFounder } from "@/lib/auth";
import { getForecast, getPortfolioSummary, listForecasts } from "@/lib/forecastsApi";
import { listOperatorLiveBets } from "@/lib/forecastsOperatorApi";
import type { OperatorBet, OperatorKillSwitchState, PortfolioSummary, PublicForecast } from "@/lib/forecastsTypes";
import { canWrite } from "@/lib/roles";

import KillSwitchPanel from "./KillSwitchPanel";
import LiveBetLedger from "./LiveBetLedger";
import PendingAuthorizations, { type AuthorizationRow } from "./PendingAuthorizations";
import PendingConfirmations, { type ConfirmGateContext } from "./PendingConfirmations";

export const dynamic = "force-dynamic";

const DEFAULT_MAX_STAKE_USD = 0;
const DEFAULT_KELLY_FRACTION = 0.25;

function envFlag(name: string): boolean {
  return process.env[name]?.trim().toLowerCase() === "true";
}

function envNumber(name: string): number | null {
  const raw = process.env[name]?.trim();
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function numericField(row: object | null | undefined, ...keys: string[]): number | null {
  if (!row) return null;
  for (const key of keys) {
    const value = (row as Record<string, unknown>)[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function marketPrice(prediction: PublicForecast): number | null {
  const price = prediction.market?.current_yes_price;
  return typeof price === "number" && Number.isFinite(price) ? price : null;
}

function modelEdge(prediction: PublicForecast): number | null {
  const p = prediction.probability_yes;
  const price = marketPrice(prediction);
  if (p === null || price === null || !Number.isFinite(p)) return null;
  return p - price;
}

function kellyStakeUsd({
  bankrollUsd,
  marketPrice,
  maxStakeUsd,
  modelProbability,
}: {
  bankrollUsd: number;
  marketPrice: number | null;
  maxStakeUsd: number;
  modelProbability: number | null;
}): number {
  if (
    marketPrice === null ||
    modelProbability === null ||
    !Number.isFinite(marketPrice) ||
    !Number.isFinite(modelProbability) ||
    marketPrice <= 0 ||
    marketPrice >= 1 ||
    bankrollUsd <= 0 ||
    maxStakeUsd <= 0
  ) {
    return 0;
  }
  const rawFraction = (modelProbability - marketPrice) / (1 - marketPrice);
  const fraction = Math.min(1, Math.max(0, rawFraction));
  return Math.min(maxStakeUsd, fraction * DEFAULT_KELLY_FRACTION * bankrollUsd);
}

async function fetchLiveBets(limit = 200): Promise<OperatorBet[]> {
  const out: OperatorBet[] = [];
  let offset = 0;
  while (out.length < limit) {
    const response = await listOperatorLiveBets({ limit: Math.min(100, limit - out.length), offset });
    out.push(...response.items);
    if (response.next_offset === null || response.items.length === 0) break;
    offset = response.next_offset;
  }
  return out;
}

async function predictionsForBets(seed: PublicForecast[], bets: OperatorBet[]): Promise<Record<string, PublicForecast>> {
  const byId: Record<string, PublicForecast> = {};
  for (const prediction of seed) {
    byId[prediction.id] = prediction;
  }
  const missing = Array.from(new Set(bets.map((bet) => bet.prediction_id).filter((id) => !byId[id])));
  await Promise.all(
    missing.map(async (id) => {
      try {
        byId[id] = await getForecast(id);
      } catch (error) {
        console.error("operator_forecast_fetch_failed", id, error);
      }
    }),
  );
  return byId;
}

function authorizationRows(
  forecasts: PublicForecast[],
  options: {
    bankrollUsd: number;
    maxStakeUsd: number;
  },
): AuthorizationRow[] {
  return forecasts
    .filter((prediction) => prediction.status === "PUBLISHED")
    .filter((prediction) => prediction.live_authorized_at === null)
    .map((prediction) => {
      const price = marketPrice(prediction);
      return {
        edge: modelEdge(prediction),
        kellyStakeUsd: kellyStakeUsd({
          bankrollUsd: options.bankrollUsd,
          marketPrice: price,
          maxStakeUsd: options.maxStakeUsd,
          modelProbability: prediction.probability_yes,
        }),
        marketPrice: price,
        prediction,
      };
    });
}

function configuredExchanges(): string[] {
  const exchanges: string[] = [];
  if (process.env.POLYMARKET_PRIVATE_KEY?.trim()) exchanges.push("POLYMARKET");
  const kalshiPrivateKey = process.env.KALSHI_API_PRIVATE_KEY?.trim() || process.env.KALSHI_PRIVATE_KEY_PEM?.trim();
  if (process.env.KALSHI_API_KEY_ID?.trim() && kalshiPrivateKey) exchanges.push("KALSHI");
  return exchanges;
}

function killSwitchState(summary: PortfolioSummary): OperatorKillSwitchState {
  return {
    kill_switch_engaged: summary.kill_switch_engaged,
    kill_switch_reason: summary.kill_switch_reason,
    organization_id: summary.organization_id,
    updated_at: summary.updated_at,
  };
}

export default async function ForecastsOperatorPage() {
  const founder = await getFounder();
  if (!founder) redirect("/login");
  if (!canWrite(founder.role)) redirect("/dashboard");

  const liveTradingEnabled = envFlag("FORECASTS_LIVE_TRADING_ENABLED");
  const maxStakeUsd = envNumber("FORECASTS_MAX_STAKE_USD") ?? DEFAULT_MAX_STAKE_USD;
  const maxDailyLossUsd = envNumber("FORECASTS_MAX_DAILY_LOSS_USD");

  const [forecastResult, betsResult, summaryResult] = await Promise.allSettled([
    listForecasts({ limit: 100, status: "PUBLISHED" }),
    fetchLiveBets(200),
    getPortfolioSummary(),
  ]);

  const forecasts = forecastResult.status === "fulfilled" ? forecastResult.value.items : [];
  const liveBets = betsResult.status === "fulfilled" ? betsResult.value : [];
  const summary =
    summaryResult.status === "fulfilled"
      ? summaryResult.value
      : {
          calibration: [],
          kill_switch_engaged: false,
          kill_switch_reason: null,
          mean_brier_90d: null,
          organization_id: founder.organizationId,
          paper_balance_usd: 0,
          paper_pnl_curve: [],
          total_bets: 0,
          updated_at: null,
        };
  const fetchErrors = [
    forecastResult.status === "rejected" ? "forecasts" : null,
    betsResult.status === "rejected" ? "live bets" : null,
    summaryResult.status === "rejected" ? "portfolio summary" : null,
  ].filter(Boolean);

  const predictionsById = await predictionsForBets(forecasts, liveBets);
  const liveBalanceUsd = numericField(summary, "live_balance_usd", "liveBalanceUsd") ?? 0;
  const dailyLossUsd = numericField(summary, "daily_loss_usd", "dailyLossUsd");
  const pendingConfirmations = liveBets.filter((bet) => bet.status === "AUTHORIZED");
  const confirmContext: ConfirmGateContext = {
    configuredExchanges: configuredExchanges(),
    dailyLossUsd,
    killSwitchEngaged: summary.kill_switch_engaged,
    liveBalanceUsd,
    liveTradingEnabled,
    maxDailyLossUsd,
    maxStakeUsd: maxStakeUsd > 0 ? maxStakeUsd : null,
  };

  return (
    <main style={{ display: "grid", gap: "1rem", margin: "0 auto", maxWidth: 1180, padding: "1.5rem 1rem 3rem" }}>
      <section>
        <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.68rem", letterSpacing: "0.2em", margin: 0, textTransform: "uppercase" }}>
          Founder operator console
        </p>
        <h1 style={{ color: "var(--amber)", fontFamily: "'Cinzel Decorative', 'Cinzel', serif", margin: "0.2rem 0 0" }}>
          Forecasts operator
        </h1>
        <p style={{ color: "var(--parchment-dim)", lineHeight: 1.5, margin: "0.45rem 0 0", maxWidth: "62rem" }}>
          Live authorization, per-bet confirmation, exchange-order ledger, and emergency kill switch are intentionally separated from the public forecasts surface.
        </p>
      </section>

      {fetchErrors.length ? (
        <div role="alert" style={{ border: "1px solid rgba(185, 92, 92, 0.55)", color: "var(--ember)", padding: "0.8rem" }}>
          Operator data fetch incomplete: {fetchErrors.join(", ")}.
        </div>
      ) : null}

      <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        <PendingAuthorizations
          liveTradingEnabled={liveTradingEnabled}
          rows={authorizationRows(forecasts, {
            bankrollUsd: liveBalanceUsd || summary.paper_balance_usd,
            maxStakeUsd,
          })}
        />
        <KillSwitchPanel initialState={killSwitchState(summary)} />
      </div>

      <PendingConfirmations
        context={confirmContext}
        predictionsById={predictionsById}
        rows={pendingConfirmations}
      />
      <LiveBetLedger initialRows={liveBets} predictionsById={predictionsById} />
    </main>
  );
}
