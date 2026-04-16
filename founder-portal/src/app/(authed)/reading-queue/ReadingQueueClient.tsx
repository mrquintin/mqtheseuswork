"use client";

import { useState } from "react";
import type { ReadingQueueRow } from "@/lib/noosphereLiteratureBridge";

const STATUSES = ["queued", "reading", "engaged", "not_relevant", "skipped"] as const;

export default function ReadingQueueClient({ initialRows }: { initialRows: ReadingQueueRow[] }) {
  const [rows, setRows] = useState(initialRows);

  async function patch(id: string, status: (typeof STATUSES)[number]) {
    const res = await fetch(`/api/reading-queue/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      alert((j as { error?: string }).error || "Update failed");
      return;
    }
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, status } : r)));
  }

  if (rows.length === 0) {
    return <p style={{ color: "var(--parchment-dim)" }}>Queue is empty.</p>;
  }

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {rows.map((r) => (
        <li key={r.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
          <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)" }}>
            session {r.session_id || "—"} · grounding claim <code>{r.grounding_claim_id}</code>
            {r.artifact_id ? (
              <>
                {" "}
                · artifact <code>{r.artifact_id}</code>
              </>
            ) : null}
          </div>
          <div style={{ marginTop: "0.5rem", color: "var(--parchment)" }}>
            <strong>{r.title}</strong>
            {r.author ? <span style={{ color: "var(--parchment-dim)" }}> — {r.author}</span> : null}
          </div>
          {r.rationale ? (
            <p style={{ marginTop: "0.35rem", fontSize: "0.82rem", color: "var(--parchment-dim)" }}>{r.rationale}</p>
          ) : null}
          <div style={{ marginTop: "0.75rem", display: "flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center" }}>
            <span style={{ fontSize: "0.7rem", color: "var(--gold-dim)" }}>status: {r.status}</span>
            {STATUSES.map((s) => (
              <button
                key={s}
                type="button"
                className="btn"
                style={{ fontSize: "0.6rem", padding: "0.2rem 0.5rem", opacity: r.status === s ? 1 : 0.7 }}
                onClick={() => patch(r.id, s)}
              >
                {s}
              </button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
