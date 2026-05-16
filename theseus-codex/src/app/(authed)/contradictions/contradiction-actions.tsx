"use client";

import Link from "next/link";

/**
 * Round 19 prompt 19 — the manual "Resolve" / "Dismiss as false positive"
 * buttons have been REMOVED per the founder's directive
 * ("resolved only by the sources themselves again"). Contradictions
 * persist as first-class entities; transitions are source-driven.
 *
 * What remains here is a static badge: it shows the legacy status if a
 * row pre-dates the lifecycle table. ACKNOWLEDGE / DISPUTE controls
 * live in ``EngineActions``; the full lifecycle (with the event log)
 * lives on the per-contradiction detail page.
 */
export default function ContradictionActions({
  contradictionId,
  status,
}: {
  contradictionId: string;
  status: string;
}) {
  return (
    <div
      style={{
        marginTop: "0.75rem",
        display: "flex",
        gap: "0.75rem",
        alignItems: "center",
        flexWrap: "wrap",
      }}
    >
      {status !== "active" ? (
        <span
          className="mono"
          style={{
            fontSize: "0.6rem",
            color:
              status === "resolved"
                ? "var(--gold)"
                : status === "acknowledged"
                ? "var(--amber)"
                : "var(--parchment-dim)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
          }}
        >
          {status}
        </span>
      ) : null}
      <Link
        href={`/contradictions/${contradictionId}`}
        className="mono"
        style={{
          fontSize: "0.6rem",
          color: "var(--gold)",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          textDecoration: "none",
        }}
      >
        View lifecycle →
      </Link>
    </div>
  );
}
