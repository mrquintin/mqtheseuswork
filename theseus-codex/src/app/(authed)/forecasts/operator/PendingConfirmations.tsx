"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";

import type { OperatorBet, PublicForecast } from "@/lib/forecastsTypes";

export type ConfirmGateCode =
  | "DISABLED"
  | "NOT_CONFIGURED"
  | "NOT_AUTHORIZED"
  | "STAKE_OVER_CEILING"
  | "DAILY_LOSS_OVER_CEILING"
  | "KILL_SWITCH_ENGAGED"
  | "INSUFFICIENT_BALANCE";

export type ConfirmGateContext = {
  configuredExchanges: string[];
  dailyLossUsd: number | null;
  killSwitchEngaged: boolean;
  liveBalanceUsd: number | null;
  liveTradingEnabled: boolean;
  maxDailyLossUsd: number | null;
  maxStakeUsd: number | null;
};

export const CONFIRM_GATE_MESSAGES: Record<ConfirmGateCode, string> = {
  DAILY_LOSS_OVER_CEILING: "Daily loss is above the configured ceiling.",
  DISABLED: "Live trading is disabled by the server environment.",
  INSUFFICIENT_BALANCE: "Live balance is below the proposed stake.",
  KILL_SWITCH_ENGAGED: "The portfolio kill switch is engaged.",
  NOT_AUTHORIZED: "The parent prediction has no live_authorized_at timestamp.",
  NOT_CONFIGURED: "Live credentials are not configured for this exchange.",
  STAKE_OVER_CEILING: "The proposed stake exceeds the configured max stake.",
};

function money(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    style: "currency",
  }).format(value);
}

function price(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return value.toFixed(3);
}

export function failingConfirmGates({
  bet,
  context,
  prediction,
}: {
  bet: OperatorBet;
  context: ConfirmGateContext;
  prediction: PublicForecast | null;
}): ConfirmGateCode[] {
  const failures: ConfirmGateCode[] = [];
  if (!context.liveTradingEnabled) failures.push("DISABLED");
  if (!context.configuredExchanges.includes(bet.exchange)) failures.push("NOT_CONFIGURED");
  if (!prediction?.live_authorized_at) failures.push("NOT_AUTHORIZED");
  if (context.maxStakeUsd !== null && bet.stake_usd > context.maxStakeUsd) failures.push("STAKE_OVER_CEILING");
  if (
    context.dailyLossUsd !== null &&
    context.maxDailyLossUsd !== null &&
    context.dailyLossUsd > context.maxDailyLossUsd
  ) {
    failures.push("DAILY_LOSS_OVER_CEILING");
  }
  if (context.killSwitchEngaged) failures.push("KILL_SWITCH_ENGAGED");
  if (context.liveBalanceUsd !== null && context.liveBalanceUsd < bet.stake_usd) failures.push("INSUFFICIENT_BALANCE");
  return failures;
}

function gateTooltip(codes: ConfirmGateCode[]): string {
  return codes.map((code) => `${code}: ${CONFIRM_GATE_MESSAGES[code]}`).join(" ");
}

async function confirmBet(predictionId: string, betId: string): Promise<void> {
  const res = await fetch(
    `/api/forecasts/operator/${encodeURIComponent(predictionId)}/bets/${encodeURIComponent(betId)}/confirm`,
    {
      body: JSON.stringify({}),
      headers: { "content-type": "application/json" },
      method: "POST",
    },
  );
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `confirm failed with ${res.status}`);
  }
}

async function cancelBet(predictionId: string, betId: string): Promise<void> {
  const res = await fetch(
    `/api/forecasts/operator/${encodeURIComponent(predictionId)}/bets/${encodeURIComponent(betId)}/cancel`,
    {
      body: JSON.stringify({}),
      headers: { "content-type": "application/json" },
      method: "POST",
    },
  );
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `cancel failed with ${res.status}`);
  }
}

