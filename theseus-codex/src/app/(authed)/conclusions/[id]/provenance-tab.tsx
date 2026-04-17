import { fetchProvenanceForConclusion, type ProvenanceRecord } from "@/lib/api/round3";

export default async function ProvenanceTab({ conclusionId }: { conclusionId: string }) {
  const records = await fetchProvenanceForConclusion(conclusionId);

  if (records.length === 0) {
    return (
      <div style={{ padding: "0.75rem 0", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        No provenance records for this conclusion.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {records.map((r) => (
        <div key={r.id} style={{ padding: "0.75rem 1rem", borderLeft: "2px solid var(--gold-dim)" }}>
          <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
            {r.extractionMethod} · confidence {(r.confidence * 100).toFixed(0)}%
          </div>
          {r.chain.length > 0 && (
            <div style={{ marginTop: "0.35rem", fontSize: "0.8rem" }}>
              {r.chain.map((link, i) => (
                <div key={i} style={{ color: "var(--parchment)", paddingLeft: `${link.step * 0.75}rem` }}>
                  <span style={{ color: "var(--gold-dim)" }}>{link.kind}</span> → {link.detail}
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: "0.25rem", fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
            {r.createdAt ? r.createdAt.slice(0, 10) : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
