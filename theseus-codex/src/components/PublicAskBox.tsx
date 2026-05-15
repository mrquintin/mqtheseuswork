"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  PublicAskKind,
  PublicAskQueryClass,
  PublicAskResponse,
  PublicAskResult,
} from "@/lib/publicAsk";

/**
 * Public inquiry-search box. Reused on the homepage (compact mode) and
 * on `/ask` (full mode). Pure retrieval — never freeform-generates
 * text. Posts to `/api/public/ask` and renders the bucketed result
 * lists with methodology + confidence + freshness pills.
 *
 * Round 17 prompt 28 added per-class rendering: the response carries a
 * `queryClass` and each class gets its own rail ordering and framing
 * (a prediction query leads with dated opinions, a counter-argument
 * query leads with open questions, etc.). The enriched no-result panel
 * surfaces the closest open question, the closest related conclusion,
 * and a research-suggestion form so a miss is a useful page.
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

const KIND_LABEL: Record<PublicAskKind, string> = {
  conclusion: "CONCLUSIONS",
  article: "ARTICLES",
  opinion: "OPINIONS · CURRENTS",
  open_question: "OPEN QUESTIONS",
};

/**
 * Per-class rail ordering. Mirrors the `kind_order` of the retrieval
 * profiles in `noosphere/inference/query_classifier.py` — each class
 * leads with the rail most likely to answer it.
 */
const CLASS_KIND_ORDER: Record<PublicAskQueryClass, PublicAskKind[]> = {
  "factual-claim": ["conclusion", "article", "opinion", "open_question"],
  "methodology-question": ["article", "open_question", "conclusion", "opinion"],
  "prediction-request": ["opinion", "conclusion", "open_question", "article"],
  "counter-argument-request": ["open_question", "opinion", "conclusion", "article"],
  browse: ["conclusion", "article", "opinion", "open_question"],
};

const CLASS_LABEL: Record<PublicAskQueryClass, string> = {
  "factual-claim": "FACTUAL CLAIM",
  "methodology-question": "METHODOLOGY QUESTION",
  "prediction-request": "PREDICTION REQUEST",
  "counter-argument-request": "COUNTER-ARGUMENT REQUEST",
  browse: "BROWSE",
};

const CLASS_BLURB: Record<PublicAskQueryClass, string> = {
  "factual-claim": "Read as a question of fact — leading with the firm's published conclusions.",
  "methodology-question":
    "Read as a methodology question — leading with method write-ups and the open questions behind them.",
  "prediction-request":
    "Read as a forward-looking question — leading with the firm's dated opinions. Note each result's date.",
  "counter-argument-request":
    "Read as a request for the other side — leading with the open questions and contradictions still on the table.",
  browse: "Browsing the firm's most relevant published material.",
};

const DEFAULT_KIND_ORDER = CLASS_KIND_ORDER.browse;

function kindOrderFor(response: PublicAskResponse | null): PublicAskKind[] {
  if (!response) return DEFAULT_KIND_ORDER;
  return CLASS_KIND_ORDER[response.queryClass] ?? DEFAULT_KIND_ORDER;
}

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

  const trimmedQuery = query.trim();
  const tooShort = trimmedQuery.length < 3;
  const submitDisabled = pending || tooShort;
  const submitDisabledReason = pending
    ? "Searching…"
    : tooShort
    ? "Type at least 3 characters"
    : "";

  const submit = useCallback(
    async (raw: string) => {
      const trimmed = raw.trim();
      if (trimmed.length < 3) {
        setResponse(null);
        setError(
          mode === "full" && trimmed.length > 0
            ? "Type at least 3 characters to search."
            : null,
        );
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
          disabled={submitDisabled}
          aria-busy={pending}
          data-testid="public-ask-submit"
          title={submitDisabledReason || "Search the firm (Enter)"}
          style={{
            background: submitDisabled ? "var(--amber-dim)" : "var(--amber)",
            border: `1px solid ${submitDisabled ? "var(--amber-dim)" : "var(--amber)"}`,
            borderRadius: 3,
            color: "#120d08",
            fontWeight: 700,
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            opacity: submitDisabled && !pending ? 0.7 : 1,
            padding: "0.7rem 1rem",
            textTransform: "uppercase",
            cursor: pending ? "wait" : submitDisabled ? "not-allowed" : "pointer",
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
        <p
          role="alert"
          data-testid="public-ask-error"
          style={{ color: "var(--amber)", marginTop: "0.8rem" }}
        >
          {error}
        </p>
      ) : null}

      {mode === "full" && pending ? (
        <p
          aria-live="polite"
          className="mono"
          data-testid="public-ask-pending"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.62rem",
            letterSpacing: "0.22em",
            marginTop: "1.2rem",
            textTransform: "uppercase",
          }}
        >
          Searching the firm's published material…
        </p>
      ) : null}

      {mode === "full" && !pending && !response && !error ? (
        <p
          data-testid="public-ask-empty"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.95rem",
            fontStyle: "italic",
            lineHeight: 1.55,
            marginTop: "1.2rem",
          }}
        >
          Type a question above and press Enter or Search. We return only
          what the firm has actually published — never a paraphrase.
        </p>
      ) : null}

      {mode === "full" && response && !pending ? (
        <ResultsView response={response} activeIdx={activeIdx} flat={flatResults} />
      ) : null}
    </section>
  );
}

