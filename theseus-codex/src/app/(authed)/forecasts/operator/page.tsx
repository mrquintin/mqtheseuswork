import Link from "next/link";
import { redirect } from "next/navigation";

import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { normalizeDecisionTrace } from "@/lib/forecastPortfolioData";
import { getForecast, getPortfolioSummary, listForecasts } from "@/lib/forecastsApi";
import { getOperatorSetupStatus, listOperatorLiveBets } from "@/lib/forecastsOperatorApi";
import type {
  DecisionTrace,
  OperatorBet,
  OperatorKillSwitchState,
  OperatorSetupStatus,
  PortfolioSummary,
  PublicForecast,
} from "@/lib/forecastsTypes";
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

async function decisionTracesByPrediction(predictionIds: string[]): Promise<Record<string, DecisionTrace>> {
  const unique = Array.from(new Set(predictionIds.filter(Boolean)));
  if (unique.length === 0) return {};
  try {
    const rows = await db.forecastTrace.findMany({
      select: { modelOutput: true, predictionId: true },
      where: { predictionId: { in: unique } },
    });
    const out: Record<string, DecisionTrace> = {};
    for (const row of rows) {
      const trace = normalizeDecisionTrace(row.modelOutput);
      if (trace) out[row.predictionId] = trace;
    }
    return out;
  } catch (error) {
    console.error("operator_decision_trace_fetch_failed", error);
    return {};
  }
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

  const [forecastResult, betsResult, summaryResult, setupResult] = await Promise.allSettled([
    listForecasts({ limit: 100, status: "PUBLISHED" }),
    fetchLiveBets(200),
    getPortfolioSummary(),
    getOperatorSetupStatus(),
  ]);

  const forecasts = forecastResult.status === "fulfilled" ? forecastResult.value.items : [];
  const liveBets = betsResult.status === "fulfilled" ? betsResult.value : [];
  const setupStatus: OperatorSetupStatus | null =
    setupResult.status === "fulfilled" ? setupResult.value : null;
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
  const decisionTraces = await decisionTracesByPrediction([
    ...forecasts.map((f) => f.id),
    ...liveBets.map((b) => b.prediction_id),
  ]);
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

      <SetupReadinessBanner status={setupStatus} />
      <SetupChecklist status={setupStatus} />

      <OperatorSection
        id="op-decision-candidates"
        subtitle="published predictions awaiting live authorization, with their decision traces"
        title="Decision candidates"
      >
        <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <PendingAuthorizations
            decisionTracesByPredictionId={decisionTraces}
            liveTradingEnabled={liveTradingEnabled}
            rows={authorizationRows(forecasts, {
              bankrollUsd: liveBalanceUsd || summary.paper_balance_usd,
              maxStakeUsd,
            })}
          />
          <KillSwitchPanel initialState={killSwitchState(summary)} />
        </div>
      </OperatorSection>

      <OperatorSection
        id="op-live-authorizations"
        subtitle="authorized bets awaiting per-bet operator confirmation against the eight safety gates"
        title="Live authorizations and confirmations"
      >
        <PendingConfirmations
          context={confirmContext}
          decisionTracesByPredictionId={decisionTraces}
          predictionsById={predictionsById}
          rows={pendingConfirmations}
        />
      </OperatorSection>

      <OperatorSection
        id="op-order-ledger"
        subtitle="external order ids and exchange status — founder-authenticated surface"
        title="Order ledger"
      >
        <LiveBetLedger
          decisionTracesByPredictionId={decisionTraces}
          initialRows={liveBets}
          predictionsById={predictionsById}
        />
      </OperatorSection>
    </main>
  );
}

function OperatorSection({
  children,
  id,
  subtitle,
  title,
}: {
  children: React.ReactNode;
  id: string;
  subtitle: string;
  title: string;
}) {
  return (
    <section aria-labelledby={id}>
      <header style={{ display: "grid", gap: "0.2rem", margin: "0.4rem 0 0.75rem" }}>
        <h2
          id={id}
          style={{
            color: "var(--amber)",
            fontFamily: "'Cinzel', serif",
            fontSize: "1.05rem",
            letterSpacing: "0.06em",
            margin: 0,
          }}
        >
          {title}
        </h2>
        <p
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.66rem",
            letterSpacing: "0.1em",
            margin: 0,
          }}
        >
          {subtitle}
        </p>
      </header>
      {children}
    </section>
  );
}

