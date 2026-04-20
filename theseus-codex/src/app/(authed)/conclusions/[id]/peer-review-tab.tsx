import Link from "next/link";
import { fetchPeerReviewsDiag, type Finding } from "@/lib/api/round3";
import { peerVerdictColor, severityColor } from "@/lib/colors";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Peer-review tab on the conclusion-detail page.
 *
 * Tenant-scoped fetch with diagnostic propagation — if `peer_review`
 * is missing / malformed the error bubbles up behind a `<details>`
 * toggle instead of looking like a genuine "no reviews" state.
 */
export default async function PeerReviewTab({ conclusionId }: { conclusionId: string }) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  const { records: reviews, error } = await fetchPeerReviewsDiag(
    tenant.organizationId,
    conclusionId,
  );

  return (
    <div>
      <div
        style={{
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          marginBottom: "0.75rem",
          lineHeight: 1.5,
        }}
      >
        Automated reviewers assess this conclusion across methodological,
        evidential, and rhetorical dimensions.
        <span style={{ color: "var(--gold)" }}> Endorse</span> = conclusion
        stands,
        <span style={{ color: "var(--ember)" }}> Challenge</span> = issues found,
        <span style={{ color: "var(--parchment-dim)" }}> Abstain</span> =
        insufficient data to judge.
      </div>

      {reviews.length === 0 ? (
        <div style={{ padding: "0.75rem 0", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
          No peer reviews yet.{" "}
          <Link href={`/peer-review/${conclusionId}`} style={{ color: "var(--gold)", textDecoration: "none" }}>
            Run one →
          </Link>
          {error && (
            <details style={{ marginTop: "0.5rem" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.7rem", color: "var(--ember)" }}>
                Query diagnostic
              </summary>
              <pre
                style={{
                  fontSize: "0.65rem",
                  color: "var(--parchment-dim)",
                  marginTop: "0.25rem",
                  whiteSpace: "pre-wrap",
                }}
              >
                {error}
              </pre>
            </details>
          )}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {reviews.map((r) => (
            <div key={r.id} style={{ padding: "0.6rem 1rem", borderLeft: `2px solid ${peerVerdictColor(r.verdict)}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--parchment)" }}>{r.reviewerName}</span>
                <span style={{ fontSize: "0.65rem", color: peerVerdictColor(r.verdict), textTransform: "uppercase" }}>
                  {r.verdict}
                </span>
              </div>
              <p style={{ marginTop: "0.25rem", color: "var(--parchment)", fontSize: "0.8rem" }}>
                {r.commentary}
              </p>
              <FindingsBlock findings={r.findings} />
              <div style={{ marginTop: "0.15rem", fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
                {r.createdAt ? r.createdAt.slice(0, 16) : ""}
              </div>
            </div>
          ))}
          <Link
            href={`/peer-review/${conclusionId}`}
            style={{ color: "var(--gold)", fontSize: "0.75rem", textDecoration: "none", marginTop: "0.25rem" }}
          >
            View all / Run new review →
          </Link>
        </div>
      )}
    </div>
  );
}

function FindingsBlock({ findings }: { findings: Finding[] }) {
  if (!findings || findings.length === 0) return null;
  const hasBlocker = findings.some((f) => f.severity === "blocker");
  return (
    <details style={{ marginTop: "0.5rem" }}>
      <summary
        style={{
          cursor: "pointer",
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          letterSpacing: "0.08em",
        }}
      >
        {findings.length} finding{findings.length > 1 ? "s" : ""}
        {hasBlocker && " (includes blockers)"}
      </summary>
      <div style={{ marginTop: "0.35rem", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        {findings.map((f, i) => (
          <div
            key={i}
            style={{
              padding: "0.4rem 0.75rem",
              borderLeft: `2px solid ${severityColor(f.severity)}`,
              fontSize: "0.75rem",
            }}
          >
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <span
                style={{
                  color: severityColor(f.severity),
                  textTransform: "uppercase",
                  fontSize: "0.6rem",
                  letterSpacing: "0.1em",
                }}
              >
                {f.severity}
              </span>
              <span style={{ color: "var(--parchment-dim)", fontSize: "0.6rem" }}>
                {f.category}
              </span>
            </div>
            <p style={{ color: "var(--parchment)", margin: "0.2rem 0" }}>{f.detail}</p>
            {f.suggestedAction && (
              <p style={{ color: "var(--gold-dim)", fontSize: "0.7rem", fontStyle: "italic", margin: 0 }}>
                Suggested: {f.suggestedAction}
              </p>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
