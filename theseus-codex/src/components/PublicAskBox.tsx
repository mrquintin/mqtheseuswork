"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  PublicAskKind,
  PublicAskResponse,
  PublicAskResult,
} from "@/lib/publicAsk";

/**
 * Public inquiry-search box. Reused on the homepage (compact mode) and
 * on `/ask` (full mode). Pure retrieval — never freeform-generates
 * text. Posts to `/api/public/ask` and renders the bucketed result
 * lists with methodology + confidence pills.
 *
 * Keyboard contract:
 *   - `/` from anywhere on the page focuses the input (skipped if the
 *     user is already typing into a form).
 *   - Arrow Up / Arrow Down moves through the flat result list once a
 *     response has rendered.
 *   - Enter on a focused result navigates to that result's href.
 *   - Submit (Enter in the input) runs a query and, in compact mode,
 *     sends the reader to `/ask?q=...` so the dedicated page can host
 *     the keyboard-driven results UI.
 */

type Mode = "compact" | "full";

const KIND_ORDER: PublicAskKind[] = [
  "conclusion",
  "article",
  "opinion",
  "open_question",
];

const KIND_LABEL: Record<PublicAskKind, string> = {
  conclusion: "CONCLUSIONS",
  article: "ARTICLES",
  opinion: "OPINIONS · CURRENTS",
  open_question: "OPEN QUESTIONS",
};

const SUBMIT_DEBOUNCE_MS = 150;

export default function PublicAskBox({
  mode = "compact",
  initialQuery = "",
  autoFocus = false,
}: {
  mode?: Mode;
  initialQuery?: string;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(initialQuery);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<PublicAskResponse | null>(null);
  const [activeIdx, setActiveIdx] = useState(-1);

  const flatResults = useMemo(() => flattenResults(response), [response]);

  const submit = useCallback(
    async (raw: string) => {
      const trimmed = raw.trim();
      if (trimmed.length < 3) {
        setResponse(null);
        setError(null);
        return;
      }
      if (mode === "compact") {
        router.push(`/ask?q=${encodeURIComponent(trimmed)}`);
        return;
      }
      setPending(true);
      setError(null);
      try {
        const res = await fetch("/api/public/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: trimmed }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as { error?: string } | null;
          throw new Error(body?.error ?? `Request failed (${res.status})`);
        }
        const json = (await res.json()) as PublicAskResponse;
        setResponse(json);
        setActiveIdx(-1);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Retrieval failed");
        setResponse(null);
      } finally {
        setPending(false);
      }
    },
    [mode, router],
  );

  // Run the initial query on mount in full mode.
  useEffect(() => {
    if (mode !== "full") return;
    if (initialQuery.trim().length < 3) return;
    let cancelled = false;
    const handle = window.setTimeout(() => {
      if (cancelled) return;
      void submit(initialQuery);
    }, SUBMIT_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
    // submit is stable per-mode; intentional that we don't re-run on
    // every keystroke (we do that via the input handler instead).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, initialQuery]);

  // Slash-to-focus.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "/") return;
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      event.preventDefault();
      inputRef.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Arrow / enter navigation when results are present.
  useEffect(() => {
    if (mode !== "full") return;
    if (flatResults.length === 0) return;

    function onKey(event: KeyboardEvent) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIdx((idx) => Math.min(flatResults.length - 1, idx + 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIdx((idx) => Math.max(-1, idx - 1));
      } else if (event.key === "Enter") {
        const target = event.target as HTMLElement | null;
        if (target?.tagName === "INPUT") return;
        if (activeIdx < 0 || activeIdx >= flatResults.length) return;
        event.preventDefault();
        const href = flatResults[activeIdx].href;
        router.push(href);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode, flatResults, activeIdx, router]);

  return (
    <section
      aria-labelledby="public-ask-heading"
      data-testid="public-ask-box"
      style={{
        border: mode === "full" ? "1px solid var(--stroke)" : "none",
        padding: mode === "full" ? "1.4rem" : 0,
        background: mode === "full" ? "rgba(232, 225, 211, 0.025)" : "transparent",
      }}
    >
      <h2
        className="mono"
        id="public-ask-heading"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.72rem",
          letterSpacing: "0.3em",
          textTransform: "uppercase",
          margin: "0 0 0.85rem",
        }}
      >
        ASK THE FIRM
      </h2>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit(query);
        }}
        style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}
      >
        <label htmlFor="public-ask-input" className="visually-hidden" style={{ position: "absolute", left: -10000 }}>
          Ask the firm
        </label>
        <input
          ref={inputRef}
          autoFocus={autoFocus}
          id="public-ask-input"
          type="search"
          placeholder="Ask anything the firm has reasoned about — e.g. land value capture, monetary inflation"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          data-testid="public-ask-input"
          style={{
            flex: 1,
            minWidth: "16rem",
            background: "rgba(0,0,0,0.35)",
            border: "1px solid var(--stroke)",
            borderRadius: 4,
            color: "var(--parchment)",
            fontFamily: "'EB Garamond', serif",
            fontSize: "1rem",
            padding: "0.7rem 0.9rem",
          }}
        />
        <button
          type="submit"
          className="mono"
          disabled={pending}
          data-testid="public-ask-submit"
          style={{
            background: "var(--amber)",
            border: "1px solid var(--amber)",
            borderRadius: 3,
            color: "#120d08",
            fontWeight: 700,
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            padding: "0.7rem 1rem",
            textTransform: "uppercase",
            cursor: pending ? "wait" : "pointer",
          }}
        >
          {pending ? "Searching…" : "Search"}
        </button>
      </form>

      <p
        className="mono"
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.16em",
          marginTop: "0.6rem",
          textTransform: "uppercase",
        }}
      >
        Press <kbd>/</kbd> to focus · <kbd>↑</kbd>/<kbd>↓</kbd> to navigate · <kbd>Enter</kbd> to open
      </p>

      {error ? (
        <p role="alert" style={{ color: "var(--amber)", marginTop: "0.8rem" }}>
          {error}
        </p>
      ) : null}

      {mode === "full" && response ? (
        <ResultsView response={response} activeIdx={activeIdx} flat={flatResults} />
      ) : null}
    </section>
  );
}

