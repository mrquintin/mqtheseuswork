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

/**
 * Coherence review queue rows. Previous version rendered a small animated
 * balance-scale per row; removed in favour of a compact textual verdict-
 * tally. The Dying Gladiator sculpture at the top of the page carries the
 * visual weight; individual rows stay typographic so a long queue scans
 * cleanly.
 */

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

export default function ReviewQueue({
  items,
  claimTexts,
}: {
  items: Row[];
  claimTexts: Record<string, string>;
}) {
  const [msg, setMsg] = useState("");
  const [warn, setWarn] = useState("");
  // Per-item resolution note the founder can type before pressing a
  // verdict button. Keyed by review-item id so typing in one row doesn't
  // bleed into another.
  const [notes, setNotes] = useState<Record<string, string>>({});
  // Optimistic-resolution state: IDs already resolved in this session
  // get filtered from the visible list, and the most recent verdict
  // surfaces as a brief toast. Replaces a full `window.location.reload()`
  // which destroyed scroll position and ephemeral client state.
  const [resolved, setResolved] = useState<Set<string>>(new Set());
  const [lastAction, setLastAction] = useState<{ id: string; verdict: string } | null>(null);
  // Batch mode state — toggleable checkbox-based selection + bulk
  // verdict buttons.
  const [batchMode, setBatchMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  async function resolve(
    id: string,
    verdict: "cohere" | "contradict" | "unresolved",
    overrule: boolean,
  ) {
    setMsg("");
    const userNote = notes[id]?.trim();
    const defaultNote = overrule ? "Founder overrule via portal" : "Founder confirm";
    const res = await fetch(`/api/review/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        verdict,
        overrule,
        note: userNote || defaultNote,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      setMsg(data.error || "Request failed");
      return;
    }
    if (data.syncFailed || data.warning) {
      setWarn(
        `Resolved, but Noosphere sync failed: ${data.warning || data.detail || "unknown error"}. The verdict is saved locally and can be retried.`,
      );
    } else {
      setWarn("");
    }
    setResolved((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    setLastAction({ id, verdict });
    // Auto-clear the toast after 3s, but only if the same action is
    // still current — otherwise a second verdict clobbered it and its
    // own timer will handle the clearing.
    setTimeout(() => {
      setLastAction((curr) => (curr?.id === id && curr.verdict === verdict ? null : curr));
    }, 3000);
  }

  async function batchResolve(
    verdict: "cohere" | "contradict" | "unresolved",
    overrule: boolean,
  ) {
    setMsg("");
    setWarn("");
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    const res = await fetch("/api/review/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ids,
        verdict,
        overrule,
        note: `Batch ${overrule ? "overrule" : "confirm"} via portal`,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      setMsg(data.error || "Batch resolution failed");
      return;
    }
    if (data.syncFailures && data.syncFailures > 0) {
      setWarn(
        `Resolved ${data.count} items; ${data.syncFailures} Noosphere syncs failed. Failures are logged in audit events and can be retried.`,
      );
    }
    setResolved((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.add(id);
      return next;
    });
    setSelected(new Set());
    setLastAction({ id: "batch", verdict });
    setTimeout(() => {
      setLastAction((curr) => (curr?.id === "batch" && curr.verdict === verdict ? null : curr));
    }, 3000);
  }

  const visible = items.filter((it) => !resolved.has(it.id));

  if (!visible.length) {
    return (
      <>
        {lastAction && (
          <div
            style={{
              padding: "0.5rem 1rem",
              borderLeft: "3px solid var(--gold)",
              fontSize: "0.8rem",
              color: "var(--gold)",
              marginBottom: "0.75rem",
            }}
          >
            Resolved as {lastAction.verdict}
          </div>
        )}
        {resolved.size > 0 && (
          <p style={{ fontSize: "0.7rem", color: "var(--parchment-dim)", marginBottom: "0.75rem" }}>
            {resolved.size} item{resolved.size > 1 ? "s" : ""} resolved this session
          </p>
        )}
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
      </>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn"
          style={{ fontSize: "0.65rem" }}
          onClick={() => {
            setBatchMode(!batchMode);
            setSelected(new Set());
          }}
        >
          {batchMode ? "Exit batch mode" : "Batch mode"}
        </button>
        {batchMode && (
          <span style={{ fontSize: "0.7rem", color: "var(--parchment-dim)" }}>
            {selected.size} selected
          </span>
        )}
      </div>

      {batchMode && (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn"
            style={{ fontSize: "0.6rem" }}
            onClick={() => setSelected(new Set(visible.map((i) => i.id)))}
          >
            Select all
          </button>
          <button
            type="button"
            className="btn"
            style={{ fontSize: "0.6rem" }}
            onClick={() => setSelected(new Set())}
          >
            Select none
          </button>
          {selected.size > 0 && (
            <>
              <button
                type="button"
                className="btn"
                style={{ fontSize: "0.6rem" }}
                onClick={() => batchResolve("cohere", false)}
              >
                Confirm all as cohere
              </button>
              <button
                type="button"
                className="btn"
                style={{ fontSize: "0.6rem" }}
                onClick={() => batchResolve("contradict", false)}
              >
                Confirm all as contradict
              </button>
              <button
                type="button"
                className="btn-solid btn"
                style={{ fontSize: "0.6rem" }}
                onClick={() => batchResolve("cohere", true)}
              >
                Overrule all → cohere
              </button>
            </>
          )}
        </div>
      )}

      {msg && <p style={{ color: "var(--ember)" }}>{msg}</p>}
      {warn && (
        <p
          style={{
            color: "var(--amber)",
            fontSize: "0.8rem",
            padding: "0.5rem 1rem",
            border: "1px solid var(--amber-dim)",
            borderRadius: 2,
            margin: 0,
          }}
        >
          {warn}
        </p>
      )}
      {lastAction && (
        <div
          style={{
            padding: "0.5rem 1rem",
            borderLeft: "3px solid var(--gold)",
            fontSize: "0.8rem",
            color: "var(--gold)",
          }}
        >
          Resolved as {lastAction.verdict}
        </div>
      )}
      {resolved.size > 0 && (
        <p style={{ fontSize: "0.7rem", color: "var(--parchment-dim)", margin: 0 }}>
          {resolved.size} item{resolved.size > 1 ? "s" : ""} resolved this session
        </p>
      )}
      {visible.map((it) => {
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

        // Dominant side for a one-glance verdict summary. Ties or
        // `unresolved`-dominated rows render as "split".
        let dominant: "cohere" | "contradict" | "split" = "split";
        if (tally.contradict > tally.cohere) dominant = "contradict";
        else if (tally.cohere > tally.contradict) dominant = "cohere";

        const claimAText = claimTexts[it.claimAId];
        const claimBText = claimTexts[it.claimBId];

        return (
          <div key={it.id} className="portal-card" style={{ padding: "1.25rem" }}>
            <div
              className="mono"
              style={{
                fontSize: "0.62rem",
                color: "var(--amber-dim)",
                textTransform: "uppercase",
                letterSpacing: "0.12em",
                marginBottom: "0.5rem",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              {batchMode && (
                <input
                  type="checkbox"
                  checked={selected.has(it.id)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(it.id);
                    else next.delete(it.id);
                    setSelected(next);
                  }}
                  style={{ marginRight: "0.35rem" }}
                />
              )}
              <span>
                severity {(it.severity * 100).toFixed(0)}% · aggregator{" "}
                {it.aggregatorVerdict || "—"} · leaning {dominant}
              </span>
            </div>

            <ClaimBlock label="A" id={it.claimAId} text={claimAText} />
            <ClaimBlock label="B" id={it.claimBId} text={claimBText} />

            <p
              style={{
                margin: "0.9rem 0 0",
                color: "var(--parchment)",
                fontFamily: "'EB Garamond', serif",
                fontSize: "1rem",
                lineHeight: 1.6,
              }}
            >
              {it.reason}
            </p>

            {/* Textual verdict tally — replaces the per-row animated
                balance. Highlights contradict in ember, cohere in amber,
                unresolved in parchment-dim so the spread is readable at
                a glance without additional visual chrome. */}
            <div
              className="mono"
              style={{
                display: "flex",
                gap: "1.1rem",
                flexWrap: "wrap",
                fontSize: "0.72rem",
                marginTop: "0.55rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              <span style={{ color: "var(--ember)" }}>
                ✕ {tally.contradict} contradict
              </span>
              <span style={{ color: "var(--amber)" }}>∙ {tally.cohere} cohere</span>
              {tally.unresolved > 0 && (
                <span style={{ color: "var(--parchment-dim)" }}>
                  ? {tally.unresolved} unresolved
                </span>
              )}
              <span style={{ color: "var(--parchment-dim)", marginLeft: "auto" }}>
                pair {it.claimAId.slice(0, 8)}… / {it.claimBId.slice(0, 8)}…
              </span>
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

            <textarea
              placeholder="Resolution notes (optional) — explain your reasoning"
              value={notes[it.id] || ""}
              onChange={(e) =>
                setNotes((prev) => ({ ...prev, [it.id]: e.target.value }))
              }
              rows={2}
              style={{
                width: "100%",
                marginTop: "0.75rem",
                padding: "0.5rem 0.75rem",
                fontSize: "0.8rem",
                fontFamily: "inherit",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--parchment)",
                borderRadius: 2,
                resize: "vertical",
              }}
            />

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

function ClaimBlock({
  label,
  id,
  text,
}: {
  label: "A" | "B";
  id: string;
  text: string | undefined;
}) {
  return (
    <div
      style={{
        marginTop: "0.6rem",
        padding: "0.6rem 0.85rem",
        borderLeft: "2px solid var(--gold-dim)",
        background: "var(--stone-light)",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: "var(--gold-dim)",
          marginBottom: "0.3rem",
        }}
      >
        Claim {label} · {id.slice(0, 8)}…
      </div>
      {text ? (
        <p
          style={{
            margin: 0,
            fontFamily: "'EB Garamond', serif",
            fontSize: "0.95rem",
            color: "var(--parchment)",
            lineHeight: 1.5,
          }}
        >
          {text}
        </p>
      ) : (
        <p
          style={{
            margin: 0,
            fontSize: "0.75rem",
            color: "var(--parchment-dim)",
            fontStyle: "italic",
          }}
        >
          Claim text unavailable — may require Noosphere connection.
        </p>
      )}
    </div>
  );
}
