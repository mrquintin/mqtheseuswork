"use client";

import { useState } from "react";

/**
 * Small inline control shown on upload rows whose processing has
 * stalled. Clicks POST /api/trigger-processing, which fires the GitHub
 * Actions dispatch so Noosphere picks the upload back up without
 * waiting for the 10-minute cron sweep.
 *
 * States
 * ------
 *   idle       → "Retry processing" button
 *   loading    → "Triggering…" disabled
 *   success    → "✓ Queued" for 3s, then back to idle
 *   error      → "⚠ " + message, stays visible until the next click
 */

export interface RetryProcessingButtonProps {
  uploadId: string;
  /** Status of the upload; button only renders for "stale" statuses. */
  status: string;
  /** When true, render even if the status looks healthy (e.g. for admin debugging). */
  alwaysShow?: boolean;
}

export default function RetryProcessingButton({
  uploadId,
  status,
  alwaysShow,
}: RetryProcessingButtonProps) {
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">(
    "idle",
  );
  const [message, setMessage] = useState<string>("");

  // The only statuses where a retry makes sense. `processing` means
  // a run is already underway so we suppress the button to avoid
  // confusing the user with concurrent dispatches.
  const stale =
    status === "queued_offline" ||
    status === "pending" ||
    status === "failed";
  if (!alwaysShow && !stale) return null;

  async function handleClick() {
    setState("loading");
    setMessage("");
    try {
      const res = await fetch("/api/trigger-processing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId, with_llm: true }),
      });
      const data = (await res.json()) as {
        dispatched?: boolean;
        note?: string;
        error?: string;
      };
      if (!res.ok) {
        setState("error");
        setMessage(data.error || `HTTP ${res.status}`);
        return;
      }
      if (data.dispatched) {
        setState("success");
        setMessage("Queued");
        setTimeout(() => {
          setState("idle");
          setMessage("");
          // Force-refresh server components so the status badge updates.
          if (typeof window !== "undefined") {
            window.location.reload();
          }
        }, 1800);
      } else {
        setState("error");
        setMessage(data.note || "Dispatch failed");
      }
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  }

  const label =
    state === "loading"
      ? "Triggering…"
      : state === "success"
        ? "✓ Queued"
        : state === "error"
          ? `⚠ ${message.slice(0, 40)}`
          : "Retry processing";

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={state === "loading" || state === "success"}
      className="mono"
      style={{
        background: "transparent",
        color:
          state === "success"
            ? "var(--success, #4ade80)"
            : state === "error"
              ? "var(--ember)"
              : "var(--amber)",
        border: `1px solid ${
          state === "success"
            ? "var(--success, #4ade80)"
            : state === "error"
              ? "var(--ember)"
              : "var(--amber-dim)"
        }`,
        padding: "0.25rem 0.6rem",
        fontSize: "0.62rem",
        letterSpacing: "0.15em",
        textTransform: "uppercase",
        cursor: state === "loading" ? "wait" : "pointer",
        borderRadius: "3px",
        transition: "all 0.2s ease",
      }}
      title={
        state === "error"
          ? message
          : "Manually re-trigger Noosphere processing for this upload"
      }
    >
      {label}
    </button>
  );
}
