"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import {
  ATTENTION_QUEUE_LABELS,
  MAX_SNOOZE_DAYS,
  type AttentionQueueId,
  type AttentionSeverity,
} from "@/lib/attention";

export type AttentionItemViewModel = {
  queue: AttentionQueueId;
  itemId: string;
  severity: AttentionSeverity;
  ageMs: number;
  createdAt: string;
  preview: string;
  link: string;
};

const SEVERITY_ACCENT: Record<AttentionSeverity, string> = {
  high: "var(--ember)",
  medium: "var(--amber)",
  low: "var(--parchment-dim)",
};

/**
 * Single row in the unified attention queue. Renders the item's
 * preview + deeplink and exposes Snooze / Dismiss affordances. Both
 * actions POST to /api/founder/attention; on success the row hides
 * itself optimistically (the next dashboard load will reflect the
 * authoritative state).
 *
 * Snooze beyond 14 days is rejected at the API layer (rewritten as a
 * dismissal with reason "deferred indefinitely"). The form here caps
 * the slider to MAX_SNOOZE_DAYS so the founder cannot accidentally
 * trigger that path.
 */
export default function AttentionItem({ item }: { item: AttentionItemViewModel }) {
  const [hidden, setHidden] = useState(false);
  const [mode, setMode] = useState<"idle" | "snooze" | "dismiss">("idle");
  const [snoozeDays, setSnoozeDays] = useState(1);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  if (hidden) return null;

  const accent = SEVERITY_ACCENT[item.severity];
  const queueLabel = ATTENTION_QUEUE_LABELS[item.queue];

  function submit(action: "snooze" | "dismiss") {
    setError(null);
    startTransition(async () => {
      const payload: Record<string, unknown> = {
        queue: item.queue,
        itemId: item.itemId,
        action,
      };
      if (action === "snooze") {
        const until = new Date(Date.now() + snoozeDays * 24 * 60 * 60 * 1000);
        payload.snoozedUntil = until.toISOString();
      }
      if (action === "dismiss") {
        if (!reason.trim()) {
          setError("Reason required");
          return;
        }
        payload.reason = reason.trim();
      }
      try {
        const res = await fetch("/api/founder/attention", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const data = (await res.json().catch(() => ({}))) as { error?: string };
          setError(data.error || `HTTP ${res.status}`);
          return;
        }
        setHidden(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "request_failed");
      }
    });
  }

  return (
    <li
      data-testid="attention-item"
      data-queue={item.queue}
      data-item-id={item.itemId}
      data-severity={item.severity}
      style={{
        listStyle: "none",
        padding: "0.75rem 1rem",
        marginBottom: "0.5rem",
        border: "1px solid var(--gold-dim, rgba(205,151,67,0.25))",
        borderLeft: `3px solid ${accent}`,
        borderRadius: 2,
        background: "rgba(0, 0, 0, 0.18)",
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
              onClick={() => setMode("snooze")}
              disabled={isPending}
            >
              Snooze
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setMode("dismiss")}
              disabled={isPending}
            >
              Dismiss
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
                  setSnoozeDays(Math.max(1, Math.min(MAX_SNOOZE_DAYS, Number(e.target.value) || 1)))
                }
                style={{ width: "4rem", marginLeft: "0.4rem" }}
              />
            </label>
            <button
              type="button"
              className="btn-solid btn"
              onClick={() => submit("snooze")}
              disabled={isPending}
            >
              Confirm snooze
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setMode("idle")}
              disabled={isPending}
            >
              Cancel
            </button>
          </>
        ) : null}

        {mode === "dismiss" ? (
          <>
            <input
              type="text"
              placeholder="Reason for dismissal"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ flex: "1 1 16rem", minWidth: "10rem" }}
            />
            <button
              type="button"
              className="btn-solid btn"
              onClick={() => submit("dismiss")}
              disabled={isPending}
            >
              Confirm dismiss
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

        {error ? (
          <span
            className="mono"
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
