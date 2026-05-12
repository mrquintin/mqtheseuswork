"use client";

import Link from "next/link";
import { useState } from "react";
import AnswerMarkdown from "@/components/AnswerMarkdown";
import {
  citationHref,
  type ResolvedCitation,
  type ResolvedCitationMap,
} from "@/lib/oracleCitations";

/**
 * Ask the Codex — client-side form. Posts to /api/ask, renders the
 * grounded answer plus the heterogeneous sources list (Conclusion
 * citations + Upload citations).
 *
 * Visual contract:
 *   - The answer text is rendered as sanitised Markdown, preserving
 *     inline citation markers [C:xxxxx] / [U:xxxxx] the oracle added.
 *   - The source panel groups Conclusions (tier-coloured chips) above
 *     Upload excerpts, and each cited row links to the same destination
 *     as its inline citation token.
 */

interface SourceConclusion {
  type: "conclusion";
  id: string;
  label: string;
  tier: string;
  topic: string;
  text: string;
  url: string | null;
  anchor?: string | null;
}

interface SourceUpload {
  type: "upload";
  id: string;
  label: string;
  text: string;
  url: string | null;
  anchor?: string | null;
}

type Source = SourceConclusion | SourceUpload;

interface AskResult {
  question: string;
  answer: string;
  model: string;
  conclusionsInContext: number;
  uploadsInContext: number;
  uploadChunksInContext: number;
  inputTokens: number;
  outputTokens: number;
  sources: Source[];
  citations: ResolvedCitationMap;
  citationsResolved: number;
  citationsUnresolved: number;
}

function citationForSource(
  source: Source,
  citations: ResolvedCitationMap,
): ResolvedCitation | null {
  return (
    Object.values(citations).find(
      (citation) => citation.type === source.type && citation.id === source.id,
    ) ?? null
  );
}

function sourceHref(source: Source, citations: ResolvedCitationMap): string | null {
  const citation = citationForSource(source, citations);
  const resolvedHref = citation ? citationHref(citation) : null;
  if (resolvedHref) return resolvedHref;
  if (!source.url) return null;
  if (source.anchor) return `${source.url}?anchor=${encodeURIComponent(source.anchor)}`;
  return source.url;
}

function sourcePreview(source: Source, citations: ResolvedCitationMap): string {
  return citationForSource(source, citations)?.preview || source.text;
}