export default function PendingConfirmations({
  context,
  predictionsById,
  rows,
}: {
  context: ConfirmGateContext;
  predictionsById: Record<string, PublicForecast>;
  rows: OperatorBet[];
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [cancelledIds, setCancelledIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const visibleRows = rows.filter((row) => !cancelledIds.has(row.id));

  return (
    <section className="portal-card" style={{ padding: "1rem" }}>
      <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>Pending bet confirmations</h2>
      <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.25rem 0 0" }}>
        AUTHORIZED live bets requiring per-bet operator confirmation.
      </p>
      {error ? <p role="alert" style={{ color: "var(--ember)" }}>{error}</p> : null}

      <div style={{ display: "grid", gap: "0.65rem", marginTop: "1rem" }}>
        {visibleRows.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>No live bets are waiting for confirmation.</p>
        ) : (
          visibleRows.map((bet) => {
            const prediction = predictionsById[bet.prediction_id] ?? null;
            const failures = failingConfirmGates({ bet, context, prediction });
            const disabled = failures.length > 0 || busyId === bet.id;
            return (
              <article
                key={bet.id}
                style={{
                  border: "1px solid rgba(232, 225, 211, 0.12)",
                  borderRadius: 6,
                  padding: "0.85rem",
                }}
              >
                <h3 style={{ color: "var(--parchment)", fontSize: "1rem", margin: "0 0 0.55rem" }}>
                  {prediction?.headline ?? bet.prediction_id}
                </h3>
                <div
                  className="mono"
                  style={{
                    color: "var(--parchment-dim)",
                    display: "grid",
                    fontSize: "0.68rem",
                    gap: "0.35rem",
                    gridTemplateColumns: "repeat(auto-fit, minmax(125px, 1fr))",
                  }}
                >
                  <span>{bet.exchange}</span>
                  <span>{bet.side} @ {price(bet.entry_price)}</span>
                  <span>Stake {money(bet.stake_usd)}</span>
                  <span>Status {bet.status}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.7rem" }}>
                  {(["DISABLED", "NOT_CONFIGURED", "STAKE_OVER_CEILING", "DAILY_LOSS_OVER_CEILING", "KILL_SWITCH_ENGAGED", "INSUFFICIENT_BALANCE"] as ConfirmGateCode[]).map((code) => (
                    <span
                      className="mono"
                      data-gate-code={code}
                      data-gate-state={failures.includes(code) ? "fail" : "pass"}
                      key={code}
                      style={{
                        border: `1px solid ${failures.includes(code) ? "rgba(185, 92, 92, 0.65)" : "rgba(126, 166, 133, 0.55)"}`,
                        borderRadius: 999,
                        color: failures.includes(code) ? "var(--ember)" : "rgba(160, 211, 170, 0.9)",
                        fontSize: "0.58rem",
                        padding: "0.18rem 0.42rem",
                      }}
                    >
                      {code}
                    </span>
                  ))}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.55rem", marginTop: "0.85rem" }}>
                  {prediction?.live_authorized_at ? (
                    <button
                      className="btn"
                      data-confirm-bet-id={bet.id}
                      disabled={disabled}
                      onClick={async () => {
                        setBusyId(bet.id);
                        setError(null);
                        try {
                          await confirmBet(bet.prediction_id, bet.id);
                        } catch (err) {
                          setError(err instanceof Error ? err.message : "Confirmation failed");
                        } finally {
                          setBusyId(null);
                        }
                      }}
                      title={failures.length ? gateTooltip(failures) : "All live-bet confirmation gates pass."}
                      type="button"
                    >
                      <CheckCircle2 aria-hidden="true" size={15} /> {busyId === bet.id ? "Confirming..." : "CONFIRM"}
                    </button>
                  ) : (
                    <span className="mono" data-confirm-hidden-reason="NOT_AUTHORIZED" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem" }}>
                      Confirm hidden until prediction live_authorized_at is present.
                    </span>
                  )}
                  <button
                    className="btn"
                    data-cancel-bet-id={bet.id}
                    disabled={busyId === bet.id}
                    onClick={async () => {
                      setBusyId(bet.id);
                      setError(null);
                      try {
                        await cancelBet(bet.prediction_id, bet.id);
                        setCancelledIds((current) => new Set(current).add(bet.id));
                      } catch (err) {
                        setError(err instanceof Error ? err.message : "Cancellation failed");
                      } finally {
                        setBusyId(null);
                      }
                    }}
                    title="Cancel this authorized live bet before exchange submission."
                    type="button"
                  >
                    <XCircle aria-hidden="true" size={15} /> {busyId === bet.id ? "Cancelling..." : "CANCEL"}
                  </button>
                </div>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}
