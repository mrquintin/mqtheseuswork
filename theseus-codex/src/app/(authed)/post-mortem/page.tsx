import { redirect } from "next/navigation";
import { fetchPostMortems, toCSV } from "@/lib/api/round3";
import DownloadButton from "@/components/DownloadButton";
import { requireTenantContext } from "@/lib/tenant";

export default async function PostMortemPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const records = await fetchPostMortems(tenant.organizationId);
  const csvData = toCSV(
    records.map((r) => ({
      id: r.id,
      conclusionId: r.conclusionId,
      retractedAt: r.retractedAt,
      reason: r.reason,
      rootCause: r.rootCause,
      founderName: r.founderName,
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
        Post-mortem analysis
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1rem", fontSize: "0.9rem" }}>
        Retracted or failed conclusions with root-cause analysis and prevention notes.
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <DownloadButton
          data={csvData}
          filename="post-mortems.csv"
          mime="text/csv"
          label="Download CSV"
          className="btn"
          style={{ fontSize: "0.65rem" }}
        />
        <DownloadButton
          data={JSON.stringify(records, null, 2)}
          filename="post-mortems.json"
          mime="application/json"
          label="Download JSON"
          className="btn"
          style={{ fontSize: "0.65rem" }}
        />
      </div>

      {records.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No post-mortems recorded yet. When conclusions are retracted, their analysis appears here.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "1rem" }}>
          {records.map((r) => (
            <li key={r.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.65rem", color: "var(--ember)", textTransform: "uppercase" }}>
                  retracted {r.retractedAt ? r.retractedAt.slice(0, 10) : ""}
                </span>
                <span style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
                  by {r.founderName}
                </span>
              </div>
              <p style={{ marginTop: "0.5rem", color: "var(--parchment)" }}>{r.conclusionText}</p>
              <div style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
                <div style={{ color: "var(--parchment-dim)" }}>
                  <strong style={{ color: "var(--gold-dim)" }}>Reason:</strong> {r.reason}
                </div>
                <div style={{ color: "var(--parchment-dim)", marginTop: "0.25rem" }}>
                  <strong style={{ color: "var(--gold-dim)" }}>Root cause:</strong> {r.rootCause}
                </div>
                {r.preventionNotes && (
                  <div style={{ color: "var(--parchment-dim)", marginTop: "0.25rem" }}>
                    <strong style={{ color: "var(--gold-dim)" }}>Prevention:</strong> {r.preventionNotes}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
