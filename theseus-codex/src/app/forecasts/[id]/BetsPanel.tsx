import type { CSSProperties } from "react";

import type { PublicBet } from "@/lib/forecastsTypes";

interface BetsPanelProps {
  paperBets: PublicBet[];
}

const panelStyle: CSSProperties = {
  border: "1px solid var(--forecasts-border)",
  borderRadius: "6px",
  marginTop: "1.2rem",
  padding: "1rem",
};

const tableStyle: CSSProperties = {
  borderCollapse: "collapse",
  fontSize: "0.86rem",
  marginTop: "0.75rem",
  width: "100%",
};

const cellStyle: CSSProperties = {
  borderTop: "1px solid var(--forecasts-border)",
  padding: "0.55rem 0.45rem",
  textAlign: "left",
};

function currency(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "open";
  return `${value >= 0 ? "+" : "-"}$${Math.abs(value).toFixed(2)}`;
}

function money(value: number): string {
  return `$${value.toFixed(2)}`;
}

function price(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

function pnlColor(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "var(--forecasts-muted)";
  if (value > 0) return "var(--forecasts-prob-yes)";
  if (value < 0) return "var(--forecasts-prob-no)";
  return "var(--forecasts-parchment-dim)";
}

export default function BetsPanel({ paperBets }: BetsPanelProps) {
  if (!paperBets.length) return null;

  return (
    <section aria-label="Paper bets" style={panelStyle}>
      <h2
        style={{
          color: "var(--forecasts-cool-gold)",
          fontFamily: "'Cinzel', serif",
          fontSize: "0.98rem",
          letterSpacing: "0.08em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        Paper bets
      </h2>
      <table style={tableStyle}>
        <thead>
          <tr style={{ color: "var(--forecasts-muted)" }}>
            <th style={cellStyle}>Side</th>
            <th style={cellStyle}>Stake</th>
            <th style={cellStyle}>Entry</th>
            <th style={cellStyle}>Status</th>
            <th style={cellStyle}>P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {paperBets.map((bet) => (
            <tr key={bet.id}>
              <td className="mono" style={cellStyle}>
                {bet.side}
              </td>
              <td className="mono" style={cellStyle}>
                {money(bet.stake_usd)}
              </td>
              <td className="mono" style={cellStyle}>
                {price(bet.entry_price)}
              </td>
              <td style={cellStyle}>{bet.status}</td>
              <td
                className="mono"
                style={{
                  ...cellStyle,
                  color: pnlColor(bet.settlement_pnl_usd),
                  fontWeight: bet.settlement_pnl_usd === null ? 400 : 700,
                }}
              >
                {currency(bet.settlement_pnl_usd)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
