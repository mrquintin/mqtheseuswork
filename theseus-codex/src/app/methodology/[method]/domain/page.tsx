import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import MethodTabs from "@/components/MethodTabs";
import PublicHeader from "@/components/PublicHeader";
import { getCatalog } from "@/lib/failureModes";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { Prisma } from "@prisma/client";
import { methodEntry } from "@/lib/methodologyManifest";

export const metadata: Metadata = {
  title: "Methodology · domain",
};

const STATUS_LABEL: Record<string, string> = {
  in_bounds: "In bounds",
  edge_case: "Edge case",
  out_of_bounds: "Out of bounds",
};

const STATUS_COLOR: Record<string, string> = {
  in_bounds: "var(--public-muted, #888)",
  edge_case: "var(--amber, #d4a017)",
  out_of_bounds: "var(--ember, #c0392b)",
};

type DomainCount = {
  status: string;
  n: number;
};

type RecentVerdict = {
  status: string;
  reason: string;
  margin: number;
  matchedTags: string[];
  computedAt: string | null;
};

/**
 * Domain tab — surfaces the public summary of the firm's domain bound
 * verdicts for this method. Counts only verdicts attached to public
 * (`PublishedConclusion`) conclusions; private verdicts never enter
 * the aggregate. The reason text is curated by the bound check itself
 * and is allowed to be public.
 */
