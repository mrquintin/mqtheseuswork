"use client";

import { RadioTower } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import type { OperatorBet, PublicForecast } from "@/lib/forecastsTypes";

import OperatorBetStream, { type OperatorStreamFrame } from "./OperatorBetStream";

type SortKey = "date" | "market" | "pnl";

function money(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "open";
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    style: "currency",
  }).format(value);
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(date);
}

export function applyOperatorStreamFrame(rows: OperatorBet[], frame: OperatorStreamFrame): OperatorBet[] {
  if (!frame.bet) return rows;
  const index = rows.findIndex((row) => row.id === frame.bet?.id);
  if (index === -1) return [frame.bet, ...rows];
  return rows.map((row, idx) => (idx === index ? { ...row, ...frame.bet } : row));
}

function sortedRows(rows: OperatorBet[], predictionsById: Record<string, PublicForecast>, sortKey: SortKey): OperatorBet[] {
  return rows.slice().sort((a, b) => {
    if (sortKey === "market") {
      const aHead = predictionsById[a.prediction_id]?.headline ?? a.prediction_id;
      const bHead = predictionsById[b.prediction_id]?.headline ?? b.prediction_id;
      return aHead.localeCompare(bHead);
    }
    if (sortKey === "pnl") {
      return (b.settlement_pnl_usd ?? Number.NEGATIVE_INFINITY) - (a.settlement_pnl_usd ?? Number.NEGATIVE_INFINITY);
    }
    return Date.parse(b.created_at) - Date.parse(a.created_at);
  });
}

export default function LiveBetLedger({
  initialRows,
  predictionsById,
}: {
  initialRows: OperatorBet[];
  predictionsById: Record<string, PublicForecast>;
}) {
  const [rows, setRows] = useState(initialRows);
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const visibleRows = useMemo(() => sortedRows(rows, predictionsById, sortKey), [predictionsById, rows, sortKey]);
  const onFrame = useCallback((frame: OperatorStreamFrame) => {
    setRows((current) => applyOperatorStreamFrame(current, frame));
  }, []);

  return (
    <section className="portal-card" style={{ padding: "1rem" }}>
      <OperatorBetStream onFrame={onFrame} />
      <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.75rem", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>Live bet ledger</h2>
          <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.25rem 0 0" }}>
            External order ids appear only on this founder-authenticated surface.
          </p>
        </div>
        <div aria-label="Ledger sort" style={{ display: "flex", gap: "0.35rem" }}>
          {(["date", "market", "pnl"] as SortKey[]).map((key) => (
            <button
              className="btn"
              data-sort-active={sortKey === key}
              key={key}
              onClick={() => setSortKey(key)}
              style={{ fontSize: "0.62rem", padding: "0.35rem 0.55rem" }}
              type="button"
            >
              {key.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div style={{ overflowX: "auto", marginTop: "1rem" }}>
        <table style={{ borderCollapse: "collapse", minWidth: "920px", width: "100%" }}>
          <thead>
            <tr className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.62rem", textAlign: "left" }}>
              <th style={{ padding: "0.45rem" }}>Date</th>
              <th style={{ padding: "0.45rem" }}>Market</th>
              <th style={{ padding: "0.45rem" }}>Exchange</th>
              <th style={{ padding: "0.45rem" }}>Side</th>
              <th style={{ padding: "0.45rem" }}>Stake</th>
              <th style={{ padding: "0.45rem" }}>P&L</th>
              <th style={{ padding: "0.45rem" }}>Order id</th>
              <th style={{ padding: "0.45rem" }}>Exchange status</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ color: "var(--parchment-dim)", padding: "0.8rem" }}>
                  No live bets have been created.
                </td>
              </tr>
            ) : (
              visibleRows.map((bet) => (
                <tr
                  data-bet-id={bet.id}
                  key={bet.id}
                  style={{ borderTop: "1px solid rgba(232, 225, 211, 0.1)", color: "var(--parchment)" }}
                >
                  <td className="mono" style={{ padding: "0.55rem" }}>{dateLabel(bet.created_at)}</td>
                  <td style={{ padding: "0.55rem" }}>{predictionsById[bet.prediction_id]?.headline ?? bet.prediction_id}</td>
                  <td className="mono" style={{ padding: "0.55rem" }}>{bet.exchange}</td>
                  <td className="mono" style={{ padding: "0.55rem" }}>{bet.side}</td>
                  <td className="mono" style={{ padding: "0.55rem" }}>{money(bet.stake_usd)}</td>
                  <td className="mono" style={{ padding: "0.55rem" }}>{money(bet.settlement_pnl_usd)}</td>
                  <td className="mono" style={{ padding: "0.55rem" }}>{bet.external_order_id || "not submitted"}</td>
                  <td className="mono" style={{ padding: "0.55rem" }}>
                    <RadioTower aria-hidden="true" size={13} /> {bet.status}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
