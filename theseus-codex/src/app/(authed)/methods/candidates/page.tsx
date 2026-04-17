import { redirect } from "next/navigation";
import Link from "next/link";
import { getFounder } from "@/lib/auth";
import { fetchMethodCandidates, toCSV, downloadHref } from "@/lib/api/round3";

export default async function MethodCandidatesPage() {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const candidates = await fetchMethodCandidates();
  const csvData = toCSV(
    candidates.map((c) => ({
      id: c.id,
      name: c.name,
      proposedBy: c.proposedBy,
      status: c.status,
      createdAt: c.createdAt,
      description: c.description,
    })),
  );

  function statusColor(status: string): string {
    switch (status) {
      case "accepted": return "var(--gold)";
      case "rejected": return "var(--ember)";
      case "under_review": return "var(--parchment)";
      default: return "var(--parchment-dim)";
    }
  }

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Link href="/methods" style={{ color: "var(--gold-dim)", fontSize: "0.75rem", textDecoration: "none" }}>
        ← Back to methods
      </Link>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
          marginTop: "1rem",
        }}
      >
        Method candidates
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1rem", fontSize: "0.9rem" }}>
        Proposed methods awaiting review and acceptance into the registry.
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(csvData, "text/csv")}
          download="method-candidates.csv"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(candidates, null, 2), "application/json")}
          download="method-candidates.json"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {candidates.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No method candidates proposed yet.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {candidates.map((c) => (
            <li key={c.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                <span style={{ color: "var(--parchment)", fontFamily: "'Cinzel', serif", fontSize: "0.85rem" }}>
                  {c.name}
                </span>
                <span style={{ fontSize: "0.65rem", color: statusColor(c.status), textTransform: "uppercase" }}>
                  {c.status.replace("_", " ")}
                </span>
              </div>
              <p style={{ marginTop: "0.35rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                {c.description}
              </p>
              <div style={{ marginTop: "0.25rem", fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
                proposed by {c.proposedBy} · {c.createdAt ? c.createdAt.slice(0, 10) : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
