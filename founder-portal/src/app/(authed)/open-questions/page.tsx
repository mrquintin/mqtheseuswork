import { db } from "@/lib/db";

export default async function OpenQuestionsPage() {
  const rows = await db.openQuestion.findMany({
    orderBy: { createdAt: "desc" },
    take: 40,
  });

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        Open questions
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem" }}>
        Unresolved coherence tensions (OpenQuestionCandidate).
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {rows.map((q) => (
          <li key={q.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
            <p style={{ color: "var(--parchment)", fontSize: "1rem" }}>{q.summary}</p>
            <p style={{ fontSize: "0.75rem", color: "var(--parchment-dim)", marginTop: "0.5rem" }}>
              {q.unresolvedReason || "—"}
            </p>
            <p style={{ fontSize: "0.65rem", color: "var(--gold-dim)", marginTop: "0.35rem" }}>
              Layers: {q.layerDisagreementSummary || "n/a"} · claims {q.claimAId.slice(0, 6)}… / {q.claimBId.slice(0, 6)}…
            </p>
          </li>
        ))}
      </ul>
    </main>
  );
}
