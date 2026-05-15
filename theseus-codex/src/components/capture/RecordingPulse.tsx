"use client";

import { CSSProperties } from "react";

/**
 * The pulsing red dot the founder sees while a quick-capture is
 * actively recording. The animation is plain inline CSS keyframes so
 * we don't rely on the global stylesheet shipping a `@keyframes`
 * helper for this one widget. The component is intentionally
 * presentation-only — state lives in QuickRecorder.
 */
export interface RecordingPulseProps {
  /** "recording" pulses, "paused" stays solid amber, otherwise hidden. */
  state: "recording" | "paused" | "idle";
  /** Elapsed milliseconds, used for the inline timer label. */
  elapsedMs: number;
  /**
   * If true, render the pulse a touch bigger so it's still unmissable
   * when the QuickRecorder is collapsed to its button-sized state.
   */
  compact?: boolean;
}

function formatTimer(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export default function RecordingPulse({
  state,
  elapsedMs,
  compact = false,
}: RecordingPulseProps) {
  if (state === "idle") return null;
  const colour = state === "recording" ? "#d62828" : "#c89034";
  const dotSize = compact ? 8 : 10;
  const dotStyle: CSSProperties = {
    width: dotSize,
    height: dotSize,
    borderRadius: "50%",
    background: colour,
    boxShadow: `0 0 0 0 ${colour}66`,
    animation:
      state === "recording"
        ? "quickRecorderPulse 1.2s ease-out infinite"
        : "none",
  };
  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={
        state === "recording"
          ? `Recording — ${formatTimer(elapsedMs)} elapsed`
          : `Recording paused at ${formatTimer(elapsedMs)}`
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.4rem",
        fontVariantNumeric: "tabular-nums",
        fontSize: compact ? "0.78rem" : "0.85rem",
        color: state === "recording" ? "#d62828" : "#8a6116",
      }}
    >
      <span style={dotStyle} aria-hidden="true" />
      <span>{formatTimer(elapsedMs)}</span>
      <style>{`
        @keyframes quickRecorderPulse {
          0%   { box-shadow: 0 0 0 0 ${colour}66; }
          70%  { box-shadow: 0 0 0 10px ${colour}00; }
          100% { box-shadow: 0 0 0 0 ${colour}00; }
        }
      `}</style>
    </span>
  );
}