export default function AskForm({
  initialQuestion = "",
}: {
  initialQuestion?: string;
} = {}) {
  const [question, setQuestion] = useState(initialQuestion);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState("");
  const [showSources, setShowSources] = useState(false);

  const trimmed = question.trim();
  const canSubmit = trimmed.length > 0 && !loading;
  const disabledReason = loading
    ? "Consulting the oracle…"
    : trimmed.length === 0
    ? "Type a question to enable Ask"
    : "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed }),
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

  // Enter (without Shift) submits — keyboard parity with the Ask
  // button. Shift+Enter still inserts a newline so multi-line
  // questions remain easy to compose.
  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void submit(event as unknown as React.FormEvent);
  }

  const conclusionSources = (result?.sources ?? []).filter(
    (s): s is SourceConclusion => s.type === "conclusion",
  );
  const uploadSources = (result?.sources ?? []).filter(
    (s): s is SourceUpload => s.type === "upload",
  );
  const citations = result?.citations ?? {};

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
          onKeyDown={onKeyDown}
          placeholder="What does the firm believe about base-rate neglect in early-stage underwriting?"
          rows={4}
          disabled={loading}
          aria-label="Your question for the Codex"
          style={{ resize: "vertical", minHeight: "100px" }}
        />
        <div
          style={{
            alignItems: "center",
            display: "flex",
            gap: "0.85rem",
            justifyContent: "flex-end",
          }}
        >
          {disabledReason ? (
            <span
              className="mono"
              aria-live="polite"
              data-loading={loading ? "true" : undefined}
              style={{
                color: loading ? "var(--amber)" : "var(--parchment-dim)",
                fontSize: "0.6rem",
                letterSpacing: "0.18em",
                textTransform: "uppercase",
              }}
            >
              {disabledReason}
            </span>
          ) : null}
          <button
            type="submit"
            className="btn-solid btn"
            disabled={!canSubmit}
            aria-busy={loading}
            title={disabledReason || "Ask the Codex (Enter)"}
          >
            {loading ? "Consulting the oracle…" : "Ask the Codex"}
          </button>
        </div>
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

          <AnswerMarkdown citations={citations}>{result.answer}</AnswerMarkdown>

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
              Grounded in{" "}
              <strong style={{ color: "var(--amber)" }}>
                {result.conclusionsInContext}
              </strong>{" "}
              conclusion{result.conclusionsInContext === 1 ? "" : "s"} ·{" "}
              <strong style={{ color: "var(--amber)" }}>
                {result.uploadsInContext}
              </strong>{" "}
              upload{result.uploadsInContext === 1 ? "" : "s"} ·{" "}
              <span title={`${result.inputTokens} in / ${result.outputTokens} out tokens`}>
                model {result.model}
              </span>
            </span>
            <span
              title={
                result.citationsUnresolved > 0
                  ? "Unverified citation tokens were not found in the retrieved corpus."
                  : "All emitted citation tokens resolved to corpus material."
              }
            >
              {result.citationsResolved} sources linked ·{" "}
              {result.citationsUnresolved} unverified.
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
            <div
              style={{
                marginTop: "1rem",
                paddingTop: "1rem",
                borderTop: "1px solid var(--amber-deep)",
                display: "flex",
                flexDirection: "column",
                gap: "1.25rem",
                maxHeight: "520px",
                overflowY: "auto",
              }}
            >
              {uploadSources.length > 0 && (
                <section>
                  <h3
                    className="mono"
                    style={{
                      fontSize: "0.58rem",
                      letterSpacing: "0.25em",
                      textTransform: "uppercase",
                      color: "var(--amber-dim)",
                      margin: "0 0 0.6rem",
                      fontWeight: 500,
                    }}
                  >
                    Fontes · Uploads ({uploadSources.length})
                  </h3>
                  <ul
                    style={{
                      listStyle: "none",
                      padding: 0,
                      margin: 0,
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.7rem",
                    }}
                  >
                    {uploadSources.map((s) => {
                      const href = sourceHref(s, citations);
                      const preview = sourcePreview(s, citations);
                      return (
                        <li
                          key={s.id}
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.3rem",
                            fontSize: "0.82rem",
                            lineHeight: 1.5,
                            color: "var(--parchment-dim)",
                            paddingLeft: "0.75rem",
                            borderLeft: "2px solid var(--amber-deep)",
                          }}
                        >
                          <div
                            className="mono"
                            style={{
                              fontSize: "0.62rem",
                              letterSpacing: "0.12em",
                              color: "var(--amber)",
                            }}
                          >
                            {href ? (
                              <Link
                                href={href}
                                rel="noopener"
                                style={{
                                  color: "var(--amber)",
                                  textDecoration: "underline",
                                  textDecorationStyle: "dotted",
                                  textUnderlineOffset: "3px",
                                }}
                                target="_blank"
                                title={preview}
                              >
                                {s.label}
                              </Link>
                            ) : (
                              <span>{s.label}</span>
                            )}
                          </div>
                          <span style={{ whiteSpace: "pre-wrap" }}>{preview}</span>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              )}

              {conclusionSources.length > 0 && (
                <section>
                  <h3
                    className="mono"
                    style={{
                      fontSize: "0.58rem",
                      letterSpacing: "0.25em",
                      textTransform: "uppercase",
                      color: "var(--amber-dim)",
                      margin: "0 0 0.6rem",
                      fontWeight: 500,
                    }}
                  >
                    Firm conclusions ({conclusionSources.length})
                  </h3>
                  <ul
                    style={{
                      listStyle: "none",
                      padding: 0,
                      margin: 0,
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.5rem",
                    }}
                  >
                    {conclusionSources.map((s, i) => {
                      const href = sourceHref(s, citations);
                      const preview = sourcePreview(s, citations);
                      const body = (
                        <>
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
                          {preview}
                        </>
                      );
                      return (
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
                          {href ? (
                            <Link
                              href={href}
                              rel="noopener"
                              style={{
                                color: "var(--parchment-dim)",
                                textDecoration: "none",
                              }}
                              target="_blank"
                              title={preview}
                            >
                              {body}
                            </Link>
                          ) : (
                            <span>{body}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              )}
            </div>
          )}
        </article>
      )}
    </div>
  );
}
