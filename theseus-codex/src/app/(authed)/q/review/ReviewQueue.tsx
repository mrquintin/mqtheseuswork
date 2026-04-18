"use client";

import { useState } from "react";
import ReviewScale from "@/components/ReviewScaleClient";

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

/** Count how many layers voted each way. `unresolved` is neutral and
 *  doesn't tip the scale. We intentionally ignore any keys not in the
 *  known triplet so unexpected verdict strings don't skew the count. */
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
        return (
          <div key={it.id} className="portal-card" style={{ padding: "1.25rem" }}>
            <div
              style={{
                display: "flex",
                gap: "1.25rem",
                alignItems: "flex-start",
                flexWrap: "wrap",
              }}
            >
              {/* Live balance scale. Tips toward whichever side has more
                  layer votes. A symmetric (unresolved-heavy) pair comes to
                  rest horizontal, which reads as "the firm is still
                  weighing this" — exactly right for an open review item. */}
              <div style={{ flexShrink: 0 }}>
                <ReviewScale
                  cohereCount={tally.cohere}
                  contradictCount={tally.contradict}
                  severity={it.severity}
                  cols={24}
                  rows={8}
                />
              </div>

              <div style={{ flex: 1, minWidth: "220px" }}>
                <div
                  className="mono"
                  style={{
                    fontSize: "0.62rem",
                    color: "var(--amber-dim)",
                    textTransform: "uppercase",
                    letterSpacing: "0.12em",
                  }}
                >
                  severity {(it.severity * 100).toFixed(0)}% · aggregator{" "}
                  {it.aggregatorVerdict || "—"}
                </div>
                <p
                  style={{
                    marginTop: "0.5rem",
                    color: "var(--parchment)",
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1rem",
                    lineHeight: 1.55,
                  }}
                >
                  {it.reason}
                </p>
                <p
                  className="mono"
                  style={{
                    fontSize: "0.65rem",
                    color: "var(--parchment-dim)",
                    marginTop: "0.45rem",
                  }}
                >
                  {tally.contradict} × contradict · {tally.cohere} × cohere
                  {tally.unresolved > 0 ? ` · ${tally.unresolved} × unresolved` : ""}
                  {" · pair "}
                  {it.claimAId.slice(0, 8)}… / {it.claimBId.slice(0, 8)}…
                </p>
              </div>
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
