"use client";

import { useEffect, useRef } from "react";

/**
 * Rolling transcript view shown during a live recording (prompt 14).
 *
 * Each utterance is rendered with speaker attribution + timing.
 * Utterances that fired a contradiction flag are visually marked so
 * the speaker on stage sees the alert without needing to look at the
 * side panel. The transcript auto-scrolls but yields to the user the
 * moment they manually scroll up.
 */

export type StreamUtterance = {
  id: string;
  speakerId: string;
  speakerName: string;
  startTime: number;
  endTime: number;
  text: string;
  derivedPrincipleIds: string[];
  flagIds: string[];
  isProvisional?: boolean;
};

type Props = {
  utterances: StreamUtterance[];
  activeSpeakerId?: string | null;
};

function formatTime(seconds: number): string {
  const sec = Math.max(0, Math.floor(seconds));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function UtteranceStream({
  utterances,
  activeSpeakerId,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [utterances.length]);

  return (
    <div
      ref={ref}
      data-testid="utterance-stream"
      onScroll={(e) => {
        const el = e.currentTarget;
        const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
        stickToBottomRef.current = dist < 32;
      }}
      style={{
        height: "60vh",
        overflowY: "auto",
        border: "1px solid var(--rule)",
        padding: "0.75rem",
        fontSize: "0.95rem",
      }}
    >
      {utterances.length === 0 ? (
        <p style={{ color: "var(--amber-dim)" }}>
          Listening for the first utterance…
        </p>
      ) : (
        utterances.map((u) => {
          const active = activeSpeakerId === u.speakerId;
          const flagged = u.flagIds.length > 0;
          return (
            <div
              key={u.id}
              data-utterance-id={u.id}
              data-flagged={flagged ? "true" : "false"}
              style={{
                marginBottom: "0.6rem",
                padding: "0.4rem",
                borderLeft: flagged
                  ? "3px solid var(--danger, #c0392b)"
                  : "3px solid transparent",
                background: active ? "rgba(183, 121, 31, 0.05)" : "transparent",
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: "0.6rem",
                  alignItems: "baseline",
                  marginBottom: "0.25rem",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.8rem",
                  color: "var(--amber-dim)",
                }}
              >
                <span>{u.speakerName}</span>
                <span>
                  {formatTime(u.startTime)} – {formatTime(u.endTime)}
                </span>
                {u.derivedPrincipleIds.length > 0 ? (
                  <span
                    title="Provisional principles will surface in triage after the session ends."
                    style={{
                      color: "var(--warning, #d35400)",
                    }}
                  >
                    PROVISIONAL · {u.derivedPrincipleIds.length} principle
                    {u.derivedPrincipleIds.length === 1 ? "" : "s"}
                  </span>
                ) : null}
                {flagged ? (
                  <span style={{ color: "var(--danger, #c0392b)" }}>
                    ⚠ contradiction
                  </span>
                ) : null}
              </div>
              <p style={{ margin: 0 }}>{u.text}</p>
            </div>
          );
        })
      )}
    </div>
  );
}
