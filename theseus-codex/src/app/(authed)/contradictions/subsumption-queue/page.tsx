import Link from "next/link";
import { db } from "@/lib/db";
import { resolveClaimTexts } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";
import SubsumptionTriage from "./subsumption-triage";

/**
 * Subsumption queue — Round 19 prompt 19.
 *
 * The synthesis engine (prompt 10) flags candidate principles that may
 * subsume both sides of an existing contradiction. The auto-resolver
 * stamps such candidates on the lifecycle row's
 * ``pendingSubsumptionPrincipleId``. The agent never auto-applies a
 * SUBSUMED transition — the founder reviews each candidate here and
 * either ACCEPTS (terminal SUBSUMED_BY_SYNTHESIS) or REJECTS (the
 * candidate is cleared; status stays STANDING).
 */
export default async function SubsumptionQueuePage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const rows = await db.contradictionLifecycle.findMany({
    where: {
      organizationId: tenant.organizationId,
      pendingSubsumptionPrincipleId: { not: null },
    },
    orderBy: { lastTransitionAt: "desc" },
    take: 50,
  });

  const contradictionIds = rows.map((r) => r.contradictionId);
  const contradictions = contradictionIds.length
    ? await db.contradiction.findMany({
        where: { id: { in: contradictionIds } },
        select: {
          id: true,
          claimAId: true,
          claimBId: true,
          severity: true,
          narrative: true,
        },
      })
    : [];
  const byId = new Map(contradictions.map((c) => [c.id, c]));

  const claimIds = new Set<string>();
  for (const c of contradictions) {
    claimIds.add(c.claimAId);
    claimIds.add(c.claimBId);
  }
  const candidateIds = rows
    .map((r) => r.pendingSubsumptionPrincipleId)
    .filter((p): p is string => Boolean(p));
  const allIds = [...claimIds, ...candidateIds];
  const claimTexts = allIds.length
    ? await resolveClaimTexts(tenant.organizationId, allIds)
    : {};

  return (
    <main style={{ maxWidth: "920px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Subsumption queue
      </h1>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "0.95rem",
          color: "var(--parchment-dim)",
          maxWidth: "44em",
          lineHeight: 1.55,
          marginBottom: "1.5rem",
        }}
      >
        When the synthesis engine produces a principle that may subsume
        both sides of an existing contradiction, it ends up here. The
        agent never auto-applies a SUBSUMED transition; you must accept
        each candidate explicitly. Rejecting a candidate clears it and
        the contradiction stays standing.
      </p>

      {rows.length === 0 ? (
        <div style={{ padding: "2rem", textAlign: "center" }}>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1rem",
              color: "var(--parchment)",
            }}
          >
            No pending candidates.
          </p>
        </div>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "1rem",
          }}
        >
          {rows.map((r) => {
            const c = byId.get(r.contradictionId);
            const candidateId = r.pendingSubsumptionPrincipleId!;
            return (
              <li
                key={r.id}
                className="portal-card"
                style={{
                  padding: "1.25rem",
                  borderLeft: "3px solid var(--gold)",
                }}
              >
                <div
                  className="mono"
                  style={{
                    fontSize: "0.6rem",
                    color: "var(--amber-dim)",
                    letterSpacing: "0.16em",
                    textTransform: "uppercase",
                    marginBottom: "0.5rem",
                  }}
                >
                  Contradiction · {r.currentStatus.replace(/_/g, " ")}
                </div>
                {c ? (
                  <>
                    <p
                      style={{
                        margin: "0 0 0.4rem",
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "0.95rem",
                        color: "var(--parchment)",
                      }}
                    >
                      A: {truncate(claimTexts[c.claimAId] || c.claimAId)}
                    </p>
                    <p
                      style={{
                        margin: "0 0 0.6rem",
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "0.95rem",
                        color: "var(--parchment)",
                      }}
                    >
                      B: {truncate(claimTexts[c.claimBId] || c.claimBId)}
                    </p>
                  </>
                ) : null}
                <div
                  className="mono"
                  style={{
                    fontSize: "0.6rem",
                    color: "var(--gold)",
                    letterSpacing: "0.16em",
                    textTransform: "uppercase",
                    marginBottom: "0.3rem",
                  }}
                >
                  Synthesis candidate
                </div>
                <p
                  style={{
                    margin: "0 0 0.75rem",
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1rem",
                    color: "var(--parchment)",
                    lineHeight: 1.55,
                  }}
                >
                  {truncate(claimTexts[candidateId] || candidateId, 260)}
                </p>
                <SubsumptionTriage
                  contradictionId={r.contradictionId}
                  candidatePrincipleId={candidateId}
                />
                <div
                  style={{
                    marginTop: "0.6rem",
                  }}
                >
                  <Link
                    href={`/contradictions/${r.contradictionId}`}
                    className="mono"
                    style={{
                      fontSize: "0.6rem",
                      color: "var(--amber-dim)",
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      textDecoration: "none",
                    }}
                  >
                    View lifecycle →
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

function truncate(s: string, n: number = 180): string {
  if (s.length <= n) return s;
  return s.slice(0, n) + "…";
}