export default async function PublicMethodologyDomainPage({
  params,
}: {
  params: Promise<{ method: string }>;
}) {
  const { method } = await params;
  const methodName = decodeURIComponent(method);
  const catalog = getCatalog(methodName);
  if (!catalog) notFound();

  const entry = await methodEntry(methodName);
  const [counts, recent] = await Promise.all([
    fetchDomainCounts(methodName),
    fetchRecentVerdicts(methodName),
  ]);

  const total = counts.reduce((acc, c) => acc + c.n, 0);

  const founder = await getFounder();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <Link
          href="/methodology"
          className="public-muted"
          style={{ fontSize: "0.75rem" }}
        >
          ← Methodology
        </Link>
        <h1 className="public-title" style={{ marginTop: "0.5rem" }}>
          Domain ·{" "}
          <span style={{ fontFamily: "monospace" }}>{methodName}</span>
        </h1>

        <MethodTabs method={methodName} active="domain" />

        <p className="public-muted public-lede">
          Domain Sensitivity is the gate on the firm's methodology score:
          a method that does not fit the question's domain cannot be
          redeemed by being severe and progressive elsewhere. This page
          shows where the firm has judged this method in-bounds, an edge
          case, or out-of-bounds across its public conclusions.
        </p>

        <section className="public-section" aria-labelledby="domain-counts-title">
          <h2 id="domain-counts-title">Verdicts on public conclusions</h2>
          {total === 0 ? (
            <p className="public-muted">
              No public domain verdicts are attached to this method yet.
              The bound check runs against every conclusion that uses the
              method; results appear here once at least one is published.
            </p>
          ) : (
            <ul
              role="list"
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: "0.75rem",
              }}
            >
              {(["in_bounds", "edge_case", "out_of_bounds"] as const).map(
                (status) => {
                  const n =
                    counts.find((c) => c.status === status)?.n ?? 0;
                  const pct = total > 0 ? Math.round((n / total) * 100) : 0;
                  return (
                    <li
                      key={status}
                      className="public-card"
                      style={{
                        padding: "0.85rem 1rem",
                        borderLeft: `3px solid ${STATUS_COLOR[status]}`,
                      }}
                    >
                      <div
                        className="mono public-muted"
                        style={{
                          fontSize: "0.6rem",
                          letterSpacing: "0.18em",
                          textTransform: "uppercase",
                          marginBottom: "0.4rem",
                        }}
                      >
                        {STATUS_LABEL[status]}
                      </div>
                      <div style={{ fontSize: "1.4rem", fontWeight: 600 }}>
                        {n}
                        <span
                          className="public-muted"
                          style={{
                            fontSize: "0.78rem",
                            marginLeft: "0.4rem",
                            fontWeight: 400,
                          }}
                        >
                          {pct}%
                        </span>
                      </div>
                    </li>
                  );
                },
              )}
            </ul>
          )}
        </section>

        <section className="public-section" aria-labelledby="domain-recent-title">
          <h2 id="domain-recent-title">Most recent verdicts</h2>
          {recent.length === 0 ? (
            <p className="public-muted">No verdicts to show yet.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {recent.map((v, idx) => (
                <li
                  key={`${v.computedAt ?? idx}-${idx}`}
                  className="public-card public-method-card"
                  style={{
                    padding: "0.85rem 1rem",
                    margin: "0.6rem 0",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "0.65rem",
                      alignItems: "baseline",
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      style={{
                        padding: "0.12rem 0.45rem",
                        border: `1px solid ${
                          STATUS_COLOR[v.status] ?? "var(--public-rule)"
                        }`,
                        color:
                          STATUS_COLOR[v.status] ?? "var(--public-muted)",
                        fontFamily: "monospace",
                        fontSize: "0.62rem",
                        letterSpacing: "0.18em",
                        textTransform: "uppercase",
                      }}
                    >
                      {STATUS_LABEL[v.status] ?? v.status}
                    </span>
                    <span
                      className="public-muted"
                      style={{ fontSize: "0.75rem" }}
                    >
                      margin {v.margin.toFixed(2)}
                      {v.computedAt
                        ? ` · ${v.computedAt.slice(0, 10)}`
                        : ""}
                    </span>
                  </div>
                  {v.reason ? (
                    <p style={{ margin: "0.55rem 0 0", fontSize: "0.92rem" }}>
                      {v.reason}
                    </p>
                  ) : null}
                  {v.matchedTags.length > 0 ? (
                    <div
                      className="public-muted mono"
                      style={{ fontSize: "0.7rem", marginTop: "0.35rem" }}
                    >
                      tags: {v.matchedTags.join(" · ")}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="public-section" aria-labelledby="domain-context-title">
          <h2 id="domain-context-title">How this is computed</h2>
          <p className="public-muted">
            Verdicts come from the recorded{" "}
            <span className="mono">DomainBoundVerdict</span> rows. A
            verdict is either anchor-driven (signed angular cosine
            distance to a curated anchor) or tag-only ({"{"}-1, +1{"}"}
            ). The verdict feeds Domain Sensitivity in the firm's
            methodology score; see{" "}
            <Link href="/methodology/criteria#domain-sensitivity">
              the criteria page
            </Link>
            .{" "}
            {entry?.calibration?.domain ? (
              <>
                The headline track-record domain for this method is{" "}
                <span className="mono">{entry.calibration.domain}</span>.
              </>
            ) : null}
          </p>
        </section>
      </main>
    </>
  );
}

async function fetchDomainCounts(methodName: string): Promise<DomainCount[]> {
  type Row = { status: string; n: bigint | number };
  try {
    const rows = await db.$queryRaw<Row[]>(
      Prisma.sql`SELECT dbv.status AS status, COUNT(*)::bigint AS n
                   FROM "DomainBoundVerdict" dbv
                   JOIN "PublishedConclusion" pc
                     ON pc."sourceConclusionId" = dbv."conclusionId"
                    AND pc."organizationId" = dbv."organizationId"
                  WHERE dbv."methodName" = ${methodName}
               GROUP BY dbv.status`,
    );
    return rows.map((r) => ({
      status: r.status,
      n: typeof r.n === "bigint" ? Number(r.n) : Number(r.n),
    }));
  } catch {
    return [];
  }
}

async function fetchRecentVerdicts(
  methodName: string,
): Promise<RecentVerdict[]> {
  type Row = {
    status: string;
    reason: string | null;
    margin: number | string | null;
    matchedTags: string[] | null;
    computedAt: Date | string | null;
  };
  try {
    const rows = await db.$queryRaw<Row[]>(
      Prisma.sql`SELECT dbv.status AS status,
                        dbv.reason AS reason,
                        dbv.margin AS margin,
                        dbv."matchedTags" AS "matchedTags",
                        dbv."createdAt" AS "computedAt"
                   FROM "DomainBoundVerdict" dbv
                   JOIN "PublishedConclusion" pc
                     ON pc."sourceConclusionId" = dbv."conclusionId"
                    AND pc."organizationId" = dbv."organizationId"
                  WHERE dbv."methodName" = ${methodName}
               ORDER BY dbv."createdAt" DESC
                  LIMIT 8`,
    );
    return rows.map((r) => ({
      status: r.status,
      reason: r.reason ?? "",
      margin: typeof r.margin === "string" ? Number(r.margin) : Number(r.margin ?? 0),
      matchedTags: Array.isArray(r.matchedTags) ? r.matchedTags : [],
      computedAt: r.computedAt
        ? r.computedAt instanceof Date
          ? r.computedAt.toISOString()
          : String(r.computedAt)
        : null,
    }));
  } catch {
    return [];
  }
}