function SetupChecklist({ status }: { status: OperatorSetupStatus | null }) {
  if (status === null) return null;
  const items: { done: boolean; label: string }[] = [];
  items.push({
    done: status.live_trading_enabled,
    label: "Enable live trading server-side (FORECASTS_LIVE_TRADING_ENABLED=true)",
  });
  items.push({
    done: status.exchanges.polymarket.configured || status.exchanges.kalshi.configured,
    label: "Wire credentials for at least one exchange (Polymarket or Kalshi)",
  });
  items.push({
    done: status.risk_limits.max_stake_configured,
    label: "Set a per-bet max stake (FORECASTS_MAX_STAKE_USD)",
  });
  items.push({
    done: status.risk_limits.max_daily_loss_configured,
    label: "Set a daily-loss ceiling (FORECASTS_MAX_DAILY_LOSS_USD)",
  });
  items.push({
    done: status.scheduler.present && status.scheduler.fresh,
    label: "Forecast scheduler running and fresh",
  });
  items.push({
    done: !status.kill_switch.engaged,
    label: "Kill switch clear",
  });
  items.push({
    done: status.readiness.monitoring_active,
    label: "Market monitoring is active",
  });
  if (status.readiness.blockers.length > 0) {
    for (const blocker of status.readiness.blockers) {
      items.push({ done: false, label: `Resolve blocker: ${blocker}` });
    }
  }
  const allDone = items.every((item) => item.done);
  if (allDone) return null;
  return (
    <section
      aria-labelledby="op-setup-checklist"
      data-testid="operator-setup-checklist"
      style={{
        border: "1px solid rgba(205, 151, 67, 0.45)",
        borderRadius: 6,
        padding: "0.85rem 1rem",
      }}
    >
      <h2
        id="op-setup-checklist"
        style={{
          color: "var(--amber)",
          fontFamily: "'Cinzel', serif",
          fontSize: "1rem",
          letterSpacing: "0.05em",
          margin: 0,
        }}
      >
        What to configure next
      </h2>
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.78rem", margin: "0.35rem 0 0.6rem" }}>
        The algorithm will not authorize live trading until every item below is checked.
      </p>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {items.map((item) => (
          <li
            key={item.label}
            data-checklist-done={item.done ? "true" : "false"}
            style={{ display: "flex", gap: "0.5rem", padding: "0.22rem 0" }}
          >
            <span
              aria-hidden="true"
              style={{
                color: item.done ? "rgba(127, 196, 143, 0.95)" : "var(--ember)",
                fontFamily: "'IBM Plex Mono', monospace",
                width: "1.3rem",
              }}
            >
              {item.done ? "[x]" : "[ ]"}
            </span>
            <span
              style={{
                color: item.done ? "var(--parchment)" : "var(--parchment-dim)",
                fontSize: "0.82rem",
              }}
            >
              {item.label}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SetupReadinessBanner({ status }: { status: OperatorSetupStatus | null }) {
  if (status === null) {
    return (
      <div
        role="status"
        style={{
          alignItems: "center",
          border: "1px solid rgba(205, 151, 67, 0.45)",
          color: "var(--parchment)",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.6rem",
          justifyContent: "space-between",
          padding: "0.7rem 0.9rem",
        }}
      >
        <span>
          Setup status unavailable — verify the forecasts API is reachable and{" "}
          <code>FORECASTS_OPERATOR_SECRET</code> is configured.
        </span>
        <Link className="mono" href="/forecasts/setup" style={{ color: "var(--amber)" }}>
          open setup →
        </Link>
      </div>
    );
  }
  const r = status.readiness;
  const allReady = r.monitoring_active && r.ready_for_live_candidates && r.ready_for_live_orders;
  const borderColor = allReady
    ? "rgba(126, 168, 58, 0.55)"
    : r.monitoring_active
      ? "rgba(205, 151, 67, 0.55)"
      : "rgba(185, 92, 92, 0.55)";
  const pill = (label: string, ok: boolean) => (
    <span
      className="mono"
      style={{
        border: `1px solid ${ok ? "var(--success)" : "var(--ember)"}`,
        borderRadius: "0.2rem",
        color: ok ? "var(--success)" : "var(--ember)",
        fontSize: "0.66rem",
        letterSpacing: "0.12em",
        padding: "0.15rem 0.45rem",
      }}
    >
      {label}: {ok ? "READY" : "NOT READY"}
    </span>
  );
  return (
    <div
      role="status"
      style={{
        alignItems: "center",
        border: `1px solid ${borderColor}`,
        display: "flex",
        flexWrap: "wrap",
        gap: "0.55rem",
        justifyContent: "space-between",
        padding: "0.7rem 0.9rem",
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
        {pill("Monitoring", r.monitoring_active)}
        {pill("Live candidates", r.ready_for_live_candidates)}
        {pill("Live orders", r.ready_for_live_orders)}
        <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
          mode: {status.trading_mode}
        </span>
      </div>
      <Link className="mono" href="/forecasts/setup" style={{ color: "var(--amber)", letterSpacing: "0.1em" }}>
        setup →
      </Link>
    </div>
  );
}
