import Link from "next/link";
import { redirect } from "next/navigation";

import { listQueuedPrinciples } from "@/lib/principlesApi";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

/**
 * Founder triage queue for distilled principles.
 *
 * Shows draft + needs-re-review rows, conviction-sorted. The detail
 * page (`/principles/[id]`) carries accept/reject/merge.
 *
 * The queue treats principles as reviewable artifacts: each row prints
 * the cluster size, the distinct domain count, and any drift reason
 * the re-distillation pass attached, so the reviewer reads the
 * provenance next to the candidate text.
 */
export default async function PrinciplesQueuePage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const rows = await listQueuedPrinciples(tenant.organizationId);

  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "2.75rem 2rem",
      }}
    >
      <header style={{ marginBottom: "1.75rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.12em",
            margin: 0,
          }}
        >
          Principles · triage queue
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.4rem",
          }}
        >
          {rows.length} awaiting review · conviction-sorted
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            color: "var(--parchment-dim)",
            marginTop: "0.75rem",
            maxWidth: "44em",
            lineHeight: 1.55,
          }}
        >
          Each draft is a candidate principle the firm keeps re-deriving
          across its conclusions. Conviction is conservative: a single
          high-centrality conclusion does not produce a principle —
          convergence across domains does. Accept (with edits), reject
          (with reason), or merge into an existing principle.
        </p>
      </header>

      {rows.length === 0 ? (
        <p
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.8rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            padding: "2rem 0",
          }}
        >
          No drafts in the queue.
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.85rem",
          }}
        >
          {rows.map((row) => (
            <li
              key={row.id}
              className="portal-card"
              style={{ padding: "1.1rem 1.3rem" }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  gap: "1rem",
                }}
              >
                <Link
                  href={`/principles/${row.id}`}
                  style={{
                    color: "var(--gold)",
                    textDecoration: "none",
                    fontSize: "1rem",
                    fontFamily: "'EB Garamond', serif",
                    flex: 1,
                  }}
                >
                  {row.text}
                </Link>
                <span
                  className="mono"
                  title="Conviction score (conservative; rewards cross-domain breadth)"
                  style={{
                    fontSize: "0.75rem",
                    color: "var(--amber)",
                    letterSpacing: "0.1em",
                  }}
                >
                  {row.convictionScore.toFixed(2)}
                </span>
              </div>
              <div
                className="mono"
                style={{
                  marginTop: "0.5rem",
                  fontSize: "0.65rem",
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  color: "var(--parchment-dim)",
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "0.75rem",
                }}
              >
                <span>cluster · {row.clusterConclusionIds.length}</span>
                <span>domains · {row.domainBreadth}</span>
                <span>status · {row.status}</span>
                {row.driftReason ? (
                  <span style={{ color: "var(--ember, #c0392b)" }}>
                    drift · {row.driftReason}
                  </span>
                ) : null}
              </div>
              {row.domains.length > 0 ? (
                <div
                  style={{
                    marginTop: "0.5rem",
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "0.4rem",
                  }}
                >
                  {row.domains.map((d) => (
                    <span
                      key={d}
                      className="mono"
                      style={{
                        fontSize: "0.6rem",
                        letterSpacing: "0.18em",
                        textTransform: "uppercase",
                        padding: "0.2rem 0.6rem",
                        border: "1px solid var(--border)",
                        color: "var(--parchment-dim)",
                      }}
                    >
                      {d}
                    </span>
                  ))}
                </div>
              ) : (
                <p
                  className="mono"
                  style={{
                    marginTop: "0.5rem",
                    fontSize: "0.6rem",
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    color: "var(--ember, #c0392b)",
                  }}
                >
                  No domain declared · cannot publish
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
