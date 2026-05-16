"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useTransition,
  type CSSProperties,
} from "react";

import type { AlgorithmRow } from "@/lib/algorithmsApi";

/**
 * Founder triage queue — interactive layer.
 *
 * The server component (`page.tsx`) fetches the DRAFT + UNDER_REVIEW
 * rows and threads server actions (accept / reject / merge) down to
 * this client component.  The keyboard navigation matches the
 * principle-queue conventions so the founder can move between the
 * two triage surfaces without re-learning bindings:
 *
 *   - `j` / `k` (or `↓` / `↑`) move the selection through the queue.
 *   - `Enter` opens the selected row's accept-with-edit panel.
 *   - `a` accepts the selected row as-is.
 *   - `r` toggles the reject panel.
 *   - `m` toggles the merge panel.
 *   - `b` runs bulk-accept with an individual gate check per row.
 *
 * The agent's draft is advisory; the founder publishes — the bulk
 * action fires one server action per row so any per-row failure
 * surfaces immediately rather than getting buried in a batch.
 */

type Action = (formData: FormData) => void | Promise<void>;

export type QueueClientProps = {
  rows: AlgorithmRow[];
  acceptAction: Action;
  rejectAction: Action;
  mergeAction: Action;
};

const cardStyle: CSSProperties = {
  border: "1px solid var(--amber-dim, #6b5b2c)",
  borderRadius: "6px",
  padding: "1.25rem 1.5rem",
  marginBottom: "1rem",
  background: "rgba(0, 0, 0, 0.15)",
};

const cardSelectedStyle: CSSProperties = {
  ...cardStyle,
  borderColor: "var(--amber, #d4a017)",
  boxShadow: "0 0 0 1px var(--amber, #d4a017)",
};

const monoSmall: CSSProperties = {
  fontSize: "0.65rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "var(--parchment-dim)",
};

