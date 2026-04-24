"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

/**
 * Retry control shown next to failed uploads in the dashboard detail
 * row. POSTs /api/upload/:id/retry, which resets the row to `pending`
 * and clears `errorMessage`/`extractionMethod`. On success we
 * optimistically show "queued…" and then router.refresh() so the
 * server-rendered badge re-reads the new status from the DB.
 *
 * Deliberately NOT a retry dispatcher — this endpoint only flips the
 * row back into the queue. The existing noosphere runner (local or
 * GitHub Actions) picks it up on its next cycle. That keeps retry idempotent
 * and avoids the double-write races that caused Wave-0 Conclusion dupes.
 */
export default function UploadRetryButton({
  uploadId,
}: {
  uploadId: string;
}) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "sending" | "queued" | "error">(
    "idle",
  );
  const [message, setMessage] = useState("");
  const [, startTransition] = useTransition();

  async function handleClick() {
    setState("sending");
    setMessage("");
    try {
      const res = await fetch(`/api/upload/${uploadId}/retry`, {
        method: "POST",
      });
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
        currentStatus?: string;
      };
      if (!res.ok || !data.ok) {
        setState("error");
        setMessage(
          data.error
            ? `${data.error}${data.currentStatus ? ` (${data.currentStatus})` : ""}`
            : `HTTP ${res.status}`,
        );
        return;
      }
      setState("queued");
      startTransition(() => {
        router.refresh();
      });
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  }

  const label =
    state === "sending"
      ? "sending…"
      : state === "queued"
        ? "✓ queued"
        : state === "error"
          ? `⚠ ${message.slice(0, 60)}`
          : "Retry";

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={state === "sending" || state === "queued"}
      className="mono"
      style={{
        marginTop: "0.5rem",
        background: "transparent",
        color: state === "error" ? "var(--ember)" : "var(--amber)",
        border: `1px solid ${state === "error" ? "var(--ember)" : "var(--amber-dim)"}`,
        padding: "0.25rem 0.7rem",
        fontSize: "0.6rem",
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        cursor: state === "sending" ? "wait" : "pointer",
        borderRadius: "2px",
      }}
      title={
        state === "error"
          ? message
          : "Reset this upload to pending so noosphere picks it up on its next cycle."
      }
    >
      {label}
    </button>
  );
}
