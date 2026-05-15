"use client";

import { useCallback, useMemo, useState } from "react";

/**
 * Client surface for the re-extraction queue.
 *
 * Render order per row (top → bottom):
 *
 *   1. Source span (verbatim, monospace) — the citation the
 *      principle must preserve.
 *   2. Existing first-person text — what the corpus shows today.
 *   3. Proposed principle-shaped rewrite — editable textarea, so the
 *      founder can edit-then-accept in a single gesture.
 *   4. Accept / Edit / Reject — one of these MUST be clicked to make
 *      a write; refreshing the page resets state for un-actioned rows.
 *
 * The HTTP surface for accept / reject lives at
 * `/api/extractor/re-extract` (not introduced by this prompt — the
 * founder may want to defer the publish-side until after the offline
 * backfill produces high-quality proposals). The client surfaces an
 * informative banner when an action fails so the founder isn't left
 * wondering whether their click took.
 */

export type ReExtractRow = {
  id: string;
  currentText: string;
  sourceSpan: string;
  proposedText: string;
  createdAt: string;
};

type RowStatus = "pending" | "accepted" | "rejected" | "error";

export default function ReExtractClient({ rows }: { rows: ReExtractRow[] }) {
  const [state, setState] = useState<
    Record<string, { proposed: string; status: RowStatus; error?: string }>
  >(() =>
    Object.fromEntries(
      rows.map((r) => [r.id, { proposed: r.proposedText, status: "pending" as RowStatus }]),
    ),
  );

  const setProposed = useCallback((id: string, proposed: string) => {
    setState((s) => ({ ...s, [id]: { ...s[id], proposed } }));
  }, []);

  const dispatch = useCallback(
    async (id: string, verdict: "accept" | "reject") => {
      const row = state[id];
      if (!row) return;
      if (verdict === "accept" && row.proposed.trim().length < 12) {
        setState((s) => ({
          ...s,
          [id]: {
            ...s[id],
            status: "error",
            error: "Rewrite must be at least 12 characters before accepting.",
          },
        }));
        return;
      }
      try {
        const res = await fetch("/api/extractor/re-extract", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            conclusionId: id,
            verdict,
            text: verdict === "accept" ? row.proposed.trim() : null,
          }),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        setState((s) => ({
          ...s,
          [id]: { ...s[id], status: verdict === "accept" ? "accepted" : "rejected" },
        }));
      } catch (e) {
        setState((s) => ({
          ...s,
          [id]: {
            ...s[id],
            status: "error",
            error: e instanceof Error ? e.message : "Request failed",
          },
        }));
      }
    },
    [state],
  );

  const pendingCount = useMemo(
    () => Object.values(state).filter((s) => s.status === "pending").length,
    [state],
  );

  if (rows.length === 0) {
    return (
      <p style={{ opacity: 0.75 }}>
        No first-person conclusions in the queue. The extractor is
        producing principle-shaped output, or the legacy corpus has
        already been triaged.
      </p>
    );
  }

  return (
    <div>
      <p style={{ opacity: 0.6, fontSize: "0.85rem", marginTop: 0 }}>
        {pendingCount} pending action
      </p>
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {rows.map((row) => {
          const rowState = state[row.id];
          return (
            <li
              key={row.id}
              style={{
                border: "1px solid var(--line, #2a2a2a)",
                borderRadius: "0.5rem",
                padding: "1rem 1.25rem",
                marginBottom: "1rem",
                opacity:
                  rowState.status === "accepted" || rowState.status === "rejected"
                    ? 0.55
                    : 1,
              }}
            >
              <header
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "0.75rem",
                  opacity: 0.65,
                  marginBottom: "0.5rem",
                }}
              >
                <span>conclusion · {row.id.slice(0, 8)}</span>
                <span>{new Date(row.createdAt).toLocaleDateString()}</span>
              </header>

              <section style={{ marginBottom: "0.65rem" }}>
                <h3 style={{ fontSize: "0.8rem", opacity: 0.7, margin: "0 0 0.25rem" }}>
                  source span
                </h3>
                <blockquote
                  style={{
                    fontFamily: "monospace",
                    fontSize: "0.85rem",
                    margin: 0,
                    padding: "0.5rem 0.75rem",
                    borderLeft: "3px solid var(--amber, #c98c1a)",
                    background: "rgba(255,255,255,0.02)",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {row.sourceSpan || "— (no source span captured)"}
                </blockquote>
              </section>

              <section style={{ marginBottom: "0.65rem" }}>
                <h3 style={{ fontSize: "0.8rem", opacity: 0.7, margin: "0 0 0.25rem" }}>
                  existing (first-person)
                </h3>
                <p style={{ margin: 0, fontStyle: "italic" }}>{row.currentText}</p>
              </section>

              <section style={{ marginBottom: "0.65rem" }}>
                <label
                  htmlFor={`proposed-${row.id}`}
                  style={{
                    display: "block",
                    fontSize: "0.8rem",
                    opacity: 0.7,
                    margin: "0 0 0.25rem",
                  }}
                >
                  proposed principle (edit before accepting)
                </label>
                <textarea
                  id={`proposed-${row.id}`}
                  value={rowState.proposed}
                  onChange={(e) => setProposed(row.id, e.target.value)}
                  placeholder="Third-person decision rule — leave blank to reject."
                  rows={3}
                  disabled={
                    rowState.status === "accepted" || rowState.status === "rejected"
                  }
                  style={{
                    width: "100%",
                    fontFamily: "inherit",
                    fontSize: "0.95rem",
                    padding: "0.5rem 0.75rem",
                    borderRadius: "0.35rem",
                    border: "1px solid var(--line, #2a2a2a)",
                    background: "rgba(255,255,255,0.03)",
                    color: "inherit",
                  }}
                />
              </section>

              <footer style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
                <button
                  type="button"
                  onClick={() => dispatch(row.id, "accept")}
                  disabled={
                    rowState.status === "accepted" || rowState.status === "rejected"
                  }
                  style={{
                    padding: "0.4rem 0.85rem",
                    borderRadius: "0.35rem",
                    border: "1px solid var(--amber, #c98c1a)",
                    background: "rgba(201,140,26,0.18)",
                    color: "inherit",
                    cursor: "pointer",
                  }}
                >
                  Accept
                </button>
                <button
                  type="button"
                  onClick={() => dispatch(row.id, "reject")}
                  disabled={
                    rowState.status === "accepted" || rowState.status === "rejected"
                  }
                  style={{
                    padding: "0.4rem 0.85rem",
                    borderRadius: "0.35rem",
                    border: "1px solid var(--line, #2a2a2a)",
                    background: "transparent",
                    color: "inherit",
                    cursor: "pointer",
                  }}
                >
                  Reject
                </button>
                <span style={{ marginLeft: "auto", fontSize: "0.8rem", opacity: 0.7 }}>
                  {rowState.status === "accepted" && "✓ accepted"}
                  {rowState.status === "rejected" && "✗ rejected"}
                  {rowState.status === "error" && (
                    <span style={{ color: "var(--err, #d97757)" }}>
                      error · {rowState.error}
                    </span>
                  )}
                </span>
              </footer>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
