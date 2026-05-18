import { db } from "@/lib/db";

/**
 * Read/write surface for the principle distillation feature.
 *
 * The Codex stores `Principle` rows produced by the noosphere
 * distillation pipeline (see noosphere/distillation/principle_distillation.py).
 * Each row carries:
 *
 *   - text                  → single-sentence claim the firm is willing to defend
 *   - domains               → JSON string[] of domain tags (public-visible
 *                              principles must declare ≥1 domain)
 *   - clusterConclusionIds  → JSON string[] of conclusions in the embedding-
 *                              space cluster that produced the principle
 *   - citedConclusionIds    → JSON string[] of conclusions the LLM explicitly
 *                              quoted when drafting
 *   - convictionScore       → conservative score in [0, 1]; convergence-across-
 *                              domains weighted, not single-conclusion centrality
 *   - status                → draft | accepted | rejected | merged | needs_rereview
 *   - publicVisible         → founder-flipped flag; the public methodology
 *                              surface filters on this column AND on a
 *                              non-empty domain list AND on status=accepted
 *
 * The authed read-only audit-log surfaces read `listRecentPrinciples`
 * here; the public `/methodology/principles` page reads
 * `listPublicPrinciples`. The accept/reject/merge helpers that backed
 * the now-decommissioned triage UI were removed on 2026-05-17 (cf.
 * `decommissioned_triage_uis_2026_05_17` in BUG_CATALOG.md).
 */

export type PrincipleStatus =
  | "draft"
  | "accepted"
  | "rejected"
  | "merged"
  | "needs_rereview";

export type PrincipleRow = {
  id: string;
  text: string;
  domains: string[];
  clusterConclusionIds: string[];
  citedConclusionIds: string[];
  status: PrincipleStatus;
  triageReason: string;
  mergedIntoId: string | null;
  convictionScore: number;
  domainBreadth: number;
  clusterCentroidSimilarity: number;
  publicVisible: boolean;
  driftReason: string | null;
  reviewedAt: Date | null;
  publishedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
};

export type PublicPrincipleRow = PrincipleRow & {
  underlyingConclusions: Array<{
    id: string;
    text: string;
    confidenceTier: string;
  }>;
};

function safeParseJsonStringArray(value: string): string[] {
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === "string");
  } catch {
    return [];
  }
}

function rowFromPrisma(p: {
  id: string;
  text: string;
  domainsJson: string;
  clusterConclusionIds: string;
  citedConclusionIds: string;
  status: string;
  triageReason: string;
  mergedIntoId: string | null;
  convictionScore: number;
  domainBreadth: number;
  clusterCentroidSimilarity: number;
  publicVisible: boolean;
  driftReason: string | null;
  reviewedAt: Date | null;
  publishedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}): PrincipleRow {
  return {
    id: p.id,
    text: p.text,
    domains: safeParseJsonStringArray(p.domainsJson),
    clusterConclusionIds: safeParseJsonStringArray(p.clusterConclusionIds),
    citedConclusionIds: safeParseJsonStringArray(p.citedConclusionIds),
    status: (p.status as PrincipleStatus) ?? "draft",
    triageReason: p.triageReason ?? "",
    mergedIntoId: p.mergedIntoId,
    convictionScore: p.convictionScore,
    domainBreadth: p.domainBreadth,
    clusterCentroidSimilarity: p.clusterCentroidSimilarity,
    publicVisible: p.publicVisible,
    driftReason: p.driftReason,
    reviewedAt: p.reviewedAt,
    publishedAt: p.publishedAt,
    createdAt: p.createdAt,
    updatedAt: p.updatedAt,
  };
}

/**
 * Read-only "Recent principles" log. Replaces the decommissioned
 * triage queue (auto-accept removed the gate; this surface is now
 * historical and not status-filtered).
 */
export async function listRecentPrinciples(
  organizationId: string,
  limit = 100,
): Promise<PrincipleRow[]> {
  const rows = await db.principle.findMany({
    where: { organizationId },
    orderBy: { createdAt: "desc" },
    take: limit,
  });
  return rows.map(rowFromPrisma);
}

export async function getPrinciple(
  organizationId: string,
  id: string,
): Promise<PrincipleRow | null> {
  const row = await db.principle.findFirst({
    where: { id, organizationId },
  });
  return row ? rowFromPrisma(row) : null;
}

/**
 * Public surface read.
 *
 * A principle is public-visible iff:
 *   - publicVisible = true
 *   - status != rejected (a positively-set rejection still hides the row)
 *   - domains is non-empty (constraint: declare your domain)
 *
 * Sorted by convictionScore desc — conviction-weighted ordering on the
 * public methodology page.
 *
 * If `organizationId` is omitted, returns public-visible principles
 * across all orgs (matches how the public methodology surfaces in
 * `methodologyManifest.ts` already read).
 */
export async function listPublicPrinciples(
  organizationId?: string,
): Promise<PublicPrincipleRow[]> {
  const rows = await db.principle.findMany({
    where: {
      ...(organizationId ? { organizationId } : {}),
      publicVisible: true,
      status: { not: "rejected" },
    },
    orderBy: [{ convictionScore: "desc" }, { publishedAt: "desc" }],
  });
  const filtered = rows
    .map(rowFromPrisma)
    .filter((r) => r.domains.length > 0);

  if (filtered.length === 0) return [];

  const allConclusionIds = Array.from(
    new Set(filtered.flatMap((r) => r.clusterConclusionIds)),
  );
  const conclusionRows = await db.conclusion.findMany({
    where: {
      id: { in: allConclusionIds },
      ...(organizationId ? { organizationId } : {}),
    },
    select: { id: true, text: true, confidenceTier: true },
  });
  const byId = new Map(conclusionRows.map((c) => [c.id, c]));

  return filtered.map((r) => ({
    ...r,
    underlyingConclusions: r.clusterConclusionIds
      .map((cid) => byId.get(cid))
      .filter(
        (c): c is { id: string; text: string; confidenceTier: string } =>
          Boolean(c),
      ),
  }));
}

// Founder accept/reject/merge handlers were removed on 2026-05-17 when
// the principle triage UI was decommissioned (drafts auto-accept on
// extraction; cf. `auto_accept_principles_2026_05_17`). The `status`,
// `reviewedAt`, and `publishedAt` columns remain on the schema so a
// future operator surface can be reintroduced without a migration.

/**
 * Accepted principles for the dashboard / knowledge tab — the public
 * surface ordering and read-only listings depend on this query.
 */
export async function listAcceptedPrinciples(
  organizationId: string,
  excludeId?: string,
): Promise<PrincipleRow[]> {
  const rows = await db.principle.findMany({
    where: {
      organizationId,
      status: "accepted",
      ...(excludeId ? { NOT: { id: excludeId } } : {}),
    },
    orderBy: [{ convictionScore: "desc" }],
    take: 50,
  });
  return rows.map(rowFromPrisma);
}

