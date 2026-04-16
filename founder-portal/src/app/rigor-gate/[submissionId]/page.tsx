import { redirect, notFound } from "next/navigation";
import { revalidatePath } from "next/cache";
import Link from "next/link";
import { getFounder } from "@/lib/auth";
import { fetchGateDetail, downloadHref } from "@/lib/api/round3";

export default async function RigorGateDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ submissionId: string }>;
  searchParams: Promise<{ ledger?: string }>;
}) {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const { submissionId } = await params;
  const sp = await searchParams;
  const detail = await fetchGateDetail(submissionId);
  if (!detail) notFound();

  function statusColor(status: string): string {
    switch (status) {
      case "approved": return "var(--gold)";
      case "rejected": return "var(--ember)";
      case "overridden": return "var(--parchment)";
      default: return "var(--parchment-dim)";
    }
  }

  async function overrideGate(formData: FormData) {
    "use server";
    const verdict = formData.get("verdict") as string;
    const reason = formData.get("reason") as string;
    if (!verdict) return;

    const base = process.env.PORTAL_API_BASE || "http://localhost:3000";
    const res = await fetch(`${base}/api/round3/gate/${submissionId}/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, reason }),
    });
    const data = await res.json();
    revalidatePath(`/rigor-gate/${submissionId}`);
    redirect(`/rigor-gate/${submissionId}?ledger=${data.ledgerEntryId || "done"}`);
  }

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Link href="/rigor-gate" style={{ color: "var(--gold-dim)", fontSize: "0.75rem", textDecoration: "none" }}>
        ← Back to gate submissions
      </Link>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
          marginTop: "1rem",
        }}
      >
        Gate submission
      </h1>

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
          Override recorded. Ledger entry: {sp.ledger}
        </div>
      )}

      <div className="portal-card" style={{ padding: "1.25rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "1.5rem", marginBottom: "1rem" }}>
          <div>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Kind</div>
            <div style={{ color: "var(--parchment)", fontSize: "0.9rem", marginTop: "0.15rem" }}>{detail.kind}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Status</div>
            <div style={{ color: statusColor(detail.status), fontSize: "0.9rem", marginTop: "0.15rem", textTransform: "uppercase" }}>
              {detail.status}
            </div>
          </div>
          <div>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Submitted by</div>
            <div style={{ color: "var(--parchment)", fontSize: "0.9rem", marginTop: "0.15rem" }}>{detail.submittedBy}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Date</div>
            <div style={{ color: "var(--parchment-dim)", fontSize: "0.9rem", marginTop: "0.15rem" }}>
              {detail.submittedAt ? detail.submittedAt.slice(0, 16) : ""}
            </div>
          </div>
        </div>

        {detail.reviewNotes && (
          <div style={{ marginTop: "0.5rem" }}>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Review notes</div>
            <p style={{ color: "var(--parchment)", fontSize: "0.85rem", marginTop: "0.25rem" }}>{detail.reviewNotes}</p>
          </div>
        )}

        {detail.overrideReason && (
          <div style={{ marginTop: "0.5rem" }}>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Override reason</div>
            <p style={{ color: "var(--parchment)", fontSize: "0.85rem", marginTop: "0.25rem" }}>{detail.overrideReason}</p>
          </div>
        )}

        {Object.keys(detail.payload).length > 0 && (
          <div style={{ marginTop: "0.75rem" }}>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Payload</div>
            <pre style={{ color: "var(--parchment-dim)", fontSize: "0.75rem", marginTop: "0.25rem", overflow: "auto" }}>
              {JSON.stringify(detail.payload, null, 2)}
            </pre>
          </div>
        )}

        {detail.ledgerEntryId && (
          <div style={{ marginTop: "0.5rem", fontSize: "0.7rem", color: "var(--parchment-dim)" }}>
            Ledger: {detail.ledgerEntryId}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(JSON.stringify(detail, null, 2), "application/json")}
          download={`gate-${submissionId.slice(0, 8)}.json`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {(detail.status === "pending" || detail.status === "rejected") && (
        <div className="portal-card" style={{ padding: "1.25rem" }}>
          <h2 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", fontSize: "0.9rem", letterSpacing: "0.08em", marginBottom: "0.75rem" }}>
            Override decision
          </h2>
          <form action={overrideGate} style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxWidth: "400px" }}>
            <select name="verdict" required style={{ fontSize: "0.8rem" }}>
              <option value="">Select verdict…</option>
              <option value="approved">Approve</option>
              <option value="rejected">Reject</option>
            </select>
            <textarea name="reason" placeholder="Reason for override" rows={3} style={{ fontSize: "0.8rem" }} />
            <button type="submit" className="btn-solid" style={{ fontSize: "0.65rem", alignSelf: "flex-start" }}>
              Submit override
            </button>
          </form>
        </div>
      )}
    </main>
  );
}
