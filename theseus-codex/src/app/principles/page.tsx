import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { listPublicPrinciples, type PublicPrincipleRow } from "@/lib/principlesApi";

/**
 * /principles — the firm's principle index, the spine of the Knowledge
 * surfaces.
 *
 * Round 21 reorganises the firm's knowledge around principles. A
 * principle here is not an axiom; it is a single-sentence rule the
 * firm has re-derived enough times across its conclusions that it is
 * willing to use it to judge new evidence. Conclusions are evidence
 * for or against a principle; claims are the raw source material that
 * produced one.
 *
 * The index exposes three filter dimensions:
 *
 *   - `kind` — the principle's structural shape (RULE, CRITERION,
 *     MECHANISM, HEURISTIC, DEFINITION, FORMULA, ALGORITHM) aggregated
 *     from the underlying conclusions' `principleKind`. Falls back to
 *     "unspecified" for legacy clusters whose conclusions pre-date the
 *     principle-shape contract.
 *   - `domain` — facets the list by domain tags the founder attached
 *     when accepting the principle.
 *   - `quantified` — when set, restricts to principles with an
 *     APPROVED `QuantitativeFormalisation` (i.e. ones the firm is
 *     willing to be tested on).
 *
 * Conviction score is shown next to every row; the list is sorted by
 * conviction descending so the firm's most-tested working positions
 * are at the top.
 */

