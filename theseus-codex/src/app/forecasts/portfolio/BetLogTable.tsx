import Link from "next/link";
import type { CSSProperties } from "react";

import type { PublicBet } from "@/lib/forecastsTypes";

export type PortfolioBet = PublicBet & {
  headline?: string | null;
  prediction?: { headline?: string | null } | null;
  prediction_headline?: string | null;
};

interface BetLogTableProps {
  bets: PortfolioBet[];
  nextSince?: string | null;
  since?: string | null;
}

const cardStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.035)",
  border: "1px solid var(--forecasts-border)",
  borderRadius: "8px",
  padding: "1rem",
};

const titleStyle: CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.2rem",
  margin: 0,
};

function formatDate(ts: string): string {
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  return parsed.toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatUsd(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "open";
  const formatted = new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(Math.abs(value));
  return value < 0 ? `-${formatted}` : value > 0 ? `+${formatted}` : formatted;
}

function formatPrice(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "open";
  return value.toFixed(3);
}

function predictionHeadline(bet: PortfolioBet): string {
  return (
    bet.prediction_headline ||
    bet.headline ||
    bet.prediction?.headline ||
    `Prediction ${bet.prediction_id.slice(0, 8)}`
  );
}

export function paperBetsOnly(bets: PortfolioBet[]): PortfolioBet[] {
  return bets.filter((bet) => bet.mode.toUpperCase() === "PAPER");
}

export default function BetLogTable({ bets, nextSince, since }: BetLogTableProps) {
  const paperBets = paperBetsOnly(bets);

  return (
    <section aria-labelledby="bet-log-heading" style={cardStyle}>
      <div style={{ alignItems: "start", display: "flex", gap: "1rem", justifyContent: "space-between" }}>
        <div>
          <h2 id="bet-log-heading" style={titleStyle}>
            Paper bet log
          </h2>
          <p style={{ color: "var(--forecasts-parchment-dim)", fontSize: "0.82rem", margin: "0.35rem 0 0" }}>
            The public table intentionally excludes LIVE mode bets.
          </p>
        </div>
        {since ? (
          <Link
            href="/forecasts/portfolio"
            style={{
              color: "var(--forecasts-cool-gold)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.72rem",
              textDecoration: "none",
              textTransform: "uppercase",
            }}
          >
            Newest
          </Link>
        ) : null}
      </div>

      {paperBets.length === 0 ? (
        <div
          role="status"
          style={{
            border: "1px dashed var(--forecasts-border)",
            borderRadius: "6px",
            color: "var(--forecasts-parchment-dim)",
            marginTop: "0.85rem",
            padding: "1.1rem",
          }}
        >
          No paper bets in this page.
        </div>
      ) : (
        <div style={{ marginTop: "1rem", overflowX: "auto" }}>
          <table
            style={{
              borderCollapse: "collapse",
              fontSize: "0.84rem",
              minWidth: "900px",
              width: "100%",
            }}
          >
            <thead>
              <tr style={{ color: "var(--forecasts-muted)", fontFamily: "'IBM Plex Mono', monospace" }}>
                <th style={thStyle}>date</th>
                <th style={thStyle}>prediction</th>
                <th style={thStyle}>side</th>
                <th style={thStyle}>stakeUsd</th>
                <th style={thStyle}>entryPrice</th>
                <th style={thStyle}>exitPrice</th>
                <th style={thStyle}>P&amp;L</th>
                <th style={thStyle}>status</th>
              </tr>
            </thead>
            <tbody>
              {paperBets.map((bet) => {
                const pnl = bet.settlement_pnl_usd;
                return (
                  <tr key={bet.id} style={{ borderTop: "1px solid var(--forecasts-border)" }}>
                    <td style={tdStyle}>{formatDate(bet.settled_at || bet.created_at)}</td>
                    <td style={tdStyle}>
                      <Link
                        href={`/forecasts/${encodeURIComponent(bet.prediction_id)}`}
                        style={{ color: "var(--forecasts-parchment)", textDecorationColor: "var(--forecasts-muted)" }}
                      >
                        {predictionHeadline(bet)}
                      </Link>
                    </td>
                    <td style={tdMonoStyle}>{bet.side}</td>
                    <td style={tdMonoStyle}>{formatUsd(bet.stake_usd).replace("+", "")}</td>
                    <td style={tdMonoStyle}>{formatPrice(bet.entry_price)}</td>
                    <td style={tdMonoStyle}>{formatPrice(bet.exit_price)}</td>
                    <td
                      style={{
                        ...tdMonoStyle,
                        color:
                          pnl === null
                            ? "var(--forecasts-parchment-dim)"
                            : pnl < 0
                              ? "var(--forecasts-prob-no)"
                              : pnl > 0
                                ? "var(--forecasts-prob-yes)"
                                : "var(--forecasts-parchment-dim)",
                      }}
                    >
                      {formatUsd(pnl)}
                    </td>
                    <td style={tdMonoStyle}>{bet.status}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {nextSince ? (
        <div style={{ marginTop: "0.9rem" }}>
          <Link
            href={`/forecasts/portfolio?since=${encodeURIComponent(nextSince)}`}
            style={{
              color: "var(--forecasts-cool-gold)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.76rem",
              textDecoration: "none",
              textTransform: "uppercase",
            }}
          >
            Older paper bets
          </Link>
        </div>
      ) : null}
    </section>
  );
}

const thStyle: CSSProperties = {
  fontSize: "0.68rem",
  fontWeight: 500,
  padding: "0 0.6rem 0.55rem",
  textAlign: "left",
  textTransform: "uppercase",
  whiteSpace: "nowrap",
};

const tdStyle: CSSProperties = {
  color: "var(--forecasts-parchment-dim)",
  lineHeight: 1.45,
  padding: "0.65rem 0.6rem",
  verticalAlign: "top",
};

const tdMonoStyle: CSSProperties = {
  ...tdStyle,
  fontFamily: "'IBM Plex Mono', monospace",
  whiteSpace: "nowrap",
};
