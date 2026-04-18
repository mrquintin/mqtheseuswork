"use client";

import { useState } from "react";

/**
 * Ask the Codex — client-side form. Posts to /api/ask, renders the
 * grounded answer + expandable source Conclusions. Intentionally
 * minimal: this is a query surface, not a conversation — each submit
 * starts a fresh round with full corpus context so there's no
 * session-state to manage.
 */

interface Source {
  id: string;
  tier: string;
  topic: string;
  text: string;
}

interface AskResult {
  question: string;
  answer: string;
  model: string;
  conclusionsInContext: number;
  sources: Source[];
}

export default function AskForm() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState("");
  const [showSources, setShowSources] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || loading) return;
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || `Request failed (HTTP ${res.status})`);
      } else {
        setResult(data as AskResult);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form
        onSubmit={submit}
        className="ascii-frame"
        data-label="QUAESTIO · YOUR QUESTION"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.9rem",
        }}
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What does the firm believe about base-rate neglect in early-stage underwriting?"
          rows={4}
          disabled={loading}
          style={{ resize: "vertical", minHeight: "100px" }}
        />
        <button
          type="submit"
          className="btn-solid btn"
          disabled={loading || !question.trim()}
          style={{ alignSelf: "flex-end" }}
        >
          {loading ? "Consulting the oracle…" : "Ask the Codex"}
        </button>
      </form>

      {error && (
        <p
          role="alert"
          style={{
            color: "var(--ember)",
            fontSize: "0.9rem",
            marginTop: "1.5rem",
            padding: "0.9rem 1rem",
            border: "1px solid var(--ember)",
            background: "rgba(201, 74, 31, 0.08)",
          }}
        >
          {error}
        </p>
      )}

      {result && (
        <article
          style={{
            marginTop: "1.75rem",
            padding: "1.5rem 1.75rem",
            border: "1px solid var(--amber-deep)",
            background:
              "linear-gradient(180deg, rgba(30,20,8,0.4) 0%, rgba(20,14,6,0.25) 100%)",
          }}
        >
          <p
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              margin: 0,
            }}
          >
            Responsum · Answer from the Codex
          </p>

          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontSize: "1.08rem",
              color: "var(--parchment)",
              marginTop: "0.7rem",
              marginBottom: 0,
              lineHeight: 1.65,
              whiteSpace: "pre-wrap",
            }}
          >
            {result.answer}
          </p>

          <div
            className="mono"
            style={{
              fontSize: "0.62rem",
              color: "var(--parchment-dim)",
              marginTop: "1rem",
              display: "flex",
              flexWrap: "wrap",
              gap: "1rem",
              alignItems: "center",
            }}
          >
            <span>
              Grounded in <strong style={{ color: "var(--amber)" }}>{result.conclusionsInContext}</strong>{" "}
              Conclusions · model {result.model}
            </span>
            {result.sources.length > 0 && (
              <button
                type="button"
                onClick={() => setShowSources((v) => !v)}
                className="btn"
                style={{ fontSize: "0.6rem", padding: "0.35rem 0.8rem" }}
              >
                {showSources ? "Hide" : "Show"} sources
              </button>
            )}
          </div>

          {showSources && result.sources.length > 0 && (
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: "1rem 0 0",
                display: "flex",
                flexDirection: "column",
                gap: "0.6rem",
                maxHeight: "360px",
                overflowY: "auto",
                borderTop: "1px solid var(--amber-deep)",
                paddingTop: "1rem",
              }}
            >
              {result.sources.map((s, i) => (
                <li
                  key={s.id}
                  style={{
                    display: "flex",
                    gap: "0.9rem",
                    fontSize: "0.82rem",
                    lineHeight: 1.5,
                    color: "var(--parchment-dim)",
                  }}
                >
                  <span
                    className="mono"
                    style={{
                      fontSize: "0.58rem",
                      letterSpacing: "0.1em",
                      color: "var(--amber-dim)",
                      flexShrink: 0,
                      width: "5.5rem",
                    }}
                  >
                    [{String(i + 1).padStart(2, "0")}] {s.tier}
                  </span>
                  <span>
                    <code
                      className="mono"
                      style={{
                        fontSize: "0.65rem",
                        color: "var(--amber)",
                        marginRight: "0.5rem",
                      }}
                    >
                      {s.id.slice(0, 10)}
                    </code>
                    {s.text}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </article>
      )}
    </div>
  );
}
