"use client";

import { useState } from "react";
import { MAX_SNOOZE_DAYS } from "@/lib/attentionShared";
import { DASHBOARD_COPY } from "@/lib/copy/dashboard";
import { color, fontSize, radius, space, tracking } from "@/lib/design/tokens";

/**
 * Bulk-action affordance for the attention queue. A populated queue is
 * unmaintainable one row at a time, so the founder can multi-select and
 * then bulk-snooze or bulk-dismiss the selection.
 *
 * Both bulk actions require a reason: snooze reasons become searchable
 * annotations, dismiss reasons feed queue tuning. The bar never
 * resolves anything itself — it hands a validated (reason, days) pair
 * back to `AttentionQueue`, which owns the requests. Selecting the
 * "wrong call by the system" dismiss reason on an opted-in queue is
 * what feeds the producer-tuning loop.
 */

// Mirrors DISMISS_REASON_WRONG_CALL in @/lib/attention — kept as a
// local literal so this client component doesn't pull the server-only
// attention module (and its db import) into the browser bundle.
const WRONG_CALL_REASON = "wrong call by the system";

const DISMISS_PRESETS: ReadonlyArray<{ label: string; reason: string }> = [
  { label: "Resolved", reason: "resolved" },
  { label: "Not actionable", reason: "not actionable" },
  { label: "Wrong call by the system", reason: WRONG_CALL_REASON },
];

export type BulkActionBarProps = {
  selectedCount: number;
  isPending: boolean;
  error: string | null;
  onClearSelection: () => void;
  onBulkSnooze: (reason: string, days: number) => void;
  onBulkDismiss: (reason: string) => void;
};

const labelStyle = {
  color: color.parchmentDim,
  fontSize: fontSize.caption,
} as const;

export default function BulkActionBar({
  selectedCount,
  isPending,
  error,
  onClearSelection,
  onBulkSnooze,
  onBulkDismiss,
}: BulkActionBarProps) {
  const [mode, setMode] = useState<"idle" | "snooze" | "dismiss">("idle");
  const [reason, setReason] = useState("");
  const [snoozeDays, setSnoozeDays] = useState(1);

  function reset() {
    setMode("idle");
    setReason("");
    setSnoozeDays(1);
  }

  const reasonReady = reason.trim().length >= 3;

  return (
    <div
      data-testid="bulk-action-bar"
      role="region"
      aria-label="Bulk actions"
      style={{
        alignItems: "center",
        background: "color-mix(in srgb, var(--amber) 6%, transparent)",
        border: `1px solid ${color.amberDim}`,
        borderRadius: radius.rounded,
        display: "flex",
        flexWrap: "wrap",
        gap: space.sm,
        marginBottom: space.lg,
        padding: `${space.sm} ${space.md}`,
      }}
    >
      <span
        className="mono"
        style={{
          color: color.amber,
          fontSize: fontSize.caption,
          letterSpacing: tracking.widest,
          textTransform: "uppercase",
        }}
      >
        {selectedCount} selected
      </span>

      {mode === "idle" ? (
        <>
          <button
            type="button"
            className="btn"
            onClick={() => setMode("snooze")}
            disabled={isPending}
          >
            {DASHBOARD_COPY.hideForNow}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setMode("dismiss")}
            disabled={isPending}
          >
            {DASHBOARD_COPY.hidePermanently}
          </button>
          <button
            type="button"
            className="btn btn--quiet"
            onClick={onClearSelection}
            disabled={isPending}
          >
            Clear selection
          </button>
        </>
      ) : null}

      {mode === "snooze" ? (
        <>
          <label className="mono" style={labelStyle}>
            days
            <input
              type="number"
              min={1}
              max={MAX_SNOOZE_DAYS}
              value={snoozeDays}
              onChange={(event) =>
                setSnoozeDays(
                  Math.max(
                    1,
                    Math.min(MAX_SNOOZE_DAYS, Number(event.target.value) || 1),
                  ),
                )
              }
              style={{ width: "4rem", marginLeft: space.sm }}
            />
          </label>
          <input
            type="text"
            aria-label="Reason for hiding for now"
            placeholder="Why hide these for now? (searchable annotation)"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            style={{ flex: "1 1 18rem", minWidth: "12rem" }}
          />
          <button
            type="button"
            className="btn-solid btn"
            onClick={() => onBulkSnooze(reason.trim(), snoozeDays)}
            disabled={isPending || !reasonReady}
          >
            {DASHBOARD_COPY.hideForNow} ({selectedCount})
          </button>
          <button
            type="button"
            className="btn"
            onClick={reset}
            disabled={isPending}
          >
            Cancel
          </button>
        </>
      ) : null}

      {mode === "dismiss" ? (
        <>
          <div style={{ display: "flex", gap: space.xs, flexWrap: "wrap" }}>
            {DISMISS_PRESETS.map((preset) => (
              <button
                key={preset.reason}
                type="button"
                className="btn btn--quiet"
                aria-pressed={reason === preset.reason}
                onClick={() => setReason(preset.reason)}
                disabled={isPending}
                style={
                  reason === preset.reason
                    ? { borderColor: color.amber, color: color.amber }
                    : undefined
                }
              >
                {preset.label}
              </button>
            ))}
          </div>
          <input
            type="text"
            aria-label="Reason for hiding permanently"
            placeholder="Why are these resolved or not useful?"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            style={{ flex: "1 1 18rem", minWidth: "12rem" }}
          />
          <button
            type="button"
            className="btn-solid btn"
            onClick={() => onBulkDismiss(reason.trim())}
            disabled={isPending || !reason.trim()}
          >
            {DASHBOARD_COPY.hidePermanently} ({selectedCount})
          </button>
          <button
            type="button"
            className="btn"
            onClick={reset}
            disabled={isPending}
          >
            Cancel
          </button>
          {reason.trim().toLowerCase() === WRONG_CALL_REASON ? (
            <span
              className="mono"
              style={{ color: color.parchmentDim, fontSize: fontSize.caption }}
            >
              Feeds producer threshold tuning on opted-in queues.
            </span>
          ) : null}
        </>
      ) : null}

      {error ? (
        <span
          className="mono"
          role="alert"
          style={{ color: color.ember, fontSize: fontSize.caption }}
        >
          {error}
        </span>
      ) : null}
    </div>
  );
}
