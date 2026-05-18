import Link from "next/link";
import { redirect } from "next/navigation";

import { listRecentPrinciples } from "@/lib/principlesApi";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

const RECENT_LIMIT = 100;

/**
 * Recent principles — read-only audit log. Replaces the old
 * founder-action surface at this URL (decommissioned 2026-05-17 per
 * `decommissioned_triage_uis_2026_05_17` in BUG_CATALOG.md).
 *
 * Distillation now auto-accepts (`auto_accept_principles_2026_05_17`);
 * this page renders the most-recent principles descending by
 * `createdAt`, with no actionable buttons. Each row links to the
 * canonical detail at `/principles/[id]`.
 */
export default async function RecentPrinciplesPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const rows = await listRecentPrinciples(tenant.organizationId, RECENT_LIMIT);

  return (
    <main
      data-testid="recent-principles"
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
          Recent principles
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
            marginTop: "0.4rem",
          }}
          data-testid="recent-principles-banner"
        >
          Principle distillation is automatic. Read-only log, most
          recent first.
        </p>
        <p
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
            marginTop: "0.2rem",
          }}
        >
          {rows.length} principle{rows.length === 1 ? "" : "s"} in window
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
          No principles distilled yet.
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
              data-testid="recent-principle-row"
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
                  title="Conviction score"
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
                <span>{new Date(row.createdAt).toLocaleDateString()}</span>
                <span>status · {row.status}</span>
                {row.domains.length > 0 ? (
                  <span>
                    domains ·{" "}
                    {row.domains.slice(0, 4).join(", ")}
                    {row.domains.length > 4 ? "…" : ""}
                  </span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
