import type { Metadata } from "next";
import Link from "next/link";

import AlgorithmCard from "@/components/algorithms/AlgorithmCard";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import {
  calibrationSeries,
  listInvocationsForAlgorithm,
  listPublicAlgorithms,
  type PublicAlgorithmRow,
  type PublicAlgorithmStatus,
  type PublicCalibrationPoint,
} from "@/lib/algorithmsPublicApi";

/**
 * /algorithms — the public surface where founders, investors, and
 * curious visitors see the firm's logical algorithms at work.
 *
 * The page answers four questions in five seconds: what is running,
 * what did each one predict most recently, which principles do they
 * rest on, and what bets (if any) they imply. Cards are sorted by
 * recent activity by default; sort + filter controls expose the rest
 * of the surface.
 */

export const metadata: Metadata = {
  title: "Algorithms · Theseus",
  description:
    "Theseus runs logical algorithms — functions derived from the firm's principles, applied to live observations of the world. Each one predicts an output and is graded when reality catches up.",
  openGraph: {
    title: "Theseus · algorithms",
    description: "The firm thinking in public: every algorithm, every principle, every fire.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

type AlgorithmsIndexSearchParams = {
  status?: string;
  domain?: string;
  principle?: string;
  sort?: string;
};

const SORT_OPTIONS = ["recent", "hit_rate", "name"] as const;
type SortKey = (typeof SORT_OPTIONS)[number];

function parseStatus(raw: string | undefined): PublicAlgorithmStatus | "ALL" {
  if (raw === "ALL") return "ALL";
  if (raw === "ACTIVE" || raw === "PAUSED" || raw === "RETIRED") return raw;
  return "ACTIVE";
}

function parseSort(raw: string | undefined): SortKey {
  if (raw && (SORT_OPTIONS as ReadonlyArray<string>).includes(raw)) return raw as SortKey;
  return "recent";
}

function sortAlgorithms(rows: PublicAlgorithmRow[], sort: SortKey): PublicAlgorithmRow[] {
  const copy = [...rows];
  if (sort === "recent") {
    copy.sort((a, b) => {
      const aT = a.latestInvocationAt?.getTime() ?? 0;
      const bT = b.latestInvocationAt?.getTime() ?? 0;
      return bT - aT;
    });
  } else if (sort === "hit_rate") {
    copy.sort((a, b) => {
      const aR = a.hitRate.ratio ?? -1;
      const bR = b.hitRate.ratio ?? -1;
      if (aR === bR) return b.hitRate.n - a.hitRate.n;
      return bR - aR;
    });
  } else if (sort === "name") {
    copy.sort((a, b) => a.name.localeCompare(b.name));
  }
  return copy;
}

function uniqueDomainsFromOutputs(rows: PublicAlgorithmRow[]): string[] {
  // Domains aren't a first-class field on LogicalAlgorithm; the closest
  // facet the public surface has is the source-principle id list. The
  // filter chip is reserved here as a forward-compatible slot — when a
  // principle->domain materialised view lands the page will derive the
  // domain set from the join. For now we expose the output-type as a
  // proxy facet so the chip strip is not empty.
  const set = new Set<string>();
  for (const row of rows) {
    if (row.output?.type) set.add(row.output.type);
  }
  return [...set].sort();
}

function filterHrefBuilder(current: AlgorithmsIndexSearchParams) {
  return function build(patch: Partial<AlgorithmsIndexSearchParams>): string {
    const next = new URLSearchParams();
    const merged: Record<string, string | undefined> = { ...current, ...patch };
    for (const [k, v] of Object.entries(merged)) {
      if (v == null || v === "") continue;
      next.set(k, v);
    }
    const q = next.toString();
    return q ? `/algorithms?${q}` : "/algorithms";
  };
}

export default async function AlgorithmsIndexPage({
  searchParams,
}: {
  searchParams?: Promise<AlgorithmsIndexSearchParams>;
}) {
  const sp = (await searchParams) ?? {};
  const founder = await getFounder().catch(() => null);
  const organizationId =
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    "";

  const status = parseStatus(sp.status);
  const sort = parseSort(sp.sort);

  const algorithms = organizationId
    ? await listPublicAlgorithms(organizationId, {
        status,
        sourcePrincipleId: sp.principle ?? null,
      })
    : [];

  // Filter by output-type proxy domain on the surface side so the
  // loader stays generic.
  const visible = sp.domain
    ? algorithms.filter((a) => a.output.type === sp.domain)
    : algorithms;
  const sorted = sortAlgorithms(visible, sort);
  const domains = uniqueDomainsFromOutputs(algorithms);
  const sourcePrincipleIds = Array.from(
    new Set(algorithms.flatMap((a) => a.sourcePrincipleIds)),
  ).slice(0, 12);

  const calibrationByAlgorithm = new Map<string, PublicCalibrationPoint[]>();
  for (const a of sorted) {
    if (a.invocationCount === 0) continue;
    const all = await listInvocationsForAlgorithm(a.id, 500);
    calibrationByAlgorithm.set(a.id, calibrationSeries(all));
  }

  const buildHref = filterHrefBuilder(sp);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main
        id="algorithms-main"
        className="public-container public-methodology-page"
        data-testid="algorithms-index"
      >
        <section className="public-section" aria-labelledby="algorithms-hero-title">
          <h1 id="algorithms-hero-title" className="public-title">
            Algorithms
          </h1>
          <p className="public-lede">
            Theseus runs {algorithms.length} algorithm
            {algorithms.length === 1 ? "" : "s"} — logical functions derived
            from our principles, applied to live observations of the world.
            Each one predicts an output and is graded when reality catches up.
            This is the firm thinking in public.
          </p>
        </section>

        <section
          className="public-section"
          aria-labelledby="algorithms-filters-title"
          data-testid="algorithms-filters"
        >
          <h2 id="algorithms-filters-title" className="mono" style={filterHeadingStyle}>
            Filter
          </h2>

          <div data-testid="filter-status" style={filterGroupStyle}>
            <span style={filterLabelStyle}>status</span>
            <FilterChip
              href={buildHref({ status: undefined })}
              label="active"
              active={status === "ACTIVE"}
            />
            <FilterChip
              href={buildHref({ status: "ALL" })}
              label="show retired"
              active={status === "ALL"}
            />
            <FilterChip
              href={buildHref({ status: "PAUSED" })}
              label="paused"
              active={status === "PAUSED"}
            />
          </div>

          {domains.length > 0 ? (
            <div data-testid="filter-domain" style={filterGroupStyle}>
              <span style={filterLabelStyle}>output type</span>
              <FilterChip
                href={buildHref({ domain: undefined })}
                label="any"
                active={!sp.domain}
              />
              {domains.map((d) => (
                <FilterChip
                  key={d}
                  href={buildHref({ domain: d })}
                  label={d.toLowerCase()}
                  active={sp.domain === d}
                />
              ))}
            </div>
          ) : null}

          {sourcePrincipleIds.length > 0 ? (
            <div data-testid="filter-principle" style={filterGroupStyle}>
              <span style={filterLabelStyle}>source principle</span>
              <FilterChip
                href={buildHref({ principle: undefined })}
                label="any"
                active={!sp.principle}
              />
              {sourcePrincipleIds.map((pid) => (
                <FilterChip
                  key={pid}
                  href={buildHref({ principle: pid })}
                  label={pid.slice(0, 10)}
                  active={sp.principle === pid}
                />
              ))}
            </div>
          ) : null}

          <div data-testid="filter-sort" style={filterGroupStyle}>
            <span style={filterLabelStyle}>sort</span>
            <FilterChip
              href={buildHref({ sort: undefined })}
              label="recent activity"
              active={sort === "recent"}
            />
            <FilterChip
              href={buildHref({ sort: "hit_rate" })}
              label="hit rate"
              active={sort === "hit_rate"}
            />
            <FilterChip
              href={buildHref({ sort: "name" })}
              label="name"
              active={sort === "name"}
            />
          </div>
        </section>

        <section className="public-section" aria-labelledby="algorithms-list-title">
          <h2 id="algorithms-list-title">
            {sorted.length === 0
              ? "No algorithms match these filters"
              : `${sorted.length} algorithm${sorted.length === 1 ? "" : "s"}`}
          </h2>
          {sorted.length === 0 ? (
            <p className="public-muted">
              {algorithms.length === 0
                ? "No public algorithms yet. The firm has not promoted any candidate to ACTIVE."
                : "Loosen the filters above to see more rows."}
            </p>
          ) : (
            <ul
              data-testid="algorithm-cards"
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "1.25rem",
              }}
            >
              {sorted.map((a) => (
                <li key={a.id}>
                  <AlgorithmCard
                    algorithm={a}
                    calibration={calibrationByAlgorithm.get(a.id) ?? []}
                  />
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
