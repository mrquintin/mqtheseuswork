"use client";

import { useEffect, useState } from "react";

import ProvenanceFilter, {
  DEFAULT_PROVENANCE_FILTER,
  type ProvenanceFilterValue,
  type ProvenanceKindStr,
} from "@/components/oracle/ProvenanceFilter";

interface OracleSource {
  id: string;
  title: string;
  provenance: string;
  weight: number;
}

interface OracleAnswer {
  question: string;
  sources: OracleSource[];
  active_provenance_kinds: string[];
  active_weights: Record<string, number>;
  total_sources_considered: number;
}

export default function OracleClient() {
  const [question, setQuestion] = useState("");
  const [filter, setFilter] = useState<ProvenanceFilterValue>(
    DEFAULT_PROVENANCE_FILTER,
  );
  const [counts, setCounts] = useState<
    Partial<Record<ProvenanceKindStr, number>>
  >({});
  const [answer, setAnswer] = useState<OracleAnswer | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/oracle/provenance-counts")
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: Array<{ provenance: string; count: number }>) => {
        if (cancelled) return;
        const next: Partial<Record<ProvenanceKindStr, number>> = {};
        for (const row of rows) {
          next[row.provenance as ProvenanceKindStr] = row.count;
        }
        setCounts(next);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/oracle/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          provenance_filter: filter,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || `ask failed (${res.status})`);
      }
      setAnswer(data as OracleAnswer);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: "860px",
        margin: "0 auto",
        padding: "3rem 1.5rem 5rem",
      }}
    >
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          letterSpacing: "0.06em",
          color: "var(--amber)",
          textShadow: "var(--glow-sm)",
          fontSize: "1.6rem",
          margin: 0,
        }}
      >
        Oracle
      </h1>
      <p
        style={{
          color: "var(--parchment-dim)",
          marginTop: "0.8rem",
          lineHeight: 1.65,
        }}
      >
        Ask the firm. The synthesizer pulls from proprietary and
        endorsed-external sources by default and weights proprietary
        twice as heavily. Studied and opposing material is excluded
        unless you opt in.
      </p>

      <form
        onSubmit={submit}
        style={{
          marginTop: "2rem",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <ProvenanceFilter
          value={filter}
          onChange={setFilter}
          counts={counts}
        />

        <textarea
          rows={4}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          style={{
            width: "100%",
            padding: "0.75rem",
            background: "rgba(0,0,0,0.25)",
            border: "1px solid var(--stroke)",
            borderRadius: "3px",
            color: "var(--parchment)",
            fontFamily: "inherit",
            fontSize: "1rem",
            resize: "vertical",
          }}
        />

        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <button
            type="submit"
            disabled={busy || !question.trim()}
            style={{
              padding: "0.55rem 1.2rem",
              border: "1px solid var(--amber)",
              background: busy ? "transparent" : "rgba(212,160,23,0.1)",
              color: "var(--amber)",
              cursor: busy ? "wait" : "pointer",
              borderRadius: "3px",
              fontFamily: "inherit",
            }}
          >
            {busy ? "Asking…" : "Ask"}
          </button>
          {error && (
            <span style={{ color: "var(--amber)", fontSize: "0.9rem" }}>
              {error}
            </span>
          )}
        </div>
      </form>

      {answer && (
        <section style={{ marginTop: "3rem" }}>
          <h2
            className="mono"
            style={{
              fontSize: "0.7rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "var(--amber)",
              borderBottom: "1px solid var(--stroke)",
              paddingBottom: "0.4rem",
            }}
          >
            Sources ({answer.sources.length}/{answer.total_sources_considered}{" "}
            considered)
          </h2>
          <div
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.12em",
              color: "var(--parchment-dim)",
              marginTop: "0.4rem",
            }}
          >
            Active: {answer.active_provenance_kinds.join(", ") || "none"} ·{" "}
            weights{" "}
            {Object.entries(answer.active_weights)
              .map(([k, v]) => `${k}=${v.toFixed(1)}×`)
              .join(", ")}
          </div>
          <ul style={{ listStyle: "none", padding: 0, marginTop: "0.8rem" }}>
            {answer.sources.map((s) => (
              <li
                key={s.id}
                style={{
                  padding: "0.6rem 0",
                  borderBottom: "1px solid var(--stroke)",
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "1rem",
                }}
              >
                <span style={{ color: "var(--parchment)" }}>{s.title}</span>
                <span
                  className="mono"
                  style={{ color: "var(--parchment-dim)", fontSize: "0.75rem" }}
                >
                  {s.provenance.replace(/_/g, " ")} · {s.weight.toFixed(1)}×
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
