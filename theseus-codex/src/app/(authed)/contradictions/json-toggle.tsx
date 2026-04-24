"use client";

import { useState } from "react";

/**
 * Keeps the raw six-layer JSON accessible for developers / audits
 * without it dominating the expanded card by default. The prose
 * LayerBreakdown above remains the primary surface.
 */
export default function JsonToggle({ json }: { json: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: "0.75rem" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          color: "var(--amber-dim)",
          cursor: "pointer",
          fontSize: "0.65rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          padding: 0,
        }}
      >
        {open ? "Hide raw JSON" : "View raw JSON"}
      </button>
      {open && (
        <pre
          style={{
            background: "var(--stone-mid)",
            padding: "0.75rem",
            borderRadius: 2,
            overflow: "auto",
            fontSize: "0.7rem",
            border: "1px solid var(--border)",
            color: "var(--parchment)",
            margin: "0.5rem 0 0",
          }}
        >
          {tryPretty(json)}
        </pre>
      )}
    </div>
  );
}

function tryPretty(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2);
  } catch {
    return s;
  }
}
