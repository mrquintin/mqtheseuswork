import type { Metadata } from "next";

import { bundle } from "@/lib/bundle";

export const metadata: Metadata = {
  title: "Open questions",
};

export default function OpenQuestionsPage() {
  const rows = bundle.openQuestions;

  return (
    <main className="container">
      <h1 style={{ marginTop: 0 }}>Open questions</h1>
      <p className="muted" style={{ maxWidth: "75ch" }}>
        Open questions are intellectual output: they record what the firm does not yet know with enough precision to
        close. Entries are exported from the same unresolved clusters used internally.
      </p>

      <ul style={{ listStyle: "none", padding: 0, margin: "1.25rem 0 0", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        {rows.map((q) => (
          <li key={q.id} className="card">
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              {q.createdAt.slice(0, 10)}
            </div>
            <div style={{ marginTop: "0.35rem", fontWeight: 650 }}>{q.summary}</div>
            {q.unresolvedReason ? (
              <p style={{ marginTop: "0.5rem", marginBottom: 0 }}>
                <span className="muted">What makes it open:</span> {q.unresolvedReason}
              </p>
            ) : null}
            {q.layerDisagreementSummary ? (
              <p className="muted" style={{ marginTop: "0.5rem", marginBottom: 0 }}>
                Layer disagreement: {q.layerDisagreementSummary}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </main>
  );
}