function flattenResults(response: PublicAskResponse | null): PublicAskResult[] {
  if (!response) return [];
  const out: PublicAskResult[] = [];
  for (const kind of KIND_ORDER) {
    out.push(...response.results[kind]);
  }
  return out;
}

function ResultsView({
  response,
  activeIdx,
  flat,
}: {
  response: PublicAskResponse;
  activeIdx: number;
  flat: PublicAskResult[];
}) {
  const indexById = useMemo(() => {
    const map = new Map<string, number>();
    flat.forEach((item, i) => map.set(item.id, i));
    return map;
  }, [flat]);

  const totalResults = flat.length;
  const noHits = totalResults === 0;

  if (response.noResult || noHits) {
    return (
      <NoResultPanel response={response} />
    );
  }

  return (
    <div style={{ marginTop: "1.6rem" }} data-testid="public-ask-results">
      {response.suggestedRephrasings.length > 0 ? (
        <SuggestedRephrasings titles={response.suggestedRephrasings} />
      ) : null}

      {KIND_ORDER.map((kind) => {
        const items = response.results[kind];
        if (items.length === 0) return null;
        return (
          <section key={kind} style={{ marginBottom: "1.5rem" }} data-testid={`public-ask-rail-${kind}`}>
            <h3
              className="mono"
              style={{
                color: "var(--amber-dim)",
                fontSize: "0.62rem",
                letterSpacing: "0.28em",
                margin: "0 0 0.55rem",
                textTransform: "uppercase",
              }}
            >
              {KIND_LABEL[kind]}
            </h3>
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {items.map((item) => (
                <ResultRow
                  key={item.id}
                  item={item}
                  active={indexById.get(item.id) === activeIdx}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function NoResultPanel({ response }: { response: PublicAskResponse }) {
  return (
    <div
      data-testid="public-ask-no-result"
      style={{
        border: "1px solid var(--stroke)",
        marginTop: "1.6rem",
        padding: "1.2rem",
      }}
    >
      <p style={{ color: "var(--parchment)", margin: "0 0 0.65rem", fontStyle: "italic" }}>
        The firm has not addressed this directly.
      </p>
      {response.closestOpenQuestion ? (
        <>
          <p
            className="mono"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.6rem",
              letterSpacing: "0.22em",
              margin: "0 0 0.4rem",
              textTransform: "uppercase",
            }}
          >
            Closest open question
          </p>
          <a
            href={response.closestOpenQuestion.href}
            style={{
              color: "var(--amber)",
              fontFamily: "'Cinzel', serif",
              fontSize: "1.05rem",
              textDecoration: "none",
            }}
          >
            {response.closestOpenQuestion.title}
          </a>
        </>
      ) : (
        <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
          No published material currently matches this query.
        </p>
      )}
    </div>
  );
}

function SuggestedRephrasings({ titles }: { titles: string[] }) {
  return (
    <div
      data-testid="public-ask-rephrasings"
      style={{
        border: "1px dashed var(--stroke)",
        marginBottom: "1.4rem",
        padding: "0.8rem 1rem",
      }}
    >
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.22em",
          margin: "0 0 0.4rem",
          textTransform: "uppercase",
        }}
      >
        Did you mean
      </p>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
        {titles.map((title) => (
          <li key={title} style={{ color: "var(--parchment-dim)", fontStyle: "italic" }}>
            {title}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResultRow({ item, active }: { item: PublicAskResult; active: boolean }) {
  return (
    <li
      data-testid="public-ask-result-row"
      data-active={active ? "true" : undefined}
      style={{
        background: active ? "rgba(205, 151, 67, 0.08)" : "transparent",
        border: "1px solid rgba(232, 225, 211, 0.14)",
        borderRadius: 4,
        marginBottom: "0.65rem",
        padding: "0.85rem",
      }}
    >
      <a
        href={item.href}
        style={{
          color: "var(--amber)",
          fontFamily: "'Cinzel', serif",
          fontSize: "1.05rem",
          lineHeight: 1.25,
          textDecoration: "none",
        }}
      >
        {item.title}
      </a>
      <div
        style={{
          alignItems: "center",
          color: "var(--parchment-dim)",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.55rem",
          fontSize: "0.62rem",
          letterSpacing: "0.16em",
          marginTop: "0.45rem",
          textTransform: "uppercase",
        }}
        className="mono"
      >
        {item.methodology ? (
          <span data-testid="public-ask-methodology-pill" style={pillStyle("var(--gold-dim, var(--amber-dim))")}>
            METHOD · {item.methodology}
          </span>
        ) : null}
        {typeof item.confidence === "number" ? (
          <span data-testid="public-ask-confidence-pill" style={pillStyle("var(--amber-dim)")}>
            CONFIDENCE · {Math.round(item.confidence * 100)}%
          </span>
        ) : null}
        {item.topicHint ? (
          <span style={{ color: "var(--parchment-dim)" }}>{item.topicHint}</span>
        ) : null}
      </div>
      <p
        style={{
          color: "var(--parchment)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "0.97rem",
          lineHeight: 1.5,
          margin: "0.55rem 0 0",
        }}
      >
        {item.snippet}
      </p>
    </li>
  );
}

function pillStyle(color: string): React.CSSProperties {
  return {
    border: `1px solid ${color}`,
    borderRadius: 999,
    color,
    padding: "0.18rem 0.55rem",
  };
}
