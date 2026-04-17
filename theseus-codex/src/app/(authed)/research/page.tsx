import { db } from "@/lib/db";

export default async function ResearchPage() {
  const rows = await db.researchSuggestion.findMany({
    orderBy: { createdAt: "desc" },
    take: 40,
    include: { suggestedForFounder: { select: { name: true } } },
  });

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        Research advisor
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem" }}>
        Suggestions mirrored from Noosphere <code>ResearchSuggestion</code> shape.
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {rows.map((r) => {
          let uris: string[] = [];
          try {
            uris = JSON.parse(r.readingUris) as string[];
          } catch {
            uris = [];
          }
          return (
            <li key={r.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <h2 style={{ fontSize: "1rem", color: "var(--gold)", marginBottom: "0.35rem" }}>{r.title}</h2>
              <p style={{ fontSize: "0.85rem", color: "var(--parchment-dim)" }}>{r.summary}</p>
              <p style={{ fontSize: "0.75rem", marginTop: "0.5rem", color: "var(--parchment)" }}>{r.rationale}</p>
              {r.suggestedForFounder && (
                <p style={{ fontSize: "0.65rem", marginTop: "0.35rem", color: "var(--gold-dim)" }}>
                  For: {r.suggestedForFounder.name}
                </p>
              )}
              {uris.length > 0 && (
                <ul style={{ marginTop: "0.5rem", fontSize: "0.75rem" }}>
                  {uris.map((u) => (
                    <li key={u}>
                      <a href={u} style={{ color: "var(--gold)" }}>
                        {u}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </main>
  );
}
