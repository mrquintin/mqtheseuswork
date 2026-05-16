import Link from "next/link";
import type { CSSProperties } from "react";

import type { AdvisoryBetRow } from "./types";

type Props = {
  rows: AdvisoryBetRow[];
};

const pillStyle = (kind: AdvisoryBetRow["positionPill"]): CSSProperties => {
  const palette: Record<AdvisoryBetRow["positionPill"], string> = {
    BULLISH: "rgba(127, 196, 143, 0.95)",
    BEARISH: "rgba(172, 54, 37, 0.85)",
    NEUTRAL: "rgba(232, 225, 211, 0.5)",
  };
  return {
    border: `1px solid ${palette[kind]}`,
    borderRadius: 999,
    color: palette[kind],
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "0.62rem",
    letterSpacing: "0.12em",
    padding: "0.15rem 0.45rem",
    textTransform: "uppercase",
  };
};

function fmtAccuracy(score: number | null): string {
  if (score === null) return "—";
  if (Number.isNaN(score)) return "—";
  return score.toFixed(2);
}

function fmtReach(reach: number | null): string {
  if (reach === null) return "—";
  return reach.toLocaleString("en-US");
}

export default function AdvisoryBetsTab({ rows }: Props) {
  // Ranked by reach × accuracy as the prompt specifies. NULLs (unresolved
  // or audience figures we haven't measured) sort last.
  const ranked = [...rows].sort((a, b) => {
    const score = (r: AdvisoryBetRow) =>
      (r.reach ?? 0) * (1 - Math.min(1, Math.abs(r.accuracyScore ?? 1)));
    return score(b) - score(a);
  });

  if (ranked.length === 0) {
    return (
      <div data-testid="portfolio-advisory-tab" className="authed-prose">
        <p className="mono" style={{ color: "var(--amber-dim)" }}>
          No advisory bets yet. Public memos with an ADVISORY_BET implied bet
          will appear here once the operator runs <code>noosphere bet propose</code>.
        </p>
      </div>
    );
  }

  return (
    <section data-testid="portfolio-advisory-tab" className="authed-prose">
      <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.82rem" }}>
        Public-commitment positions. Ranked by reach × accuracy (better
        accuracy ranks higher).
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--rule)" }}>
            <th style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>Position</th>
            <th style={{ padding: "0.4rem" }}>Proposition</th>
            <th style={{ padding: "0.4rem" }}>Audience</th>
            <th style={{ padding: "0.4rem" }}>Reach</th>
            <th style={{ padding: "0.4rem" }}>Accuracy</th>
            <th style={{ padding: "0.4rem" }}>Memo</th>
            <th style={{ padding: "0.4rem" }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((row) => (
            <tr key={row.id} style={{ borderBottom: "1px solid var(--rule)" }}>
              <td style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>
                <span style={pillStyle(row.positionPill)}>{row.positionPill}</span>
              </td>
              <td style={{ padding: "0.4rem" }}>
                {row.publicUrl ? (
                  <Link href={row.publicUrl}>{row.proposition || row.id}</Link>
                ) : (
                  row.proposition || row.id
                )}
              </td>
              <td className="mono" style={{ padding: "0.4rem" }}>{row.audience}</td>
              <td className="mono" style={{ padding: "0.4rem" }}>{fmtReach(row.reach)}</td>
              <td className="mono" style={{ padding: "0.4rem" }}>{fmtAccuracy(row.accuracyScore)}</td>
              <td style={{ padding: "0.4rem" }}>
                {row.memoId ? (
                  <Link href={`/memos/${row.memoId}`}>{row.memoId}</Link>
                ) : (
                  <span style={{ color: "var(--amber-dim)" }}>—</span>
                )}
              </td>
              <td className="mono" style={{ padding: "0.4rem" }}>
                {row.outcome ? row.outcome.toLowerCase() : row.status.toLowerCase()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
