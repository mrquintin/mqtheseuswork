import Link from "next/link";
import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

/**
 * /deals — VC firm preset's daily-driver page.
 *
 * Each row is one investment opportunity. The principle-alignment
 * column shows a roll-up count (match / conflict / unclear) so the
 * partner can scan the queue and click into the rows that need
 * attention.
 *
 * The page is only meaningful under the vc_firm preset; for tenants
 * without the deals module enabled the layout still renders but the
 * list is empty + the page links the operator to the preset docs.
 */
export default async function DealsIndexPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const deals = await db.deal.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { updatedAt: "desc" },
    include: { alignments: true },
  });

  type Row = {
    id: string;
    name: string;
    stage: string;
    sector: string;
    decisionStatus: string;
    match: number;
    conflict: number;
    unclear: number;
    updatedAt: Date;
  };

  const rows: Row[] = deals.map((d) => {
    let match = 0;
    let conflict = 0;
    let unclear = 0;
    for (const a of d.alignments) {
      if (a.verdict === "MATCH") match++;
      else if (a.verdict === "CONFLICT") conflict++;
      else unclear++;
    }
    return {
      id: d.id,
      name: d.name,
      stage: d.stage,
      sector: d.sector,
      decisionStatus: d.decisionStatus,
      match,
      conflict,
      unclear,
      updatedAt: d.updatedAt,
    };
  });

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
          Deals
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
          {rows.length} {rows.length === 1 ? "opportunity" : "opportunities"}
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
          Each deal lists the firm principles that apply, with the agent's
          verdict and citations. The agent surfaces which principles apply;
          the partner decides.
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
          data-testid="deals-empty-state"
        >
          No deals yet. Create one to see principle alignment.
        </p>
      ) : (
        <table
          data-testid="deals-index-table"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontFamily: "'EB Garamond', serif",
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: "1px solid var(--amber-dim)",
                textAlign: "left",
              }}
            >
              <th style={{ padding: "0.6rem 0.4rem" }}>Name</th>
              <th style={{ padding: "0.6rem 0.4rem" }}>Stage</th>
              <th style={{ padding: "0.6rem 0.4rem" }}>Sector</th>
              <th style={{ padding: "0.6rem 0.4rem" }}>Status</th>
              <th style={{ padding: "0.6rem 0.4rem" }}>Alignment</th>
              <th style={{ padding: "0.6rem 0.4rem" }}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                style={{ borderBottom: "1px solid rgba(180,150,80,0.15)" }}
                data-testid="deals-row"
                data-deal-id={r.id}
              >
                <td style={{ padding: "0.55rem 0.4rem" }}>
                  <Link
                    href={`/deals/${r.id}`}
                    style={{ color: "var(--amber)" }}
                  >
                    {r.name}
                  </Link>
                </td>
                <td style={{ padding: "0.55rem 0.4rem" }}>{r.stage || "—"}</td>
                <td style={{ padding: "0.55rem 0.4rem" }}>
                  {r.sector || "—"}
                </td>
                <td
                  className="mono"
                  style={{
                    padding: "0.55rem 0.4rem",
                    fontSize: "0.7rem",
                    letterSpacing: "0.12em",
                  }}
                >
                  {r.decisionStatus}
                </td>
                <td
                  className="mono"
                  style={{
                    padding: "0.55rem 0.4rem",
                    fontSize: "0.75rem",
                  }}
                >
                  <span style={{ color: "var(--match, #5fa86b)" }}>
                    {r.match}m
                  </span>{" "}
                  <span style={{ color: "var(--conflict, #c05050)" }}>
                    {r.conflict}c
                  </span>{" "}
                  <span style={{ color: "var(--parchment-dim)" }}>
                    {r.unclear}?
                  </span>
                </td>
                <td
                  className="mono"
                  style={{
                    padding: "0.55rem 0.4rem",
                    color: "var(--parchment-dim)",
                    fontSize: "0.7rem",
                  }}
                >
                  {r.updatedAt.toISOString().slice(0, 10)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
