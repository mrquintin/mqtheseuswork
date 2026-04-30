"use client";

import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import type { PublicForecast } from "@/lib/forecastsTypes";

export type AuthorizationRow = {
  edge: number | null;
  kellyStakeUsd: number;
  marketPrice: number | null;
  prediction: PublicForecast;
};

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    style: "currency",
  }).format(value);
}

function probability(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return `${Math.round(value * 100)}%`;
}

function signed(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`;
}

export function kellyStakeUsd({
  bankrollUsd,
  kellyFraction,
  marketPrice,
  maxStakeUsd,
  modelProbability,
}: {
  bankrollUsd: number;
  kellyFraction: number;
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
    kellyFraction <= 0 ||
    maxStakeUsd <= 0
  ) {
    return 0;
  }
  const rawFraction = (modelProbability - marketPrice) / (1 - marketPrice);
  const fraction = Math.min(1, Math.max(0, rawFraction));
  return Math.min(maxStakeUsd, fraction * kellyFraction * bankrollUsd);
}

async function authorizePrediction(predictionId: string): Promise<void> {
  const res = await fetch(`/api/forecasts/operator/${encodeURIComponent(predictionId)}/authorize-live`, {
    body: JSON.stringify({}),
    headers: { "content-type": "application/json" },
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `authorize-live failed with ${res.status}`);
  }
}

export default function PendingAuthorizations({
  liveTradingEnabled,
  rows,
}: {
  liveTradingEnabled: boolean;
  rows: AuthorizationRow[];
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <section className="portal-card" style={{ padding: "1rem" }}>
      <div style={{ alignItems: "center", display: "flex", justifyContent: "space-between", gap: "1rem" }}>
        <div>
          <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>Pending live authorizations</h2>
          <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.25rem 0 0" }}>
            Predictions not yet promoted into live-betting eligibility.
          </p>
        </div>
      </div>

      {error ? <p role="alert" style={{ color: "var(--ember)" }}>{error}</p> : null}

      <div style={{ display: "grid", gap: "0.65rem", marginTop: "1rem" }}>
        {rows.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>No predictions are waiting for live authorization.</p>
        ) : (
          rows.map((row) => (
            <article
              key={row.prediction.id}
              style={{
                border: "1px solid rgba(232, 225, 211, 0.12)",
                borderRadius: 6,
                padding: "0.85rem",
              }}
            >
              <h3 style={{ color: "var(--parchment)", fontSize: "1rem", margin: "0 0 0.55rem" }}>
                {row.prediction.headline}
              </h3>
              <div
                className="mono"
                style={{
                  color: "var(--parchment-dim)",
                  display: "grid",
                  fontSize: "0.68rem",
                  gap: "0.35rem",
                  gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                }}
              >
                <span>Model {probability(row.prediction.probability_yes)}</span>
                <span>Market {probability(row.marketPrice)}</span>
                <span>Edge {signed(row.edge)}</span>
                <span>Kelly {money(row.kellyStakeUsd)}</span>
              </div>
              <div style={{ marginTop: "0.8rem" }}>
                {liveTradingEnabled ? (
                  <button
                    className="btn"
                    disabled={busyId === row.prediction.id}
                    onClick={async () => {
                      setBusyId(row.prediction.id);
                      setError(null);
                      try {
                        await authorizePrediction(row.prediction.id);
                      } catch (err) {
                        setError(err instanceof Error ? err.message : "Authorization failed");
                      } finally {
                        setBusyId(null);
                      }
                    }}
                    type="button"
                  >
                    <ShieldCheck aria-hidden="true" size={15} />{" "}
                    {busyId === row.prediction.id ? "Authorizing..." : "Authorize live betting on this prediction"}
                  </button>
                ) : (
                  <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem" }}>
                    Live trading disabled server-side.
                  </span>
                )}
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
