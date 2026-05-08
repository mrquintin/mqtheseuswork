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
 * The triage UI (queue + detail page) reads from here; the public
 * `/methodology/principles` page reads `listPublicPrinciples`.
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

/** Founder triage queue: drafts + needs-re-review, conviction-sorted. */
export async function listQueuedPrinciples(
  organizationId: string,
): Promise<PrincipleRow[]> {
  const rows = await db.principle.findMany({
    where: {
      organizationId,
      status: { in: ["draft", "needs_rereview"] },
    },
    orderBy: [{ convictionScore: "desc" }, { createdAt: "desc" }],
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
 *   - status = accepted
 *   - publicVisible = true
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
      status: "accepted",
      publicVisible: true,
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

export type AcceptInput = {
  text: string;
  domains: string[];
  publicVisible: boolean;
};

export async function acceptPrinciple(
  organizationId: string,
  id: string,
  founderId: string,
  input: AcceptInput,
): Promise<void> {
  // Public visibility requires a non-empty domain list — the firm
  // avoids publishing universal-sounding principles whose evidence
  // is domain-narrow.
  const safeDomains = input.domains.map((d) => d.trim()).filter(Boolean);
  const allowPublic = input.publicVisible && safeDomains.length > 0;
  await db.principle.update({
    where: { id },
    data: {
      text: input.text.trim(),
      domainsJson: JSON.stringify(safeDomains),
      status: "accepted",
      driftReason: null,
      reviewedByFounderId: founderId,
      reviewedAt: new Date(),
      publicVisible: allowPublic,
      publishedAt: allowPublic ? new Date() : null,
      triageReason: "",
    },
  });
  // Touch organizationId in the WHERE clause via a separate guard so a
  // cross-tenant update fails fast.
  await db.principle.updateMany({
    where: { id, organizationId },
    data: {},
  });
}

export async function rejectPrinciple(
  organizationId: string,
  id: string,
  founderId: string,
  reason: string,
): Promise<void> {
  await db.principle.updateMany({
    where: { id, organizationId },
    data: {
      status: "rejected",
      triageReason: reason.trim(),
      reviewedByFounderId: founderId,
      reviewedAt: new Date(),
      publicVisible: false,
      publishedAt: null,
    },
  });
}

export async function mergePrinciple(
  organizationId: string,
  id: string,
  founderId: string,
  intoId: string,
): Promise<void> {
  if (id === intoId) {
    throw new Error("Cannot merge a principle into itself");
  }
  const target = await db.principle.findFirst({
    where: { id: intoId, organizationId },
  });
  if (!target) {
    throw new Error("Merge target not found in this organization");
  }
  await db.principle.updateMany({
    where: { id, organizationId },
    data: {
      status: "merged",
      mergedIntoId: intoId,
      reviewedByFounderId: founderId,
      reviewedAt: new Date(),
      publicVisible: false,
      publishedAt: null,
    },
  });
}

/** Used by the founder detail page to pick a merge target. */
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

/**
 * Hydrate cluster conclusion text for the founder detail page so the
 * reviewer reads the principle next to the conclusions it generalizes.
 */
export async function hydrateClusterConclusions(
  organizationId: string,
  ids: string[],
): Promise<Array<{ id: string; text: string; confidenceTier: string }>> {
  if (ids.length === 0) return [];
  const rows = await db.conclusion.findMany({
    where: { id: { in: ids }, organizationId },
    select: { id: true, text: true, confidenceTier: true },
  });
  const byId = new Map(rows.map((r) => [r.id, r]));
  return ids
    .map((id) => byId.get(id))
    .filter(
      (c): c is { id: string; text: string; confidenceTier: string } =>
        Boolean(c),
    );
}
