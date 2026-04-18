"use client";

import { useState } from "react";

type Row = {
  id: string;
  claimAId: string;
  claimBId: string;
  reason: string;
  severity: number;
  aggregatorVerdict: string | null;
  layerVerdictsJson: string;
  priorScoresJson: string | null;
};

/**
 * Coherence review queue rows. Previous version rendered a small animated
 * balance-scale per row; removed in favour of a compact textual verdict-
 * tally. The Dying Gladiator sculpture at the top of the page carries the
 * visual weight; individual rows stay typographic so a long queue scans
 * cleanly.
 */

function tallyVerdicts(layers: Record<string, string>): {
  cohere: number;
  contradict: number;
  unresolved: number;
} {
  let cohere = 0;
  let contradict = 0;
  let unresolved = 0;
  for (const v of Object.values(layers)) {
    if (v === "cohere") cohere++;
    else if (v === "contradict") contradict++;
    else if (v === "unresolved") unresolved++;
  }
  return { cohere, contradict, unresolved };
}

export default function ReviewQueue({ items }: { items: Row[] }) {
  const [msg, setMsg] = useState("");

  async function resolve(
    id: string,
    verdict: "cohere" | "contradict" | "unresolved",
    overrule: boolean,
  ) {
    setMsg("");
    const res = await fetch(`/api/review/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        verdict,
        overrule,
        note: overrule ? "Founder overrule via portal" : "Founder confirm",
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      setMsg(data.error || "Request failed");
      return;
    }
    window.location.reload();
  }

  if (!items.length) {
    return (
      <div
        className="ascii-frame"
        data-label="IUDICIUM · NO ITEMS"
        style={{ padding: "2rem 1rem", textAlign: "center" }}
      >
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "1.1rem",
            color: "var(--parchment)",
            margin: 0,
          }}
        >
          Nihil in trutina.
        </p>
        <p
          className="mono"
          style={{
            fontSize: "0.7rem",
            color: "var(--parchment-dim)",
            marginTop: "0.4rem",
          }}
        >
          No open review items. Nothing on the scales.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {msg && <p style={{ color: "var(--ember)" }}>{msg}</p>}
      {items.map((it) => {
        let layers: Record<string, string> = {};
        let scores: Record<string, number> | null = null;
        try {
          layers = JSON.parse(it.layerVerdictsJson) as Record<string, string>;
        } catch {
          layers = {};
        }
        try {
          scores = it.priorScoresJson
            ? (JSON.parse(it.priorScoresJson) as Record<string, number>)
            : null;
        } catch {
          scores = null;
        }
        const tally = tallyVerdicts(layers);

        // Dominant side for a one-glance verdict summary. Ties or
        // `unresolved`-dominated rows render as "split".
        let dominant: "cohere" | "contradict" | "split" = "split";
        if (tally.contradict > tally.cohere) dominant = "contradict";
        else if (tally.cohere > tally.contradict) dominant = "cohere";

        return (
          <div key={it.id} className="portal-card" style={{ padding: "1.25rem" }}>
            <div
              className="mono"
              style={{
                fontSize: "0.62rem",
                color: "var(--amber-dim)",
                textTransform: "uppercase",
                letterSpacing: "0.12em",
                marginBottom: "0.5rem",
              }}
            >
              severity {(it.severity * 100).toFixed(0)}% · aggregator{" "}
              {it.aggregatorVerdict || "—"} · leaning {dominant}
            </div>

            <p
              style={{
                margin: 0,
                color: "var(--parchment)",
                fontFamily: "'EB Garamond', serif",
                fontSize: "1rem",
                lineHeight: 1.6,
              }}
            >
              {it.reason}
            </p>

            {/* Textual verdict tally — replaces the per-row animated
                balance. Highlights contradict in ember, cohere in amber,
                unresolved in parchment-dim so the spread is readable at
                a glance without additional visual chrome. */}
            <div
              className="mono"
              style={{
                display: "flex",
                gap: "1.1rem",
                flexWrap: "wrap",
                fontSize: "0.72rem",
                marginTop: "0.55rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              <span style={{ color: "var(--ember)" }}>
                ✕ {tally.contradict} contradict
              </span>
              <span style={{ color: "var(--amber)" }}>∙ {tally.cohere} cohere</span>
              {tally.unresolved > 0 && (
                <span style={{ color: "var(--parchment-dim)" }}>
                  ? {tally.unresolved} unresolved
                </span>
              )}
              <span style={{ color: "var(--parchment-dim)", marginLeft: "auto" }}>
                pair {it.claimAId.slice(0, 8)}… / {it.claimBId.slice(0, 8)}…
              </span>
            </div>

            <details style={{ marginTop: "0.9rem" }}>
              <summary
                className="mono"
                style={{
                  cursor: "pointer",
                  fontSize: "0.7rem",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                }}
              >
                Layer verdicts · full detail
              </summary>
              <pre style={{ fontSize: "0.7rem", marginTop: "0.5rem", overflow: "auto" }}>
                {JSON.stringify(layers, null, 2)}
              </pre>
              {scores && (
                <pre
                  style={{
                    fontSize: "0.7rem",
                    marginTop: "0.5rem",
                    overflow: "auto",
                  }}
                >
                  {JSON.stringify(scores, null, 2)}
                </pre>
              )}
            </details>

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "0.5rem",
                marginTop: "1rem",
              }}
            >
              <button
                type="button"
                className="btn"
                onClick={() => resolve(it.id, "cohere", false)}
              >
                Confirm cohere
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => resolve(it.id, "contradict", false)}
              >
                Confirm contradict
              </button>
              <button
                type="button"
                className="btn-solid btn"
                onClick={() => resolve(it.id, "contradict", true)}
              >
                Overrule → contradict
              </button>
              <button
                type="button"
                className="btn-solid btn"
                onClick={() => resolve(it.id, "cohere", true)}
              >
                Overrule → cohere
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => resolve(it.id, "unresolved", true)}
              >
                Overrule → unresolved
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