function flattenResults(response: PublicAskResponse | null): PublicAskResult[] {
  if (!response) return [];
  const out: PublicAskResult[] = [];
  for (const kind of kindOrderFor(response)) {
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
      <QueryClassBadge queryClass={response.queryClass} />

      {response.suggestedRephrasings.length > 0 ? (
        <SuggestedRephrasings titles={response.suggestedRephrasings} />
      ) : null}

      {kindOrderFor(response).map((kind) => {
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

function QueryClassBadge({ queryClass }: { queryClass: PublicAskQueryClass }) {
  const label = CLASS_LABEL[queryClass] ?? CLASS_LABEL.browse;
  const blurb = CLASS_BLURB[queryClass] ?? CLASS_BLURB.browse;
  return (
    <div
      data-testid="public-ask-query-class"
      data-query-class={queryClass}
      style={{
        alignItems: "baseline",
        display: "flex",
        flexWrap: "wrap",
        gap: "0.6rem",
        marginBottom: "1.2rem",
      }}
    >
      <span
        className="mono"
        style={{
          ...pillStyle("var(--amber)"),
          fontSize: "0.6rem",
          letterSpacing: "0.2em",
        }}
      >
        {label}
      </span>
      <span
        style={{
          color: "var(--parchment-dim)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "0.9rem",
          fontStyle: "italic",
        }}
      >
        {blurb}
      </span>
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
      <QueryClassBadge queryClass={response.queryClass} />

      <p style={{ color: "var(--parchment)", margin: "0 0 1.1rem", fontStyle: "italic" }}>
        The firm has not addressed this directly. Here is the closest
        material the firm <em>has</em> published — and a way to put this
        question on the firm's radar.
      </p>

      {response.closestOpenQuestion ? (
        <NoResultPointer
          testid="public-ask-closest-open-question"
          label="Closest open question"
          item={response.closestOpenQuestion}
        />
      ) : null}

      {response.closestRelatedConclusion ? (
        <NoResultPointer
          testid="public-ask-closest-conclusion"
          label="Closest related conclusion"
          item={response.closestRelatedConclusion}
        />
      ) : null}

      {!response.closestOpenQuestion && !response.closestRelatedConclusion ? (
        <p style={{ color: "var(--parchment-dim)", margin: "0 0 1.1rem" }}>
          No published material currently matches this query.
        </p>
      ) : null}

      <ResearchSuggestionForm />
    </div>
  );
}

function NoResultPointer({
  testid,
  label,
  item,
}: {
  testid: string;
  label: string;
  item: PublicAskResult;
}) {
  return (
    <div data-testid={testid} style={{ marginBottom: "1.1rem" }}>
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
        {label}
      </p>
      <a
        href={item.href}
        style={{
          color: "var(--amber)",
          fontFamily: "'Cinzel', serif",
          fontSize: "1.05rem",
          textDecoration: "none",
        }}
      >
        {item.title}
      </a>
      <div style={{ marginTop: "0.35rem" }}>
        <FreshnessPill item={item} />
      </div>
      {item.snippet ? (
        <p
          style={{
            color: "var(--parchment)",
            fontFamily: "'EB Garamond', serif",
            fontSize: "0.92rem",
            lineHeight: 1.5,
            margin: "0.4rem 0 0",
          }}
        >
          {item.snippet}
        </p>
      ) : null}
    </div>
  );
}

/**
 * "Submit a research suggestion" form. The only write on the public
 * ask surface — it stores what the reader types, verbatim, into the
 * `ResearchSuggestion` model via `POST /api/public/ask`. The reader's
 * search query is deliberately not attached (query-log discipline).
 */
function ResearchSuggestionForm() {
  const [title, setTitle] = useState("");
  const [rationale, setRationale] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const trimmedTitle = title.trim();
  const canSubmit = trimmedTitle.length >= 8 && status !== "sending";

  const onSubmit = useCallback(async () => {
    if (trimmedTitle.length < 8) {
      setStatus("error");
      setErrorMsg("Give the suggestion a title of at least 8 characters.");
      return;
    }
    setStatus("sending");
    setErrorMsg(null);
    try {
      const res = await fetch("/api/public/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          suggestion: { title: trimmedTitle, rationale: rationale.trim() },
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `Request failed (${res.status})`);
      }
      setStatus("sent");
      setTitle("");
      setRationale("");
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Could not save suggestion");
    }
  }, [trimmedTitle, rationale]);

  if (status === "sent") {
    return (
      <div
        data-testid="public-ask-suggestion-sent"
        style={{
          borderTop: "1px solid var(--stroke)",
          color: "var(--parchment)",
          fontStyle: "italic",
          marginTop: "0.4rem",
          paddingTop: "1rem",
        }}
      >
        Thank you — your suggestion is on the firm's research queue.
      </div>
    );
  }

  return (
    <form
      data-testid="public-ask-suggestion-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit();
      }}
      style={{
        borderTop: "1px solid var(--stroke)",
        marginTop: "0.4rem",
        paddingTop: "1rem",
      }}
    >
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.22em",
          margin: "0 0 0.55rem",
          textTransform: "uppercase",
        }}
      >
        Submit a research suggestion
      </p>
      <label
        htmlFor="public-ask-suggestion-title"
        className="visually-hidden"
        style={{ position: "absolute", left: -10000 }}
      >
        Suggestion title
      </label>
      <input
        id="public-ask-suggestion-title"
        type="text"
        data-testid="public-ask-suggestion-title"
        placeholder="What should the firm investigate?"
        value={title}
        maxLength={240}
        onChange={(event) => setTitle(event.target.value)}
        style={{
          background: "rgba(0,0,0,0.35)",
          border: "1px solid var(--stroke)",
          borderRadius: 4,
          color: "var(--parchment)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "0.95rem",
          padding: "0.6rem 0.8rem",
          width: "100%",
        }}
      />
      <label
        htmlFor="public-ask-suggestion-rationale"
        className="visually-hidden"
        style={{ position: "absolute", left: -10000 }}
      >
        Why this matters (optional)
      </label>
      <textarea
        id="public-ask-suggestion-rationale"
        data-testid="public-ask-suggestion-rationale"
        placeholder="Why does this matter? (optional)"
        value={rationale}
        maxLength={2000}
        rows={2}
        onChange={(event) => setRationale(event.target.value)}
        style={{
          background: "rgba(0,0,0,0.35)",
          border: "1px solid var(--stroke)",
          borderRadius: 4,
          color: "var(--parchment)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "0.95rem",
          marginTop: "0.5rem",
          padding: "0.6rem 0.8rem",
          resize: "vertical",
          width: "100%",
        }}
      />
      {status === "error" && errorMsg ? (
        <p
          role="alert"
          data-testid="public-ask-suggestion-error"
          style={{ color: "var(--amber)", fontSize: "0.85rem", margin: "0.5rem 0 0" }}
        >
          {errorMsg}
        </p>
      ) : null}
      <button
        type="submit"
        className="mono"
        disabled={!canSubmit}
        data-testid="public-ask-suggestion-submit"
        style={{
          background: canSubmit ? "var(--amber)" : "var(--amber-dim)",
          border: `1px solid ${canSubmit ? "var(--amber)" : "var(--amber-dim)"}`,
          borderRadius: 3,
          color: "#120d08",
          cursor: canSubmit ? "pointer" : "not-allowed",
          fontSize: "0.66rem",
          fontWeight: 700,
          letterSpacing: "0.18em",
          marginTop: "0.7rem",
          opacity: canSubmit ? 1 : 0.7,
          padding: "0.6rem 1rem",
          textTransform: "uppercase",
        }}
      >
        {status === "sending" ? "Sending…" : "Send suggestion"}
      </button>
    </form>
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
        <FreshnessPill item={item} />
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

function formatDate(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "";
  return new Date(ts).toISOString().slice(0, 10);
}

/**
 * Freshness signal. Every result carries its date and whether the firm
 * still considers it current. A stale result is *shown as stale* — it
 * is never silently de-ranked, so the reader can judge it themselves.
 */
function FreshnessPill({ item }: { item: PublicAskResult }) {
  const date = formatDate(item.occurredAt);
  const current = item.isCurrent !== false;
  const color = current ? "var(--amber-dim)" : "var(--amber)";
  return (
    <span
      data-testid="public-ask-freshness-pill"
      data-current={current ? "true" : "false"}
      style={pillStyle(color)}
    >
      {date ? `${date} · ` : ""}
      {current ? "STILL CURRENT" : "STALE"}
    </span>
  );
}