export const metadata: Metadata = {
  title: "Principles · Theseus",
  description:
    "Principles are the firm's reusable rules — what we use to judge new evidence. Each links to the conclusions that produced it, the conclusions that would weaken it, and (where the firm has approved one) the quantitative test that would update it.",
  openGraph: {
    title: "Theseus · principles",
    description:
      "The spine of the firm's knowledge: principles, with evidence for and against, and the quantitative tests that would update them.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

const PRINCIPLE_KINDS = [
  "RULE",
  "CRITERION",
  "MECHANISM",
  "HEURISTIC",
  "DEFINITION",
  "FORMULA",
  "ALGORITHM",
] as const;
type PrincipleKindKey = (typeof PRINCIPLE_KINDS)[number];
type AggregatedKind = PrincipleKindKey | "UNSPECIFIED";

type PrincipleIndexSearchParams = {
  kind?: string;
  domain?: string;
  quantified?: string;
  minConviction?: string;
};

function isPrincipleKind(value: string | null | undefined): value is PrincipleKindKey {
  return value != null && (PRINCIPLE_KINDS as ReadonlyArray<string>).includes(value);
}

function aggregateKind(kinds: Array<string | null>): AggregatedKind {
  const counts = new Map<PrincipleKindKey, number>();
  for (const raw of kinds) {
    if (isPrincipleKind(raw)) {
      counts.set(raw, (counts.get(raw) ?? 0) + 1);
    }
  }
  if (counts.size === 0) return "UNSPECIFIED";
  let best: { kind: PrincipleKindKey; count: number } | null = null;
  for (const [kind, count] of counts) {
    if (!best || count > best.count) best = { kind, count };
  }
  return best!.kind;
}

type EnrichedPrinciple = PublicPrincipleRow & {
  aggregatedKind: AggregatedKind;
  hasApprovedFormalisation: boolean;
};

async function loadEnrichedPrinciples(): Promise<EnrichedPrinciple[]> {
  const principles = await listPublicPrinciples();
  if (principles.length === 0) return [];

  const allConclusionIds = Array.from(
    new Set(principles.flatMap((p) => p.clusterConclusionIds)),
  );
  const principleIds = principles.map((p) => p.id);

  const [kindRows, approvedFormalisations] = await Promise.all([
    allConclusionIds.length > 0
      ? fetchPrincipleKinds(allConclusionIds)
      : Promise.resolve([] as Array<{ id: string; principleKind: string | null }>),
    // Schema-lag-safe — quantitativeFormalisation may not be in the
    // generated client yet on this branch.
    (async () => {
      try {
        // @ts-expect-error — generated client may lag schema; falls back to [].
        const rows = (await db.quantitativeFormalisation?.findMany({
          where: { principleId: { in: principleIds }, status: "APPROVED" },
          select: { principleId: true },
        })) as Array<{ principleId: string }> | undefined;
        return rows ?? [];
      } catch {
        return [] as Array<{ principleId: string }>;
      }
    })(),
  ]);
  const kindByConclusion = new Map(
    kindRows.map((r) => [r.id, r.principleKind] as const),
  );
  const approvedSet = new Set(approvedFormalisations.map((r) => r.principleId));

  return principles.map((p) => ({
    ...p,
    aggregatedKind: aggregateKind(
      p.clusterConclusionIds.map((cid) => kindByConclusion.get(cid) ?? null),
    ),
    hasApprovedFormalisation: approvedSet.has(p.id),
  }));
}

function applyFilters(
  rows: EnrichedPrinciple[],
  filters: {
    kind: string | null;
    domain: string | null;
    quantified: boolean;
    minConviction: number;
  },
): EnrichedPrinciple[] {
  return rows.filter((row) => {
    if (filters.kind && row.aggregatedKind !== filters.kind) return false;
    if (filters.domain && !row.domains.includes(filters.domain)) return false;
    if (filters.quantified && !row.hasApprovedFormalisation) return false;
    if (
      Number.isFinite(filters.minConviction) &&
      row.convictionScore < filters.minConviction
    ) {
      return false;
    }
    return true;
  });
}

function uniqueDomains(rows: EnrichedPrinciple[]): string[] {
  const set = new Set<string>();
  for (const r of rows) for (const d of r.domains) set.add(d);
  return [...set].sort();
}

function parseConviction(raw: string | undefined): number {
  if (!raw) return 0;
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export default async function PrinciplesIndexPage({
  searchParams,
}: {
  searchParams?: Promise<PrincipleIndexSearchParams>;
}) {
  const sp = (await searchParams) ?? {};
  const founder = await getFounder();
  const enriched = await loadEnrichedPrinciples();

  const filters = {
    kind:
      sp.kind && (sp.kind === "UNSPECIFIED" || isPrincipleKind(sp.kind))
        ? sp.kind
        : null,
    domain: sp.domain ? sp.domain : null,
    quantified: sp.quantified === "1" || sp.quantified === "true",
    minConviction: parseConviction(sp.minConviction),
  };
  const visible = applyFilters(enriched, filters);
  const domains = uniqueDomains(enriched);

  function filterHref(patch: Partial<PrincipleIndexSearchParams>): string {
    const next = new URLSearchParams();
    const current: Record<string, string | undefined> = {
      kind: filters.kind ?? undefined,
      domain: filters.domain ?? undefined,
      quantified: filters.quantified ? "1" : undefined,
      minConviction:
        filters.minConviction > 0 ? filters.minConviction.toString() : undefined,
      ...patch,
    };
    for (const [k, v] of Object.entries(current)) {
      if (v == null || v === "") continue;
      next.set(k, v);
    }
    const q = next.toString();
    return q ? `/principles?${q}` : "/principles";
  }

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main
        id="principles-main"
        className="public-container public-methodology-page"
        data-testid="principles-index"
      >
        <section className="public-section" aria-labelledby="principles-hero-title">
          <h1 id="principles-hero-title" className="public-title">
            Principles
          </h1>
          <p className="public-lede">
            Principles are the firm&apos;s reusable rules — what we use
            to judge new evidence. A claim becomes a principle when the
            same logic recurs across enough conclusions that we are
            willing to defend it, and to be held to it. Conclusions are
            evidence for or against a principle; claims are the raw
            source material that produced one.
          </p>
        </section>

        <section
          className="public-section"
          aria-labelledby="principles-filters-title"
          data-testid="principles-filters"
        >
          <h2
            id="principles-filters-title"
            className="mono"
            style={filterHeadingStyle}
          >
            Filter
          </h2>

          <div data-testid="filter-kind" style={filterGroupStyle}>
            <span style={filterLabelStyle}>kind</span>
            <FilterChip
              href={filterHref({ kind: undefined })}
              label="any"
              active={!filters.kind}
            />
            {PRINCIPLE_KINDS.map((k) => (
              <FilterChip
                key={k}
                href={filterHref({ kind: k })}
                label={k.toLowerCase()}
                active={filters.kind === k}
              />
            ))}
            <FilterChip
              href={filterHref({ kind: "UNSPECIFIED" })}
              label="unspecified"
              active={filters.kind === "UNSPECIFIED"}
            />
          </div>

          {domains.length > 0 ? (
            <div data-testid="filter-domain" style={filterGroupStyle}>
              <span style={filterLabelStyle}>domain</span>
              <FilterChip
                href={filterHref({ domain: undefined })}
                label="any"
                active={!filters.domain}
              />
              {domains.map((d) => (
                <FilterChip
                  key={d}
                  href={filterHref({ domain: d })}
                  label={d}
                  active={filters.domain === d}
                />
              ))}
            </div>
          ) : null}

          <div data-testid="filter-quantified" style={filterGroupStyle}>
            <span style={filterLabelStyle}>quantified</span>
            <FilterChip
              href={filterHref({ quantified: undefined })}
              label="any"
              active={!filters.quantified}
            />
            <FilterChip
              href={filterHref({ quantified: "1" })}
              label="approved formalisation"
              active={filters.quantified}
            />
          </div>

          <div data-testid="filter-conviction" style={filterGroupStyle}>
            <span style={filterLabelStyle}>min conviction</span>
            {[0, 0.25, 0.5, 0.75].map((threshold) => (
              <FilterChip
                key={threshold}
                href={filterHref({
                  minConviction: threshold > 0 ? threshold.toString() : undefined,
                })}
                label={threshold.toFixed(2)}
                active={Math.abs(filters.minConviction - threshold) < 1e-9}
              />
            ))}
          </div>
        </section>

        <section
          className="public-section"
          aria-labelledby="principles-list-title"
        >
          <h2 id="principles-list-title">
            {visible.length === 0
              ? "No principles match these filters"
              : `${visible.length} principle${visible.length === 1 ? "" : "s"}`}
          </h2>
          {visible.length === 0 ? (
            <p className="public-muted">
              {enriched.length === 0
                ? "No public principles yet. The firm has not promoted any candidate to public visibility."
                : "Loosen the filters above — particularly the kind or quantified filter — to see more rows."}
            </p>
          ) : (
            <ul
              data-testid="principles-list"
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "1rem",
              }}
            >
              {visible.map((p) => (
                <li
                  key={p.id}
                  className="public-card public-method-card"
                  style={{ padding: "1.1rem 1.3rem" }}
                  data-testid="principle-row"
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
                      href={`/principles/${p.id}`}
                      style={{
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "1.1rem",
                        lineHeight: 1.5,
                        color: "inherit",
                        textDecoration: "none",
                        flex: 1,
                      }}
                    >
                      {p.text}
                    </Link>
                    <span
                      className="mono"
                      title="Conviction (cross-domain convergence; conservative)"
                      style={{
                        fontSize: "0.7rem",
                        letterSpacing: "0.18em",
                        color: "var(--amber, #d4a017)",
                      }}
                    >
                      {p.convictionScore.toFixed(2)}
                    </span>
                  </div>
                  <div
                    className="mono"
                    style={{
                      marginTop: "0.55rem",
                      fontSize: "0.6rem",
                      letterSpacing: "0.22em",
                      textTransform: "uppercase",
                      color: "var(--public-muted, #888)",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "0.5rem",
                      alignItems: "center",
                    }}
                  >
                    <span
                      data-testid="principle-kind-badge"
                      style={{
                        padding: "0.18rem 0.55rem",
                        border: "1px solid var(--amber, #d4a017)",
                        color: "var(--amber, #d4a017)",
                      }}
                    >
                      {p.aggregatedKind.toLowerCase()}
                    </span>
                    {p.domains.map((d) => (
                      <span
                        key={d}
                        style={{
                          padding: "0.18rem 0.55rem",
                          border: "1px solid var(--public-muted, #888)",
                        }}
                      >
                        {d}
                      </span>
                    ))}
                    {p.hasApprovedFormalisation ? (
                      <span
                        data-testid="principle-quantified-badge"
                        style={{
                          padding: "0.18rem 0.55rem",
                          border: "1px solid rgba(160, 211, 170, 0.9)",
                          color: "rgba(160, 211, 170, 0.9)",
                        }}
                      >
                        quantified
                      </span>
                    ) : null}
                    <span>cluster · {p.clusterConclusionIds.length}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  );
}

function FilterChip({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      data-active={active ? "true" : undefined}
      style={{
        padding: "0.22rem 0.65rem",
        border: `1px solid ${active ? "var(--amber, #d4a017)" : "var(--public-muted, #888)"}`,
        color: active ? "var(--amber, #d4a017)" : "var(--public-muted, #888)",
        textDecoration: "none",
        fontSize: "0.58rem",
        letterSpacing: "0.18em",
        textTransform: "uppercase",
      }}
    >
      {label}
    </Link>
  );
}

const filterHeadingStyle: React.CSSProperties = {
  fontSize: "0.65rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--public-muted, #888)",
  margin: "0 0 0.65rem",
};

const filterGroupStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.4rem",
  alignItems: "center",
  marginBottom: "0.6rem",
};

const filterLabelStyle: React.CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontSize: "0.85rem",
  marginRight: "0.4rem",
  color: "var(--public-muted, #888)",
};

/**
 * Schema-lag-tolerant read of the Round-21 principle-shape columns on
 * `Conclusion`. The generated Prisma client may not include
 * `principleKind` yet on this branch; the schema does. Issuing a
 * `findMany` without `select`, then projecting in TS, lets us read the
 * column at runtime while keeping the file typecheck-clean. The cast
 * to `unknown` first satisfies the TS bridge between the generated
 * model row and the projection we actually consume.
 */
async function fetchPrincipleKinds(
  conclusionIds: string[],
): Promise<Array<{ id: string; principleKind: string | null }>> {
  const rows = (await db.conclusion.findMany({
    where: { id: { in: conclusionIds } },
  })) as unknown as Array<{ id: string; principleKind: string | null }>;
  return rows.map((r) => ({ id: r.id, principleKind: r.principleKind ?? null }));
}
