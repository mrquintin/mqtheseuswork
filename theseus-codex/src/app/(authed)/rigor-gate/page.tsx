import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import Link from "next/link";
import { fetchGateSubmissions, toCSV, downloadHref } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

export default async function RigorGatePage({
  searchParams,
}: {
  searchParams: Promise<{ ledger?: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const sp = await searchParams;
  const submissions = await fetchGateSubmissions(tenant.organizationId);

  const csvData = toCSV(
    submissions.map((s) => ({
      id: s.id,
      kind: s.kind,
      status: s.status,
      submittedBy: s.submittedBy,
      submittedAt: s.submittedAt,
      resolvedAt: s.resolvedAt ?? "",
    })),
  );

  function statusColor(status: string): string {
    switch (status) {
      case "approved": return "var(--gold)";
      case "rejected": return "var(--ember)";
      case "overridden": return "var(--parchment)";
      default: return "var(--parchment-dim)";
    }
  }

  async function submitToGate(formData: FormData) {
    "use server";
    const conclusionId = formData.get("conclusionId") as string;
    const kind = formData.get("kind") as string;
    const notes = formData.get("notes") as string;
    if (!conclusionId || !kind) return;

    const base = process.env.PORTAL_API_BASE || "http://localhost:3000";
    const res = await fetch(`${base}/api/round3/gate/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conclusionId, kind, notes }),
    });
    const data = await res.json();
    revalidatePath("/rigor-gate");
    redirect(`/rigor-gate?ledger=${data.ledgerEntryId || "done"}`);
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
        Rigor gate
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1rem", fontSize: "0.9rem" }}>
        All gate submissions. Every mutation in the portal passes through this gate before execution.
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
          Submission recorded. Ledger entry: {sp.ledger}
        </div>
      )}

      <details style={{ marginBottom: "1.5rem" }}>
        <summary
          style={{
            cursor: "pointer",
            color: "var(--gold-dim)",
            fontFamily: "'Cinzel', serif",
            fontSize: "0.75rem",
            letterSpacing: "0.1em",
          }}
        >
          Submit new gate request
        </summary>
        <form
          action={submitToGate}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            marginTop: "0.75rem",
            maxWidth: "400px",
          }}
        >
          <input name="conclusionId" placeholder="Conclusion ID" required style={{ fontSize: "0.8rem" }} />
          <input name="kind" placeholder="Kind (e.g. promotion, retraction)" required style={{ fontSize: "0.8rem" }} />
          <textarea name="notes" placeholder="Notes (optional)" rows={2} style={{ fontSize: "0.8rem" }} />
          <button type="submit" className="btn-solid" style={{ fontSize: "0.65rem", alignSelf: "flex-start" }}>
            Submit to gate
          </button>
        </form>
      </details>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(csvData, "text/csv")}
          download="gate-submissions.csv"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(submissions, null, 2), "application/json")}
          download="gate-submissions.json"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {submissions.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No gate submissions yet.
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {["Kind", "Status", "Submitted by", "Date", ""].map((h) => (
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
            {submissions.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                  {s.kind}
                </td>
                <td style={{ padding: "0.6rem 0.75rem", color: statusColor(s.status), fontSize: "0.75rem", textTransform: "uppercase" }}>
                  {s.status}
                </td>
                <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                  {s.submittedBy}
                </td>
                <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment-dim)", fontSize: "0.75rem" }}>
                  {s.submittedAt ? s.submittedAt.slice(0, 16) : ""}
                </td>
                <td style={{ padding: "0.6rem 0.75rem" }}>
                  <Link
                    href={`/rigor-gate/${s.id}`}
                    style={{ color: "var(--gold)", fontSize: "0.75rem", textDecoration: "none" }}
                  >
                    Detail →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
