"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import {
  ATTENTION_QUEUE_LABELS,
  MAX_SNOOZE_DAYS,
  type AttentionQueueId,
  type AttentionSeverity,
} from "@/lib/attentionShared";
import { DASHBOARD_COPY } from "@/lib/copy/dashboard";

export type AttentionItemViewModel = {
  queue: AttentionQueueId;
  itemId: string;
  severity: AttentionSeverity;
  ageMs: number;
  createdAt: string;
  preview: string;
  link: string;
  /**
   * Whether this item's queue has opted in to the false-positive
   * training loop. Computed server-side; defaults to off so the firm
   * never gets a feedback loop it did not consent to.
   */
  trainingFeedbackEnabled?: boolean;
};

const SEVERITY_ACCENT: Record<AttentionSeverity, string> = {
  high: "var(--ember)",
  medium: "var(--amber)",
  low: "var(--parchment-dim)",
};

// Mirrors DISMISS_REASON_WRONG_CALL in @/lib/attention — kept as a
// local literal so this client component doesn't pull the server-only
// attention module (and its db import) into the browser bundle.
const WRONG_CALL_REASON = "wrong call by the system";

const DISMISS_PRESETS: ReadonlyArray<{ label: string; reason: string }> = [
  { label: "Resolved", reason: "resolved" },
  { label: "Not actionable", reason: "not actionable" },
  { label: "Wrong call by the system", reason: WRONG_CALL_REASON },
];

export function attentionItemKey(item: {
  queue: AttentionQueueId;
  itemId: string;
}): string {
  return `${item.queue}::${item.itemId}`;
}

export type AttentionItemProps = {
  item: AttentionItemViewModel;
  /** Multi-select state, owned by the parent `AttentionQueue`. */
  selected?: boolean;
  onToggleSelected?: (key: string) => void;
  /**
   * Called after the row resolves itself (snooze/dismiss). When
   * provided the parent owns visibility; otherwise the row hides
   * itself locally.
   */
  onResolved?: (key: string) => void;
};

/**
 * Single row in the unified attention queue. Renders the item's
 * preview + deeplink and exposes a select checkbox plus Later / Clear
 * affordances. Both actions POST to /api/founder/attention; on success
 * the row reports up via `onResolved` (and hides itself if the parent
 * isn't tracking visibility).
 *
 * Snooze now requires a reason — it becomes a searchable annotation,
 * not a silent disappearance. Clear offers preset reasons including
 * "wrong call by the system", which (on opted-in queues) feeds the
 * producer's threshold tuning. Requests beyond 14 days are rejected at
 * the API layer; the slider is capped to MAX_SNOOZE_DAYS so the founder
 * cannot accidentally trigger that path.
 */
