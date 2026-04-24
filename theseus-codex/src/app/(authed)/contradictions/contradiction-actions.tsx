"use client";

import { useState } from "react";

/**
 * Resolve / dismiss controls for a single Contradiction.
 *
 * When the row's status is anything other than "active" we render a
 * read-only status badge — the contradiction is already in the
 * resolved/dismissed bucket and the action UI would be redundant.
 */
export default function ContradictionActions({
  contradictionId,
  status,
}: {
  contradictionId: string;
  status: string;
}) {
  const [mode, setMode] = useState<"idle" | "resolve" | "dismiss">("idle");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status !== "active") {
    return (
      <span
        className="mono"
        style={{
          fontSize: "0.6rem",
          color: status === "resolved" ? "var(--gold)" : "var(--parchment-dim)",
          textTransform: "uppercase",
          letterSpacing: "0.1em",
        }}
      >
        {status}
      </span>
    );
  }

  async function submit() {
    if (mode === "idle") return;
    setSubmitting(true);
    setError(null);
    const res = await fetch(`/api/contradictions/${contradictionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: mode, resolution: note || undefined }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Request failed");
      setSubmitting(false);
      return;
    }
    window.location.reload();
  }

  return (
    <div style={{ marginTop: "0.75rem" }}>
      {mode === "idle" ? (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            type="button"
            className="btn"
            onClick={() => setMode("resolve")}
            style={{ fontSize: "0.65rem" }}
          >
            Resolve
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setMode("dismiss")}
            style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}
          >
            Dismiss as false positive
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={
              mode === "resolve"
                ? "How was this contradiction resolved?"
                : "Optional: why is this a false positive?"
            }
            rows={2}
            style={{
              width: "100%",
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
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className="btn-solid btn"
              onClick={submit}
              disabled={submitting}
              style={{ fontSize: "0.65rem" }}
            >
              {submitting ? "Saving…" : `Confirm ${mode}`}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setMode("idle");
                setNote("");
                setError(null);
              }}
              disabled={submitting}
              style={{ fontSize: "0.65rem" }}
            >
              Cancel
            </button>
          </div>
          {error && (
            <p style={{ color: "var(--ember)", fontSize: "0.75rem", margin: 0 }}>{error}</p>
          )}
        </div>
      )}
    </div>
  );
}
