"use client";

import { useMemo, useState } from "react";

/**
 * Live contradiction alerts pane for the Dialectic recording surface
 * (prompt 14).
 *
 * Each flag renders the current speaker's span, the prior position
 * (intra-session or historical), the contradiction score and axis
 * label, and two buttons: ACKNOWLEDGE (logs intent to address) and
 * ADDRESS-NOW (logs a spoken response targeting the flag).
 *
 * The panel is purely presentational — it never mutates the
 * contradiction log itself. All write paths route through the
 * `acknowledge` callback (POST /v1/dialectic/.../acknowledge).
 */

export type ContradictionAlert = {
  id: string;
  utteranceId: string;
  flagKind:
    | "INTRA_SESSION"
    | "HISTORICAL_SELF"
    | "HISTORICAL_OTHER"
    | "HISTORICAL_FIRM";
  currentSpeaker: string;
  currentText: string;
  priorSpeaker: string | null;
  priorWhen: string | null; // human-readable date or "earlier in this session"
  priorText: string;
  contradictionScore: number;
  axis: string | null;
  acknowledgedAt: string | null;
};

type Props = {
  sessionId: string;
  alerts: ContradictionAlert[];
  onAcknowledge: (flagId: string, note: string) => Promise<void> | void;
  onAddressNow?: (flagId: string) => Promise<void> | void;
};

function flagKindLabel(kind: ContradictionAlert["flagKind"]): string {
  switch (kind) {
    case "INTRA_SESSION":
      return "Earlier in this session";
    case "HISTORICAL_SELF":
      return "You said the opposite before";
    case "HISTORICAL_OTHER":
      return "Another speaker said the opposite";
    case "HISTORICAL_FIRM":
      return "Contradicts a firm principle";
    default:
      return kind;
  }
}

function scoreBadgeColor(score: number): string {
  if (score >= 0.85) return "var(--danger, #c0392b)";
  if (score >= 0.7) return "var(--warning, #d35400)";
  return "var(--amber, #b7791f)";
}

export default function LiveContradictionPanel({
  sessionId,
  alerts,
  onAcknowledge,
  onAddressNow,
}: Props) {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [draftNote, setDraftNote] = useState<string>("");

  const sorted = useMemo(
    () =>
      [...alerts].sort((a, b) => {
        // unacknowledged first, then by score desc
        if (!a.acknowledgedAt && b.acknowledgedAt) return -1;
        if (a.acknowledgedAt && !b.acknowledgedAt) return 1;
        return b.contradictionScore - a.contradictionScore;
      }),
    [alerts],
  );

  return (
    <aside
      data-testid="live-contradiction-panel"
      data-session-id={sessionId}
      style={{
        borderLeft: "1px solid var(--rule)",
        paddingLeft: "1rem",
        minWidth: "320px",
        maxWidth: "420px",
        fontSize: "0.92rem",
      }}
    >
      <h2 style={{ marginTop: 0 }}>Contradiction alerts</h2>
      {sorted.length === 0 ? (
        <p style={{ color: "var(--amber-dim)" }}>
          No contradictions flagged yet. The system is listening.
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {sorted.map((alert) => {
            const isOpen = pendingId === alert.id;
            return (
              <li
                key={alert.id}
                data-flag-kind={alert.flagKind}
                style={{
                  marginBottom: "1rem",
                  padding: "0.75rem",
                  border: "1px solid var(--rule)",
                  background: alert.acknowledgedAt
                    ? "transparent"
                    : "rgba(192, 57, 43, 0.08)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                  }}
                >
                  <strong>{flagKindLabel(alert.flagKind)}</strong>
                  <span
                    style={{
                      color: scoreBadgeColor(alert.contradictionScore),
                      fontFamily: "var(--font-mono)",
                    }}
                    data-testid="contradiction-score"
                  >
                    {alert.contradictionScore.toFixed(2)}
                  </span>
                </div>
                {alert.axis ? (
                  <div
                    style={{
                      fontSize: "0.8rem",
                      color: "var(--amber-dim)",
                      marginBottom: "0.4rem",
                    }}
                  >
                    axis: {alert.axis}
                  </div>
                ) : null}
                <p style={{ margin: "0.25rem 0" }}>
                  <em>{alert.currentSpeaker} just said:</em> &ldquo;
                  {alert.currentText}&rdquo;
                </p>
                <p style={{ margin: "0.25rem 0", color: "var(--amber-dim)" }}>
                  <em>
                    But {alert.priorWhen ?? "earlier"}
                    {alert.priorSpeaker
                      ? `, ${alert.priorSpeaker}`
                      : ""}
                    {" "}said:
                  </em>{" "}
                  &ldquo;{alert.priorText}&rdquo;
                </p>
                {alert.acknowledgedAt ? (
                  <small style={{ color: "var(--amber-dim)" }}>
                    Acknowledged {alert.acknowledgedAt}
                  </small>
                ) : (
                  <div style={{ marginTop: "0.5rem" }}>
                    {isOpen ? (
                      <div>
                        <textarea
                          value={draftNote}
                          onChange={(e) => setDraftNote(e.target.value)}
                          placeholder="Note (optional)"
                          rows={2}
                          style={{ width: "100%", marginBottom: "0.4rem" }}
                        />
                        <button
                          type="button"
                          onClick={async () => {
                            await onAcknowledge(alert.id, draftNote);
                            setPendingId(null);
                            setDraftNote("");
                          }}
                        >
                          Save acknowledgment
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button
                          type="button"
                          onClick={() => setPendingId(alert.id)}
                        >
                          Acknowledge
                        </button>
                        {onAddressNow ? (
                          <button
                            type="button"
                            onClick={() => onAddressNow(alert.id)}
                          >
                            Address now
                          </button>
                        ) : null}
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