export default function QueueClient({
  rows,
  acceptAction,
  rejectAction,
  mergeAction,
}: QueueClientProps) {
  const [selected, setSelected] = useState(0);
  const [editOpen, setEditOpen] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState<string | null>(null);
  const [mergeOpen, setMergeOpen] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [bulkProgress, setBulkProgress] = useState<{
    total: number;
    done: number;
    failed: string[];
  } | null>(null);

  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const move = useCallback((delta: number) => {
    setSelected((current) => {
      const n = rowsRef.current.length;
      if (n === 0) return 0;
      return (current + delta + n) % n;
    });
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (
          tag === "INPUT" ||
          tag === "TEXTAREA" ||
          tag === "SELECT" ||
          target.isContentEditable
        ) {
          return;
        }
      }
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        move(1);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        move(-1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const row = rowsRef.current[selected];
        if (row) setEditOpen(row.id);
      } else if (e.key === "a") {
        const row = rowsRef.current[selected];
        if (!row) return;
        const fd = new FormData();
        fd.set("id", row.id);
        startTransition(() => {
          acceptAction(fd);
        });
      } else if (e.key === "r") {
        const row = rowsRef.current[selected];
        if (!row) return;
        setRejectOpen((current) => (current === row.id ? null : row.id));
      } else if (e.key === "m") {
        const row = rowsRef.current[selected];
        if (!row) return;
        setMergeOpen((current) => (current === row.id ? null : row.id));
      } else if (e.key === "b") {
        runBulkAccept();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [move, selected, acceptAction]);

  const runBulkAccept = useCallback(() => {
    // Bulk-accept with individual gate check: fire the server action
    // one row at a time, so a per-row validation failure surfaces
    // immediately and does not poison the rest of the batch.
    const ids = rowsRef.current.map((r) => r.id);
    if (ids.length === 0) return;
    setBulkProgress({ total: ids.length, done: 0, failed: [] });
    void (async () => {
      for (const id of ids) {
        const fd = new FormData();
        fd.set("id", id);
        try {
          await Promise.resolve(acceptAction(fd));
          setBulkProgress((prev) =>
            prev ? { ...prev, done: prev.done + 1 } : prev,
          );
        } catch (err) {
          setBulkProgress((prev) =>
            prev
              ? { ...prev, done: prev.done + 1, failed: [...prev.failed, id] }
              : prev,
          );
        }
      }
    })();
  }, [acceptAction]);

  return (
    <section>
      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <button
          type="button"
          data-testid="bulk-accept-button"
          onClick={runBulkAccept}
          disabled={rows.length === 0 || isPending}
          style={{
            border: "1px solid var(--amber-dim)",
            background: "transparent",
            color: "var(--amber)",
            padding: "0.4rem 0.8rem",
            cursor: "pointer",
          }}
        >
          Bulk accept ({rows.length}) · gate-checked per row
        </button>
        <span className="mono" style={monoSmall}>
          j/k navigate · enter edit · a accept · r reject · m merge · b bulk
        </span>
      </div>
      {bulkProgress ? (
        <p
          className="mono"
          data-testid="bulk-progress"
          style={{ ...monoSmall, marginBottom: "1rem" }}
        >
          bulk · {bulkProgress.done}/{bulkProgress.total}
          {bulkProgress.failed.length > 0
            ? ` · failed: ${bulkProgress.failed.join(", ")}`
            : null}
        </p>
      ) : null}

      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {rows.map((row, index) => {
          const selectedRow = index === selected;
          const isEditing = editOpen === row.id;
          const isRejecting = rejectOpen === row.id;
          const isMerging = mergeOpen === row.id;
          return (
            <li
              key={row.id}
              data-testid="algorithm-row"
              data-row-id={row.id}
              style={selectedRow ? cardSelectedStyle : cardStyle}
              onClick={() => setSelected(index)}
            >
              <header style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
                <h2
                  style={{
                    fontFamily: "'Cinzel', serif",
                    fontSize: "1.1rem",
                    margin: 0,
                    color: "var(--amber)",
                  }}
                >
                  {row.name}
                </h2>
                <span className="mono" style={monoSmall}>
                  {row.status}
                </span>
              </header>
              {row.description ? (
                <p
                  style={{
                    margin: "0.5rem 0 0.75rem",
                    fontFamily: "'EB Garamond', serif",
                    lineHeight: 1.5,
                    color: "var(--parchment)",
                  }}
                >
                  {row.description}
                </p>
              ) : null}
              <p className="mono" style={monoSmall}>
                source principles ·{" "}
                {row.sourcePrincipleIds.length > 0
                  ? row.sourcePrincipleIds.map((pid, i) => (
                      <span key={pid}>
                        <Link
                          href={`/principles/${pid}`}
                          style={{ color: "var(--amber-dim)" }}
                        >
                          {pid}
                        </Link>
                        {i < row.sourcePrincipleIds.length - 1 ? ", " : ""}
                      </span>
                    ))
                  : "—"}
              </p>

              <details style={{ marginTop: "0.75rem" }} open={selectedRow}>
                <summary
                  className="mono"
                  style={{ ...monoSmall, cursor: "pointer" }}
                >
                  inputs · {row.inputs.length}
                </summary>
                <ul style={{ marginTop: "0.4rem", paddingLeft: "1.25rem" }}>
                  {row.inputs.map((inp) => (
                    <li key={inp.name} style={{ marginBottom: "0.25rem" }}>
                      <code>{inp.name}</code>{" "}
                      <span className="mono" style={monoSmall}>
                        ({inp.type})
                      </span>{" "}
                      <span style={{ color: "var(--parchment-dim)" }}>
                        — {inp.description}
                      </span>{" "}
                      <span className="mono" style={monoSmall}>
                        src: {inp.observability_source}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>

              <details style={{ marginTop: "0.5rem" }}>
                <summary
                  className="mono"
                  style={{ ...monoSmall, cursor: "pointer" }}
                >
                  output · {row.output.name} ({row.output.type})
                </summary>
                <p style={{ margin: "0.4rem 0", color: "var(--parchment)" }}>
                  {row.output.description}
                </p>
                {row.output.range ? (
                  <p className="mono" style={monoSmall}>
                    range · [{row.output.range[0]}, {row.output.range[1]}]
                  </p>
                ) : null}
              </details>

              <details style={{ marginTop: "0.5rem" }} open={selectedRow}>
                <summary
                  className="mono"
                  style={{ ...monoSmall, cursor: "pointer" }}
                >
                  reasoning chain · {row.reasoningChain.length} steps
                </summary>
                <ol style={{ marginTop: "0.4rem", paddingLeft: "1.5rem" }}>
                  {row.reasoningChain.map((step, i) => (
                    <li key={i} style={{ marginBottom: "0.25rem" }}>
                      <span className="mono" style={monoSmall}>
                        {step.step_kind}
                      </span>
                      {step.principle_id ? (
                        <>
                          {" · "}
                          <Link
                            href={`/principles/${step.principle_id}`}
                            style={{ color: "var(--amber-dim)" }}
                          >
                            {step.principle_id}
                          </Link>
                        </>
                      ) : null}
                      {step.predicate ? (
                        <>
                          {" · "}
                          <code>{step.predicate}</code>
                        </>
                      ) : null}
                      {step.derived_fact ? (
                        <span style={{ color: "var(--parchment)" }}>
                          {" "}
                          — {step.derived_fact}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </details>

              <p
                className="mono"
                style={{ ...monoSmall, marginTop: "0.5rem" }}
              >
                trigger · <code>{row.triggerPredicate}</code>
              </p>
              {row.confidenceNote ? (
                <p
                  style={{
                    fontStyle: "italic",
                    color: "var(--parchment-dim)",
                    marginTop: "0.5rem",
                  }}
                >
                  drafter note: {row.confidenceNote}
                </p>
              ) : null}

              <div
                style={{
                  marginTop: "1rem",
                  display: "flex",
                  gap: "0.5rem",
                  flexWrap: "wrap",
                }}
              >
                <form action={acceptAction}>
                  <input type="hidden" name="id" value={row.id} />
                  <button
                    type="submit"
                    data-testid="accept-button"
                    data-row-id={row.id}
                    style={{
                      border: "1px solid var(--amber)",
                      background: "var(--amber)",
                      color: "#000",
                      padding: "0.35rem 0.75rem",
                      cursor: "pointer",
                    }}
                  >
                    Accept
                  </button>
                </form>
                <button
                  type="button"
                  data-testid="accept-with-edit-button"
                  data-row-id={row.id}
                  onClick={() => setEditOpen(isEditing ? null : row.id)}
                  style={{
                    border: "1px solid var(--amber-dim)",
                    background: "transparent",
                    color: "var(--amber)",
                    padding: "0.35rem 0.75rem",
                    cursor: "pointer",
                  }}
                >
                  Accept with edit
                </button>
                <button
                  type="button"
                  data-testid="reject-toggle"
                  data-row-id={row.id}
                  onClick={() => setRejectOpen(isRejecting ? null : row.id)}
                  style={{
                    border: "1px solid var(--ember, #c0392b)",
                    background: "transparent",
                    color: "var(--ember, #c0392b)",
                    padding: "0.35rem 0.75rem",
                    cursor: "pointer",
                  }}
                >
                  Reject
                </button>
                <button
                  type="button"
                  data-testid="merge-toggle"
                  data-row-id={row.id}
                  onClick={() => setMergeOpen(isMerging ? null : row.id)}
                  style={{
                    border: "1px solid var(--parchment-dim)",
                    background: "transparent",
                    color: "var(--parchment-dim)",
                    padding: "0.35rem 0.75rem",
                    cursor: "pointer",
                  }}
                >
                  Merge with existing
                </button>
              </div>

              {isEditing ? (
                <form
                  action={acceptAction}
                  data-testid="accept-edit-form"
                  data-row-id={row.id}
                  style={{ marginTop: "0.75rem" }}
                >
                  <input type="hidden" name="id" value={row.id} />
                  <label style={{ display: "block", marginBottom: "0.4rem" }}>
                    <span className="mono" style={monoSmall}>
                      name
                    </span>
                    <input
                      type="text"
                      name="name"
                      defaultValue={row.name}
                      style={{
                        width: "100%",
                        padding: "0.35rem",
                        background: "transparent",
                        border: "1px solid var(--amber-dim)",
                        color: "var(--parchment)",
                      }}
                    />
                  </label>
                  <label style={{ display: "block", marginBottom: "0.4rem" }}>
                    <span className="mono" style={monoSmall}>
                      description
                    </span>
                    <textarea
                      name="description"
                      defaultValue={row.description}
                      rows={3}
                      style={{
                        width: "100%",
                        padding: "0.35rem",
                        background: "transparent",
                        border: "1px solid var(--amber-dim)",
                        color: "var(--parchment)",
                      }}
                    />
                  </label>
                  <label style={{ display: "block", marginBottom: "0.4rem" }}>
                    <span className="mono" style={monoSmall}>
                      trigger predicate
                    </span>
                    <input
                      type="text"
                      name="triggerPredicate"
                      defaultValue={row.triggerPredicate}
                      style={{
                        width: "100%",
                        padding: "0.35rem",
                        background: "transparent",
                        border: "1px solid var(--amber-dim)",
                        color: "var(--parchment)",
                        fontFamily: "monospace",
                      }}
                    />
                  </label>
                  <button
                    type="submit"
                    data-testid="accept-edit-submit"
                    style={{
                      border: "1px solid var(--amber)",
                      background: "var(--amber)",
                      color: "#000",
                      padding: "0.35rem 0.75rem",
                      cursor: "pointer",
                    }}
                  >
                    Accept with edits
                  </button>
                </form>
              ) : null}

              {isRejecting ? (
                <form
                  action={rejectAction}
                  data-testid="reject-form"
                  data-row-id={row.id}
                  style={{ marginTop: "0.75rem" }}
                >
                  <input type="hidden" name="id" value={row.id} />
                  <label style={{ display: "block", marginBottom: "0.4rem" }}>
                    <span className="mono" style={monoSmall}>
                      reason
                    </span>
                    <textarea
                      name="reason"
                      required
                      rows={2}
                      style={{
                        width: "100%",
                        padding: "0.35rem",
                        background: "transparent",
                        border: "1px solid var(--ember, #c0392b)",
                        color: "var(--parchment)",
                      }}
                    />
                  </label>
                  <button
                    type="submit"
                    style={{
                      border: "1px solid var(--ember, #c0392b)",
                      background: "transparent",
                      color: "var(--ember, #c0392b)",
                      padding: "0.35rem 0.75rem",
                      cursor: "pointer",
                    }}
                  >
                    Confirm reject
                  </button>
                </form>
              ) : null}

              {isMerging ? (
                <form
                  action={mergeAction}
                  data-testid="merge-form"
                  data-row-id={row.id}
                  style={{ marginTop: "0.75rem" }}
                >
                  <input type="hidden" name="id" value={row.id} />
                  <label style={{ display: "block", marginBottom: "0.4rem" }}>
                    <span className="mono" style={monoSmall}>
                      merge into algorithm id
                    </span>
                    <input
                      type="text"
                      name="intoId"
                      required
                      style={{
                        width: "100%",
                        padding: "0.35rem",
                        background: "transparent",
                        border: "1px solid var(--parchment-dim)",
                        color: "var(--parchment)",
                      }}
                    />
                  </label>
                  <button
                    type="submit"
                    style={{
                      border: "1px solid var(--parchment-dim)",
                      background: "transparent",
                      color: "var(--parchment-dim)",
                      padding: "0.35rem 0.75rem",
                      cursor: "pointer",
                    }}
                  >
                    Confirm merge
                  </button>
                </form>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
