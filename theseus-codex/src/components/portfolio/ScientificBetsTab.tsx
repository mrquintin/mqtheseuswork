import Link from "next/link";
import type { CSSProperties } from "react";

import type { ScientificBetRow } from "./types";

type Props = {
  rows: ScientificBetRow[];
};

const statusPill = (outcome: string | null, status: string): CSSProperties => {
  const color = outcome === "CORRECT"
    ? "rgba(127, 196, 143, 0.95)"
    : outcome === "INCORRECT"
      ? "rgba(172, 54, 37, 0.85)"
      : outcome === "PARTIALLY_CORRECT"
        ? "var(--amber)"
        : status === "OPEN"
          ? "rgba(232, 225, 211, 0.5)"
          : "rgba(232, 225, 211, 0.35)";
  return {
    border: `1px solid ${color}`,
    borderRadius: 999,
    color,
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "0.62rem",
    letterSpacing: "0.12em",
    padding: "0.15rem 0.45rem",
    textTransform: "uppercase",
  };
};

export default function ScientificBetsTab({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <div data-testid="portfolio-scientific-tab" className="authed-prose">
        <p className="mono" style={{ color: "var(--amber-dim)" }}>
          No scientific bets yet. Hypothesis-track memos with a SCIENTIFIC_BET
          implied bet will appear here once the operator runs <code>noosphere bet propose</code>.
        </p>
      </div>
    );
  }
  // Pending first (open) then resolved, both newest first.
  const sorted = [...rows].sort((a, b) => {
    const rank = (r: ScientificBetRow) => (r.status === "OPEN" ? 0 : 1);
    const byRank = rank(a) - rank(b);
    if (byRank !== 0) return byRank;
    return (b.horizonAt || "").localeCompare(a.horizonAt || "");
  });
  return (
    <section data-testid="portfolio-scientific-tab" className="authed-prose">
      <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.82rem" }}>
        Published hypotheses. Each bet resolves against a named external feed
        (BLS, FRED, World Bank). Tolerance is the band within which the
        observed value still counts as CORRECT.
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--rule)" }}>
            <th style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>Status</th>
            <th style={{ padding: "0.4rem" }}>Proposition</th>
            <th style={{ padding: "0.4rem" }}>Source</th>
            <th style={{ padding: "0.4rem" }}>Expected ± tol</th>
            <th style={{ padding: "0.4rem" }}>Horizon</th>
            <th style={{ padding: "0.4rem" }}>Memo</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.id} style={{ borderBottom: "1px solid var(--rule)" }}>
              <td style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>
                <span style={statusPill(row.outcome, row.status)}>
                  {row.outcome ?? row.status}
                </span>
              </td>
              <td style={{ padding: "0.4rem" }}>{row.proposition || row.id}</td>
              <td className="mono" style={{ padding: "0.4rem" }}>{row.dataSource}</td>
              <td className="mono" style={{ padding: "0.4rem" }}>
                {row.expectedValue.toLocaleString("en-US")} ± {row.tolerance.toLocaleString("en-US")}
              </td>
              <td className="mono" style={{ padding: "0.4rem" }}>
                {row.horizonAt.slice(0, 10)}
              </td>
              <td style={{ padding: "0.4rem" }}>
                {row.memoId ? (
                  <Link href={`/inbox/${row.memoId}`}>{row.memoId}</Link>
                ) : (
                  <span style={{ color: "var(--amber-dim)" }}>—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
