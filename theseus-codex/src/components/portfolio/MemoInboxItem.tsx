"use client";

import { useState, useTransition } from "react";

import { acknowledgeDispatchAction } from "@/app/(authed)/portfolio-agents/[id]/inbox/actions";

export type EightGateStatus = Record<string, boolean>;

export type MemoInboxItemProps = {
  dispatchId: string;
  agentId: string;
  memoId: string;
  memoTitle: string;
  memoTldr: string;
  questionType: string;
  dispatchedAt: string;
  eightGateStatus: EightGateStatus;
  bodyMarkdown: string;
};

const ACCEPT_AND_BET = "ACCEPTED_AND_BET";
const ACCEPT_NO_BET = "ACCEPTED_NO_BET";
const REJECT = "REJECTED";
const DEFER = "DEFERRED";

function GateBadge({ name, ok }: { name: string; ok: boolean }) {
  return (
    <span
      className="mono"
      style={{
        fontSize: "0.72rem",
        marginRight: "0.4rem",
        color: ok ? "var(--ok, #4ade80)" : "var(--warn, #f97316)",
      }}
    >
      {ok ? "✅" : "⬜"} {name}
    </span>
  );
}

/**
 * `<MemoInboxItem>` — a single PENDING dispatch with full memo body
 * and the four operator actions: ACCEPT-AND-BET, ACCEPT-NO-BET,
 * REJECT, DEFER. The eight-gate readiness panel is re-evaluated at
 * click time on the server (the inbox snapshot is informational only)
 * and surface failures inline.
 */
export default function MemoInboxItem(props: MemoInboxItemProps) {
  const [rationale, setRationale] = useState("");
  const [deferUntil, setDeferUntil] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [gateFailures, setGateFailures] = useState<string[]>([]);
  const [resolved, setResolved] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const gateNames = Object.keys(props.eightGateStatus || {});
  const failingGates = gateNames.filter((g) => !props.eightGateStatus[g]);

  function handleAction(outcome: string) {
    setError(null);
    setGateFailures([]);

    if (outcome === REJECT && rationale.trim().length < 20) {
      setError("REJECT requires a rationale of at least 20 characters.");
      return;
    }
    if (outcome === DEFER && !deferUntil) {
      setError("DEFER requires a defer-until timestamp.");
      return;
    }

    startTransition(async () => {
      const result = await acknowledgeDispatchAction({
        dispatchId: props.dispatchId,
        agentId: props.agentId,
        outcome,
        rationale: rationale.trim(),
        deferredUntil: outcome === DEFER ? deferUntil : null,
      });
      if (!result.ok) {
        if (result.failingGates && result.failingGates.length > 0) {
          setGateFailures(result.failingGates);
        }
        setError(result.error || "Action failed.");
        return;
      }
      setResolved(outcome);
    });
  }

  if (resolved) {
    return (
      <article
        className="mono"
        style={{
          padding: "1rem",
          marginBottom: "1rem",
          border: "1px solid var(--rule)",
          opacity: 0.6,
        }}
      >
        Dispatch resolved as <strong>{resolved.toLowerCase()}</strong>.
      </article>
    );
  }

  return (
    <article
      style={{
        padding: "1rem",
        marginBottom: "1.25rem",
        border: "1px solid var(--rule)",
      }}
      data-testid="memo-inbox-item"
      data-dispatch-id={props.dispatchId}
    >
      <header style={{ marginBottom: "0.6rem" }}>
        <h3 style={{ margin: 0 }}>{props.memoTitle || props.memoId}</h3>
        <p
          className="mono"
          style={{ color: "var(--amber-dim)", fontSize: "0.78rem" }}
        >
          {props.questionType.toLowerCase()} · dispatched{" "}
          {new Date(props.dispatchedAt).toISOString().slice(0, 19).replace("T", " ")}
        </p>
      </header>

      {props.memoTldr ? <p>{props.memoTldr}</p> : null}

      <details style={{ margin: "0.6rem 0 0.8rem" }}>
        <summary className="mono" style={{ fontSize: "0.85rem", cursor: "pointer" }}>
          Full memo body (10-section view)
        </summary>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            fontSize: "0.78rem",
            padding: "0.75rem",
            background: "var(--surface-1, rgba(0,0,0,0.2))",
            marginTop: "0.5rem",
          }}
        >
          {props.bodyMarkdown || "(memo body not yet rendered)"}
        </pre>
      </details>

      <div style={{ marginBottom: "0.7rem" }}>
        <strong className="mono" style={{ fontSize: "0.78rem" }}>
          Eight-gate readiness (snapshot at dispatch):
        </strong>
        <div style={{ marginTop: "0.35rem" }}>
          {gateNames.length === 0 ? (
            <span className="mono" style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}>
              (no eight-gate snapshot recorded)
            </span>
          ) : (
            gateNames.map((g) => (
              <GateBadge key={g} name={g} ok={!!props.eightGateStatus[g]} />
            ))
          )}
        </div>
        {failingGates.length > 0 && (
          <p
            className="mono"
            style={{
              fontSize: "0.72rem",
              color: "var(--warn, #f97316)",
              marginTop: "0.3rem",
            }}
          >
            ACCEPT-AND-BET will fail the eight-gate re-check until these
            gates pass.
          </p>
        )}
      </div>

      <label
        className="mono"
        style={{ display: "block", fontSize: "0.78rem", marginBottom: "0.3rem" }}
      >
        Rationale (required for REJECT, ≥ 20 chars)
      </label>
      <textarea
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
        rows={3}
        style={{
          width: "100%",
          fontFamily: "inherit",
          fontSize: "0.85rem",
          padding: "0.5rem",
          marginBottom: "0.6rem",
        }}
      />

      <label
        className="mono"
        style={{ display: "block", fontSize: "0.78rem", marginBottom: "0.3rem" }}
      >
        Defer until (required for DEFER, ISO timestamp)
      </label>
      <input
        type="datetime-local"
        value={deferUntil}
        onChange={(e) => setDeferUntil(e.target.value)}
        style={{
          fontFamily: "inherit",
          fontSize: "0.85rem",
          padding: "0.35rem",
          marginBottom: "0.8rem",
        }}
      />

      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => handleAction(ACCEPT_AND_BET)}
          disabled={isPending}
          className="mono"
        >
          ACCEPT-AND-BET
        </button>
        <button
          type="button"
          onClick={() => handleAction(ACCEPT_NO_BET)}
          disabled={isPending}
          className="mono"
        >
          ACCEPT-NO-BET
        </button>
        <button
          type="button"
          onClick={() => handleAction(REJECT)}
          disabled={isPending}
          className="mono"
        >
          REJECT
        </button>
        <button
          type="button"
          onClick={() => handleAction(DEFER)}
          disabled={isPending}
          className="mono"
        >
          DEFER
        </button>
      </div>

      {gateFailures.length > 0 && (
        <p
          className="mono"
          style={{
            color: "var(--warn, #f97316)",
            fontSize: "0.78rem",
            marginTop: "0.5rem",
          }}
        >
          Eight-gate re-check failed: {gateFailures.join(", ")}
        </p>
      )}
      {error && (
        <p
          className="mono"
          style={{
            color: "var(--err, #ef4444)",
            fontSize: "0.78rem",
            marginTop: "0.5rem",
          }}
        >
          {error}
        </p>
      )}
    </article>
  );
}
