import { Suspense } from "react";
import TemporalReplayBar from "@/components/TemporalReplayBar";
import { db } from "@/lib/db";
import { AS_OF_ISO, asOfEndUtc } from "@/lib/replayDate";

// Defensive parse: any corrupt `sixLayerJson` row would otherwise throw
// during render and 500 the entire /contradictions route, not just that row.
function prettyJsonOrRaw(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2);
  } catch {
    return s;
  }
}

export default async function ContradictionsPage({
  searchParams,
}: {
  searchParams: Promise<{ asOf?: string }>;
}) {
  const sp = await searchParams;
  const asOf = sp.asOf;
  const end = asOf && AS_OF_ISO.test(asOf) ? asOfEndUtc(asOf) : undefined;

  const rows = await db.contradiction.findMany({
    where: end ? { createdAt: { lte: end } } : undefined,
    orderBy: { severity: "desc" },
    take: 50,
  });

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Suspense fallback={null}>
        <TemporalReplayBar />
      </Suspense>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        Contradictions
      </h1>
      {end ? (
        <p style={{ color: "var(--ember)", fontSize: "0.85rem", marginBottom: "1rem" }}>
          Replay: rows with <code>createdAt</code> ≤ end of {asOf} (UTC). This is a portal-store approximation, not
          full Noosphere coherence replay.
        </p>
      ) : null}
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem" }}>
        Sorted by severity. Expand a row to inspect six-layer scores (JSON).
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {rows.map((c) => (
          <li key={c.id} className="portal-card" style={{ padding: 0, overflow: "hidden" }}>
            <details>
              <summary
                style={{
                  cursor: "pointer",
                  padding: "1rem 1.25rem",
                  listStyle: "none",
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "1rem",
                }}
              >
                <span style={{ color: "var(--parchment)" }}>
                  {(c.severity * 100).toFixed(0)}% · {c.claimAId.slice(0, 8)}… ↔ {c.claimBId.slice(0, 8)}…
                </span>
                <span style={{ fontSize: "0.7rem", color: "var(--ember)" }}>severity</span>
              </summary>
              <div style={{ padding: "0 1.25rem 1rem", fontSize: "0.8rem", color: "var(--parchment-dim)" }}>
                {c.narrative && <p style={{ marginBottom: "0.5rem" }}>{c.narrative}</p>}
                {c.sixLayerJson ? (
                  <pre
                    style={{
                      background: "#0d0d12",
                      padding: "0.75rem",
                      borderRadius: "6px",
                      overflow: "auto",
                      fontSize: "0.7rem",
                    }}
                  >
                    {prettyJsonOrRaw(c.sixLayerJson)}
                  </pre>
                ) : (
                  <p>No layer scores stored.</p>
                )}
              </div>
            </details>
          </li>
        ))}
      </ul>
    </main>
  );
}
