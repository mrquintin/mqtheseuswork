"use client";

import { useState } from "react";

/**
 * Triage controls for one pending subsumption candidate.
 *
 * ACCEPT → terminal SUBSUMED_BY_SYNTHESIS.
 * REJECT → clears the candidate; lifecycle stays at its current status.
 */
export default function SubsumptionTriage({
  contradictionId,
  candidatePrincipleId,
}: {
  contradictionId: string;
  candidatePrincipleId: string;
}) {
  const [mode, setMode] = useState<"idle" | "reject">("idle");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function accept() {
    setSubmitting(true);
    setError(null);
    const res = await fetch(`/api/contradictions/${contradictionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "accept-subsumption",
        subsumingPrincipleId: candidatePrincipleId,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Accept failed");
      setSubmitting(false);
      return;
    }
    window.location.reload();
  }

  async function reject() {
    setSubmitting(true);
    setError(null);
    const res = await fetch(`/api/contradictions/${contradictionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "reject-subsumption",
        reason: reason || undefined,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Reject failed");
      setSubmitting(false);
      return;
    }
    window.location.reload();
  }

  return (
    <div>
      {mode === "idle" ? (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-solid"
            onClick={accept}
            disabled={submitting}
            style={{ fontSize: "0.7rem" }}
          >
            {submitting ? "Saving…" : "Accept subsumption"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setMode("reject")}
            style={{ fontSize: "0.7rem", color: "var(--parchment-dim)" }}
          >
            Reject candidate
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Optional: why is this not a valid synthesis?"
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
              className="btn btn-solid"
              onClick={reject}
              disabled={submitting}
              style={{ fontSize: "0.7rem" }}
            >
              {submitting ? "Saving…" : "Confirm reject"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setMode("idle");
                setReason("");
                setError(null);
              }}
              disabled={submitting}
              style={{ fontSize: "0.7rem" }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {error ? (
        <p style={{ color: "var(--ember)", fontSize: "0.75rem", margin: "0.4rem 0 0" }}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
