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

export default function ReviewQueue({ items }: { items: Row[] }) {
  const [msg, setMsg] = useState("");

  async function resolve(id: string, verdict: "cohere" | "contradict" | "unresolved", overrule: boolean) {
    setMsg("");
    const res = await fetch(`/api/review/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, overrule, note: overrule ? "Founder overrule via portal" : "Founder confirm" }),
    });
    const data = await res.json();
    if (!res.ok) {
      setMsg(data.error || "Request failed");
      return;
    }
    window.location.reload();
  }

  if (!items.length) {
    return <p style={{ color: "var(--parchment-dim)" }}>No open review items.</p>;
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
          scores = it.priorScoresJson ? (JSON.parse(it.priorScoresJson) as Record<string, number>) : null;
        } catch {
          scores = null;
        }
        return (
          <div key={it.id} className="portal-card" style={{ padding: "1.25rem" }}>
            <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
              severity {(it.severity * 100).toFixed(0)}% · aggregator {it.aggregatorVerdict || "—"}
            </div>
            <p style={{ marginTop: "0.5rem", color: "var(--parchment)" }}>{it.reason}</p>
            <p style={{ fontSize: "0.75rem", color: "var(--parchment-dim)", marginTop: "0.35rem" }}>
              Pair: {it.claimAId} · {it.claimBId}
            </p>
            <details style={{ marginTop: "0.75rem" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.8rem" }}>Layer verdicts</summary>
              <pre style={{ fontSize: "0.7rem", marginTop: "0.5rem", overflow: "auto" }}>
                {JSON.stringify(layers, null, 2)}
              </pre>
              {scores && (
                <pre style={{ fontSize: "0.7rem", marginTop: "0.5rem", overflow: "auto" }}>
                  {JSON.stringify(scores, null, 2)}
                </pre>
              )}
            </details>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "1rem" }}>
              <button type="button" className="btn" onClick={() => resolve(it.id, "cohere", false)}>
                Confirm cohere
              </button>
              <button type="button" className="btn" onClick={() => resolve(it.id, "contradict", false)}>
                Confirm contradict
              </button>
              <button type="button" className="btn-solid btn" onClick={() => resolve(it.id, "contradict", true)}>
                Overrule → contradict
              </button>
              <button type="button" className="btn-solid btn" onClick={() => resolve(it.id, "cohere", true)}>
                Overrule → cohere
              </button>
              <button type="button" className="btn" onClick={() => resolve(it.id, "unresolved", true)}>
                Overrule → unresolved
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
