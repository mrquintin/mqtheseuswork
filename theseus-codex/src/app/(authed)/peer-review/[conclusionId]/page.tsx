import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { getFounder } from "@/lib/auth";
import {
  fetchPeerReviews,
  submitToRigorGate,
  toCSV,
  downloadHref,
} from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";
import { requireTenantContext } from "@/lib/tenant";

export default async function PeerReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ conclusionId: string }>;
  searchParams: Promise<{ ledger?: string }>;
}) {
  // Tenant context is required here for two reasons: it verifies the
  // caller is still authenticated (same effect as the previous
  // `getFounder()` call), AND it hands us the `organizationId` we need
  // to forward into the tenant-scoped SQL below. `requireTenantContext`
  // calls `getFounder()` under the hood, so this is one round-trip, not
  // two.
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const { conclusionId } = await params;
  const sp = await searchParams;
  const reviews = await fetchPeerReviews(tenant.organizationId, conclusionId);

  const csvData = toCSV(
    reviews.map((r) => ({
      id: r.id,
      reviewerName: r.reviewerName,
      verdict: r.verdict,
      commentary: r.commentary,
      createdAt: r.createdAt,
    })),
  );

  async function runReview() {
    "use server";
    // Server action runs on the server; calling underlying helpers
    // directly avoids (a) a pointless HTTP round-trip to ourselves,
    // (b) the cookie-forwarding problem that broke auth on the old
    // self-fetch path, and (c) the PORTAL_API_BASE env dependency
    // that only worked on localhost.
    const founder = await getFounder();
    if (!founder) redirect("/login");

    const gate = await submitToRigorGate("peer_review.run", founder.name);
    if (!gate.approved) {
      redirect(
        `/peer-review/${conclusionId}?ledger=${encodeURIComponent(
          `rejected:${gate.reason || "rigor gate"}`,
        )}`,
      );
    }

    await callNoosphereJson(
      ["peer-review", "--conclusion-id", conclusionId],
      "Peer review run failed",
    );
    revalidatePath(`/peer-review/${conclusionId}`);
    redirect(`/peer-review/${conclusionId}?ledger=${gate.ledgerEntryId || "done"}`);
  }

  function verdictColor(verdict: string): string {
    switch (verdict) {
      case "endorse": return "var(--gold)";
      case "challenge": return "var(--ember)";
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
        Peer review
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "0.5rem", fontSize: "0.9rem" }}>
        Reviews for conclusion{" "}
        <code style={{ color: "var(--gold-dim)" }}>{conclusionId.slice(0, 12)}…</code>
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
          Review recorded. Ledger entry: {sp.ledger}
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <form action={runReview}>
          <button type="submit" className="btn-solid" style={{ fontSize: "0.65rem" }}>
            Run peer review
          </button>
        </form>
        <a
          href={downloadHref(csvData, "text/csv")}
          download={`peer-review-${conclusionId.slice(0, 8)}.csv`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(reviews, null, 2), "application/json")}
          download={`peer-review-${conclusionId.slice(0, 8)}.json`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {reviews.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No peer reviews recorded for this conclusion. Click &quot;Run peer review&quot; to trigger one.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {reviews.map((r) => (
            <li key={r.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--parchment)" }}>
                  {r.reviewerName}
                </span>
                <span style={{ fontSize: "0.65rem", color: verdictColor(r.verdict), textTransform: "uppercase" }}>
                  {r.verdict}
                </span>
              </div>
              <p style={{ marginTop: "0.5rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                {r.commentary}
              </p>
              <div style={{ marginTop: "0.25rem", fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
                {r.createdAt ? r.createdAt.slice(0, 16) : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
