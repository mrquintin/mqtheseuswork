"use client";

import { useState } from "react";

/**
 * ACKNOWLEDGE / DISPUTE controls for contradictions produced by the
 * canonical ContradictionEngine (Round 19 prompt 06).
 *
 * - ACKNOWLEDGE: the contradiction is real. It stands until new sources
 *   resolve it (prompt 08 covers source-driven resolution).
 * - DISPUTE: the engine got it wrong. The dispute is logged and the
 *   result is downgraded. Multiple disputes on the same detection
 *   method version trigger a calibration review on the methodology
 *   surface.
 *
 * Distinct from the existing Resolve / Dismiss controls, which are
 * preserved for legacy heuristic rows until prompt 16.
 */
export default function EngineActions({
  contradictionId,
  status,
}: {
  contradictionId: string;
  status: string;
}) {
  const [mode, setMode] = useState<"idle" | "dispute">("idle");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "acknowledged" || status === "disputed") {
    return (
      <span
        className="mono"
        style={{
          fontSize: "0.6rem",
          color:
            status === "acknowledged"
              ? "var(--amber)"
              : "var(--parchment-dim)",
          textTransform: "uppercase",
          letterSpacing: "0.1em",
        }}
      >
        {status}
      </span>
    );
  }

  if (status !== "active") return null;

  async function acknowledge() {
    setSubmitting(true);
    setError(null);
    const res = await fetch(`/api/contradictions/${contradictionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "acknowledge" }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Acknowledge failed");
      setSubmitting(false);
      return;
    }
    window.location.reload();
  }

  async function submitDispute() {
    if (!reason.trim()) {
      setError("Dispute reason is required");
      return;
    }
    setSubmitting(true);
    setError(null);
    const res = await fetch(`/api/contradictions/${contradictionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "dispute", reason }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Dispute failed");
      setSubmitting(false);
      return;
    }
    window.location.reload();
  }

  return (
    <div style={{ marginTop: "0.75rem" }}>
      {mode === "idle" ? (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-solid"
            onClick={acknowledge}
            disabled={submitting}
            style={{ fontSize: "0.65rem" }}
          >
            {submitting ? "Saving…" : "Acknowledge"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setMode("dispute")}
            style={{ fontSize: "0.65rem", color: "var(--ember)" }}
          >
            Dispute
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why did the engine get this wrong? (required — feeds calibration review)"
            rows={3}
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
              onClick={submitDispute}
              disabled={submitting}
              style={{ fontSize: "0.65rem" }}
            >
              {submitting ? "Submitting…" : "Submit dispute"}
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
              style={{ fontSize: "0.65rem" }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && (
        <p
          style={{
            color: "var(--ember)",
            fontSize: "0.75rem",
            margin: "0.4rem 0 0",
          }}
        >
          {error}
        </p>
      )}
    </div>
  );
}
