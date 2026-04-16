import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { getFounder } from "@/lib/auth";
import { fetchDecayRecords, toCSV, downloadHref } from "@/lib/api/round3";

export default async function DecayPage({
  searchParams,
}: {
  searchParams: Promise<{ ledger?: string }>;
}) {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const sp = await searchParams;
  const records = await fetchDecayRecords();

  const csvData = toCSV(
    records.map((r) => ({
      id: r.id,
      conclusionId: r.conclusionId,
      currentConfidence: r.currentConfidence,
      decayRate: r.decayRate,
      lastValidated: r.lastValidated,
      projectedExpiry: r.projectedExpiry ?? "",
      status: r.status,
    })),
  );

  function statusColor(status: string): string {
    switch (status) {
      case "healthy": return "var(--gold)";
      case "decaying": return "var(--parchment)";
      case "expired": return "var(--ember)";
      default: return "var(--parchment-dim)";
    }
  }

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Decay dashboard
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1rem", fontSize: "0.9rem" }}>
        Confidence decay tracking for all conclusions. Stale conclusions need revalidation.
      </p>

      {sp.ledger && (
        <div
          className="portal-card"
          style={{
            padding: "0.6rem 1rem",
            marginBottom: "1rem",
            borderLeft: "3px solid var(--gold)",
            fontSize: "0.8rem",
            color: "var(--gold)",
          }}
        >
          Revalidation recorded. Ledger entry: {sp.ledger}
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(csvData, "text/csv")}
          download="decay-records.csv"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(records, null, 2), "application/json")}
          download="decay-records.json"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {records.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No decay records found. Run{" "}
          <code style={{ color: "var(--gold-dim)" }}>python -m noosphere decay scan</code> to compute decay rates.
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {["Conclusion", "Confidence", "Decay rate", "Last validated", "Status", ""].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: "left",
                    padding: "0.5rem 0.75rem",
                    fontFamily: "'Cinzel', serif",
                    fontSize: "0.65rem",
                    color: "var(--gold-dim)",
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <RevalidateRow key={r.id} record={r} statusColor={statusColor} />
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

function RevalidateRow({
  record,
  statusColor,
}: {
  record: {
    id: string;
    conclusionId: string;
    conclusionText: string;
    currentConfidence: number;
    decayRate: number;
    lastValidated: string;
    status: string;
  };
  statusColor: (s: string) => string;
}) {
  async function revalidate() {
    "use server";
    const base = process.env.PORTAL_API_BASE || "http://localhost:3000";
    const res = await fetch(`${base}/api/round3/decay/revalidate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conclusionId: record.conclusionId }),
    });
    const data = await res.json();
    revalidatePath("/decay");
    redirect(`/decay?ledger=${data.ledgerEntryId || "done"}`);
  }

  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment)", fontSize: "0.8rem", maxWidth: "300px" }}>
        {record.conclusionText.slice(0, 80)}
        {record.conclusionText.length > 80 ? "…" : ""}
      </td>
      <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
        {(record.currentConfidence * 100).toFixed(0)}%
      </td>
      <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        {record.decayRate.toFixed(4)}/day
      </td>
      <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment-dim)", fontSize: "0.75rem" }}>
        {record.lastValidated ? record.lastValidated.slice(0, 10) : "never"}
      </td>
      <td style={{ padding: "0.6rem 0.75rem", color: statusColor(record.status), fontSize: "0.75rem", textTransform: "uppercase" }}>
        {record.status}
      </td>
      <td style={{ padding: "0.6rem 0.75rem" }}>
        <form action={revalidate}>
          <button type="submit" className="btn" style={{ fontSize: "0.6rem", padding: "0.25rem 0.6rem" }}>
            Revalidate
          </button>
        </form>
      </td>
    </tr>
  );
}