export default function AttentionItem({
  item,
  selected = false,
  onToggleSelected,
  onResolved,
}: AttentionItemProps) {
  const [hidden, setHidden] = useState(false);
  const [mode, setMode] = useState<"idle" | "snooze" | "dismiss">("idle");
  const [snoozeDays, setSnoozeDays] = useState(1);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  if (hidden) return null;

  const accent = SEVERITY_ACCENT[item.severity];
  const queueLabel = ATTENTION_QUEUE_LABELS[item.queue];
  const itemKey = attentionItemKey(item);

  function submit(action: "snooze" | "dismiss") {
    setError(null);
    const trimmedReason = reason.trim();
    if (action === "snooze" && trimmedReason.length < 3) {
      setError("A reason is required to snooze an item.");
      return;
    }
    if (action === "dismiss" && !trimmedReason) {
      setError("A reason is required to clear an item.");
      return;
    }
    startTransition(async () => {
      const payload: Record<string, unknown> = {
        queue: item.queue,
        itemId: item.itemId,
        action,
        reason: trimmedReason,
      };
      if (action === "snooze") {
        const until = new Date(Date.now() + snoozeDays * 24 * 60 * 60 * 1000);
        payload.snoozedUntil = until.toISOString();
      }
      try {
        const res = await fetch("/api/founder/attention", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const data = (await res.json().catch(() => ({}))) as {
            error?: string | { message?: string };
          };
          const message =
            typeof data.error === "string" ? data.error : data.error?.message;
          setError(message || `HTTP ${res.status}`);
          return;
        }
        onResolved?.(itemKey);
        setHidden(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "request_failed");
      }
    });
  }

  const wrongCallSelected =
    mode === "dismiss" && reason.trim().toLowerCase() === WRONG_CALL_REASON;

  return (
    <li
      data-testid="attention-item"
      data-queue={item.queue}
      data-item-id={item.itemId}
      data-severity={item.severity}
      data-selected={selected ? "true" : "false"}
      style={{
        listStyle: "none",
        padding: "0.75rem 1rem",
        marginBottom: "0.5rem",
        border: "1px solid var(--gold-dim, rgba(205,151,67,0.25))",
        borderLeft: `3px solid ${accent}`,
        borderRadius: 2,
        background: selected ? "rgba(205,151,67,0.08)" : "rgba(0, 0, 0, 0.18)",
        display: "flex",
        flexDirection: "column",
        gap: "0.45rem",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "1rem",
          justifyContent: "space-between",
          alignItems: "baseline",
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: "0.5rem",
          }}
        >
          {onToggleSelected ? (
            <input
              type="checkbox"
              checked={selected}
              aria-label={`Select review item ${item.itemId}`}
              onChange={() => onToggleSelected(itemKey)}
              disabled={isPending}
              style={{ alignSelf: "center" }}
            />
          ) : null}
          <span
            className="mono"
            style={{
              color: accent,
              fontSize: "0.62rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
            }}
          >
            {queueLabel} · {item.severity} · {formatAge(item.ageMs)}
          </span>
        </span>
        <Link href={item.link} style={{ color: "var(--gold)", fontSize: "0.78rem" }}>
          Open →
        </Link>
      </div>
      <p
        style={{
          margin: 0,
          fontSize: "0.88rem",
          color: "var(--parchment)",
          lineHeight: 1.5,
        }}
      >
        {item.preview}
      </p>
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        {mode === "idle" ? (
          <>
            <button
              type="button"
              className="btn"
              aria-label="Hide this review item for now"
              onClick={() => setMode("snooze")}
              disabled={isPending}
            >
              {DASHBOARD_COPY.hideForNow}
            </button>
            <button
              type="button"
              className="btn"
              aria-label="Hide this review item permanently"
              onClick={() => setMode("dismiss")}
              disabled={isPending}
            >
              {DASHBOARD_COPY.hidePermanently}
            </button>
          </>
        ) : null}

        {mode === "snooze" ? (
          <>
            <label
              className="mono"
              style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}
            >
              days
              <input
                type="number"
                min={1}
                max={MAX_SNOOZE_DAYS}
                value={snoozeDays}
                onChange={(e) =>
                  setSnoozeDays(
                    Math.max(
                      1,
                      Math.min(MAX_SNOOZE_DAYS, Number(e.target.value) || 1),
                    ),
                  )
                }
                style={{ width: "4rem", marginLeft: "0.4rem" }}
              />
            </label>
            <input
              type="text"
              aria-label="Reason for hiding for now"
              placeholder="Why hide this for now? (searchable annotation)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ flex: "1 1 14rem", minWidth: "10rem" }}
            />
            <button
              type="button"
              className="btn-solid btn"
              onClick={() => submit("snooze")}
              disabled={isPending || reason.trim().length < 3}
            >
              Hide until then
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setMode("idle");
                setReason("");
              }}
              disabled={isPending}
            >
              Cancel
            </button>
          </>
        ) : null}

        {mode === "dismiss" ? (
          <>
            <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
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
                      ? {
                          borderColor: "var(--amber)",
                          color: "var(--amber)",
                        }
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
              placeholder="Why is this resolved or not useful?"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ flex: "1 1 16rem", minWidth: "10rem" }}
            />
            <button
              type="button"
              className="btn-solid btn"
              onClick={() => submit("dismiss")}
              disabled={isPending || !reason.trim()}
            >
              {DASHBOARD_COPY.hidePermanently}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setMode("idle");
                setReason("");
              }}
              disabled={isPending}
            >
              Cancel
            </button>
            {wrongCallSelected ? (
              <span
                className="mono"
                style={{ color: "var(--parchment-dim)", fontSize: "0.65rem" }}
              >
                {item.trainingFeedbackEnabled
                  ? `Feeds ${queueLabel} threshold tuning.`
                  : `${queueLabel} has not opted in — recorded, not fed back.`}
              </span>
            ) : null}
          </>
        ) : null}

        {error ? (
          <span
            className="mono"
            role="alert"
            style={{ color: "var(--ember)", fontSize: "0.65rem" }}
          >
            {error}
          </span>
        ) : null}
      </div>
    </li>
  );
}

function formatAge(ms: number): string {
  if (ms <= 0) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}
