"use client";

import { useEffect, useState } from "react";

import type { MatchedFailureMode } from "@/lib/failureModes";

const SEVERITY_COLOR: Record<string, string> = {
  high: "var(--ember)",
  medium: "var(--amber)",
  low: "var(--parchment-dim)",
};

function ackKey(conclusionId: string, method: string, mode: string): string {
  return `failureMode:ack:${conclusionId}:${method}:${mode}`;
}

/**
 * Founder workspace card for matched failure modes. Each entry
 * exposes a "Was this mode considered?" affirmation. High-severity
 * matched modes must be acknowledged before publish; the gate state
 * is signalled to the rest of the page through a hidden DOM marker
 * (`data-failure-modes-gate`) that the publish flow reads.
 *
 * Acknowledgement is currently kept in localStorage so a reviewer's
 * review state persists across sessions on a single workstation.
 * Durable per-tenant persistence is a follow-up; the contract on the
 * gate marker stays the same when that lands.
 */
export default function FailureModesCard({
  conclusionId,
  matched,
}: {
  conclusionId: string;
  matched: MatchedFailureMode[];
}) {
  const [acks, setAcks] = useState<Record<string, boolean>>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const next: Record<string, boolean> = {};
    for (const mode of matched) {
      const key = ackKey(conclusionId, mode.method, mode.name);
      try {
        next[key] = window.localStorage.getItem(key) === "1";
      } catch {
        next[key] = false;
      }
    }
    setAcks(next);
    setHydrated(true);
  }, [conclusionId, matched]);

  if (matched.length === 0) {
    return (
      <section
        className="portal-card"
        style={{
          padding: "0.85rem 1.1rem",
          marginBottom: "1.5rem",
        }}
      >
        <h2
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.62rem",
            letterSpacing: "0.22em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          Failure modes
        </h2>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.78rem",
            margin: "0.3rem 0 0",
          }}
        >
          No matched failure modes for the methods this conclusion was
          produced under. Catalogs grow over time — re-check after the
          next catalog edit.
        </p>
      </section>
    );
  }

  const highSeverity = matched.filter((m) => m.severity === "high");
  const unackedHigh = highSeverity.filter(
    (m) => !acks[ackKey(conclusionId, m.method, m.name)],
  );
  const gateOk = unackedHigh.length === 0;

  function setAck(method: string, mode: string, value: boolean) {
    const key = ackKey(conclusionId, method, mode);
    setAcks((prev) => ({ ...prev, [key]: value }));
    if (typeof window !== "undefined") {
      try {
        if (value) window.localStorage.setItem(key, "1");
        else window.localStorage.removeItem(key);
      } catch {
        // localStorage unavailable (private mode etc.) — ack is in-
        // memory only; the page will require re-acknowledging next
        // load, which is the safer default.
      }
    }
  }

  return (
    <section
      className="portal-card"
      aria-labelledby="failure-modes-title"
      data-failure-modes-gate={hydrated && gateOk ? "ok" : "blocked"}
      style={{
        padding: "1rem 1.25rem",
        marginBottom: "1.5rem",
        borderLeft: gateOk
          ? "3px solid var(--gold-dim)"
          : "3px solid var(--ember)",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2
            className="mono"
            id="failure-modes-title"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.62rem",
              letterSpacing: "0.22em",
              margin: 0,
              textTransform: "uppercase",
            }}
          >
            Failure modes ({matched.length} matched)
          </h2>
          <p
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.78rem",
              margin: "0.35rem 0 0",
            }}
          >
            Curated failure modes whose trigger conditions plausibly apply
            here. Acknowledging a mode is not the same as accepting it —
            it means: <em>I saw it and have a response</em>.
          </p>
        </div>
        {!gateOk && hydrated ? (
          <span
            className="mono"
            style={{
              alignSelf: "flex-start",
              padding: "0.3rem 0.5rem",
              border: "1px solid var(--ember)",
              color: "var(--ember)",
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            Publish blocked · {unackedHigh.length} high-severity unacked
          </span>
        ) : null}
      </header>

      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: "0.85rem 0 0",
          display: "grid",
          gap: "0.6rem",
        }}
      >
        {matched.map((mode) => {
          const key = ackKey(conclusionId, mode.method, mode.name);
          const acked = Boolean(acks[key]);
          return (
            <li
              key={key}
              style={{
                padding: "0.65rem 0.75rem",
                border: "1px solid var(--border)",
                borderLeft: `3px solid ${SEVERITY_COLOR[mode.severity] ?? "var(--border)"}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "0.5rem",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <span
                    className="mono"
                    style={{
                      color: SEVERITY_COLOR[mode.severity] ?? "var(--parchment)",
                      fontSize: "0.58rem",
                      letterSpacing: "0.2em",
                      textTransform: "uppercase",
                      marginRight: "0.5rem",
                    }}
                  >
                    {mode.severity}
                  </span>
                  <span
                    style={{
                      color: "var(--parchment)",
                      fontSize: "0.85rem",
                      fontWeight: 600,
                    }}
                  >
                    {mode.name}
                  </span>
                  <span
                    className="mono"
                    style={{
                      color: "var(--parchment-dim)",
                      fontSize: "0.6rem",
                      marginLeft: "0.5rem",
                    }}
                  >
                    · {mode.method}
                  </span>
                </div>
                <label
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    fontSize: "0.72rem",
                    color: acked ? "var(--gold)" : "var(--parchment-dim)",
                    cursor: "pointer",
                  }}
                >
                  <input
                    aria-label={`Acknowledge ${mode.name}`}
                    checked={acked}
                    onChange={(e) =>
                      setAck(mode.method, mode.name, e.target.checked)
                    }
                    type="checkbox"
                  />
                  Was this mode considered?
                </label>
              </div>

              <p
                style={{
                  margin: "0.45rem 0 0",
                  fontSize: "0.82rem",
                  color: "var(--parchment)",
                  lineHeight: 1.5,
                }}
              >
                {mode.description}
              </p>

              <details style={{ marginTop: "0.45rem" }}>
                <summary
                  className="mono"
                  style={{
                    cursor: "pointer",
                    color: "var(--parchment-dim)",
                    fontSize: "0.58rem",
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                  }}
                >
                  Trigger · worked example · mitigation
                </summary>
                <dl
                  style={{
                    margin: "0.4rem 0 0",
                    display: "grid",
                    gridTemplateColumns: "max-content 1fr",
                    columnGap: "0.6rem",
                    rowGap: "0.3rem",
                    fontSize: "0.78rem",
                    color: "var(--parchment)",
                  }}
                >
                  <dt
                    className="mono"
                    style={{ color: "var(--amber-dim)", fontSize: "0.58rem", letterSpacing: "0.16em", textTransform: "uppercase" }}
                  >
                    Trigger
                  </dt>
                  <dd style={{ margin: 0 }}>{mode.trigger_conditions}</dd>
                  <dt
                    className="mono"
                    style={{ color: "var(--amber-dim)", fontSize: "0.58rem", letterSpacing: "0.16em", textTransform: "uppercase" }}
                  >
                    Example
                  </dt>
                  <dd style={{ margin: 0 }}>{mode.worked_example}</dd>
                  <dt
                    className="mono"
                    style={{ color: "var(--amber-dim)", fontSize: "0.58rem", letterSpacing: "0.16em", textTransform: "uppercase" }}
                  >
                    Mitigation
                  </dt>
                  <dd style={{ margin: 0 }}>{mode.mitigation}</dd>
                </dl>
              </details>

              <p
                className="mono"
                style={{
                  margin: "0.45rem 0 0",
                  color: "var(--parchment-dim)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.05em",
                }}
              >
                match score {mode.matchScore.toFixed(2)}
                {mode.public ? " · public" : " · private"}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
