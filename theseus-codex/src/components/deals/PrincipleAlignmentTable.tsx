"use client";

import Link from "next/link";

/**
 * Render the per-principle alignment table for a single deal.
 *
 * The table is the load-bearing UI for the VC firm preset: it tells
 * the partner which firm principles apply, what the agent's verdict
 * is, and what the citation trail looks like. The agent surfaces
 * which principles apply — the partner decides.
 *
 * Verdict color legend:
 *   MATCH    — amber (positive but conservative)
 *   CONFLICT — red
 *   UNCLEAR  — parchment-dim
 */

export type AlignmentCitation = {
  quote: string;
  source_uri?: string;
  conclusion_id?: string;
  locator?: string;
};

export type AlignmentRow = {
  principleId: string;
  principleText: string;
  principleDomains: string[];
  verdict: "MATCH" | "CONFLICT" | "UNCLEAR";
  rationale: string;
  confidence: number;
  citations: AlignmentCitation[];
};

const VERDICT_COLOR: Record<AlignmentRow["verdict"], string> = {
  MATCH: "var(--match, #5fa86b)",
  CONFLICT: "var(--conflict, #c05050)",
  UNCLEAR: "var(--parchment-dim)",
};

export default function PrincipleAlignmentTable({
  rows,
  dealId,
}: {
  rows: AlignmentRow[];
  dealId: string;
}) {
  if (rows.length === 0) {
    return (
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          color: "var(--parchment-dim)",
          margin: 0,
        }}
        data-testid="alignment-empty"
        data-deal-id={dealId}
      >
        No alignment rows yet. The runner has not produced verdicts for this
        deal, or no firm principles applied to its sector + stage.
      </p>
    );
  }

  return (
    <table
      data-testid="alignment-table"
      data-deal-id={dealId}
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: "'EB Garamond', serif",
      }}
    >
      <thead>
        <tr
          style={{
            borderBottom: "1px solid var(--amber-dim)",
            textAlign: "left",
          }}
        >
          <th style={{ padding: "0.55rem 0.4rem", width: "32%" }}>
            Principle
          </th>
          <th style={{ padding: "0.55rem 0.4rem", width: "10%" }}>Verdict</th>
          <th style={{ padding: "0.55rem 0.4rem", width: "10%" }}>
            Confidence
          </th>
          <th style={{ padding: "0.55rem 0.4rem" }}>Rationale</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr
            key={r.principleId}
            data-testid="alignment-row"
            data-principle-id={r.principleId}
            data-verdict={r.verdict}
            style={{ borderBottom: "1px solid rgba(180,150,80,0.12)" }}
          >
            <td style={{ padding: "0.7rem 0.4rem", verticalAlign: "top" }}>
              <Link
                href={`/principles/${r.principleId}`}
                style={{ color: "var(--amber)" }}
              >
                {r.principleText}
              </Link>
              {r.principleDomains.length ? (
                <div
                  className="mono"
                  style={{
                    marginTop: "0.3rem",
                    fontSize: "0.6rem",
                    letterSpacing: "0.18em",
                    color: "var(--amber-dim)",
                    textTransform: "uppercase",
                  }}
                >
                  {r.principleDomains.join(" · ")}
                </div>
              ) : null}
            </td>
            <td
              className="mono"
              style={{
                padding: "0.7rem 0.4rem",
                fontSize: "0.7rem",
                letterSpacing: "0.14em",
                color: VERDICT_COLOR[r.verdict],
                verticalAlign: "top",
              }}
            >
              {r.verdict}
            </td>
            <td
              className="mono"
              style={{
                padding: "0.7rem 0.4rem",
                fontSize: "0.7rem",
                color: "var(--parchment-dim)",
                verticalAlign: "top",
              }}
            >
              {(r.confidence * 100).toFixed(0)}%
            </td>
            <td
              style={{
                padding: "0.7rem 0.4rem",
                verticalAlign: "top",
                lineHeight: 1.45,
              }}
            >
              <div>{r.rationale || "—"}</div>
              {r.citations.length ? (
                <ul
                  style={{
                    listStyle: "none",
                    padding: 0,
                    margin: "0.45rem 0 0",
                  }}
                >
                  {r.citations.map((c, i) => (
                    <li
                      key={`${r.principleId}-c${i}`}
                      style={{
                        fontStyle: "italic",
                        color: "var(--parchment-dim)",
                        fontSize: "0.85rem",
                        marginTop: "0.25rem",
                      }}
                    >
                      “{c.quote}”
                      {c.locator ? (
                        <span
                          className="mono"
                          style={{
                            marginLeft: "0.4rem",
                            fontSize: "0.6rem",
                            letterSpacing: "0.14em",
                          }}
                        >
                          [{c.locator}]
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
