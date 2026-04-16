import { redirect } from "next/navigation";
import Link from "next/link";
import { getFounder } from "@/lib/auth";
import {
  fetchProvenanceRecords,
  toCSV,
  downloadHref,
  type ProvenanceRecord,
} from "@/lib/api/round3";

export default async function ProvenancePage() {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const records = await fetchProvenanceRecords();
  const csvData = toCSV(
    records.map((r) => ({
      id: r.id,
      conclusionId: r.conclusionId,
      extractionMethod: r.extractionMethod,
      confidence: r.confidence,
      createdAt: r.createdAt,
    })),
  );

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Provenance
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1rem", fontSize: "0.9rem" }}>
        Full extraction provenance for every conclusion — how each claim was derived from source material.
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(csvData, "text/csv")}
          download="provenance.csv"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(records, null, 2), "application/json")}
          download="provenance.json"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {records.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No provenance records found. Run{" "}
          <code style={{ color: "var(--gold-dim)" }}>python -m noosphere ingest</code> to generate provenance data.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {records.map((r) => (
            <ProvenanceCard key={r.id} record={r} />
          ))}
        </ul>
      )}
    </main>
  );
}

function ProvenanceCard({ record }: { record: ProvenanceRecord }) {
  return (
    <li className="portal-card" style={{ padding: "1rem 1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
        <span style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
          conclusion {record.conclusionId.slice(0, 8)}…
        </span>
        <span style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
          {record.extractionMethod} · confidence {(record.confidence * 100).toFixed(0)}%
        </span>
      </div>
      {record.chain.length > 0 && (
        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
          {record.chain.map((link, i) => (
            <div key={i} style={{ color: "var(--parchment)", paddingLeft: `${link.step * 1}rem` }}>
              <span style={{ color: "var(--gold-dim)" }}>{link.kind}</span>
              {" → "}
              {link.detail}
            </div>
          ))}
        </div>
      )}
      <div style={{ marginTop: "0.35rem", fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
        {record.createdAt ? record.createdAt.slice(0, 10) : ""}
        {record.sourceUploadId ? ` · upload ${record.sourceUploadId.slice(0, 8)}…` : ""}
      </div>
    </li>
  );
}
