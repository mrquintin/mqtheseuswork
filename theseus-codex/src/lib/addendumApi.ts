import { db } from "@/lib/db";
import type { TenantContext } from "@/lib/tenant";

/**
 * Self-critique addendum API.
 *
 * The quarterly self-critique pass (see
 * `noosphere/peer_review/self_critique.py` and
 * `noosphere/peer_review/scheduler_self_critique.py`) lands findings in
 * the founder review queue. When the founder picks the `addend`
 * action, that finding becomes a row in this table — initially in
 * `pending` state, transitioning to `published` (visible to the
 * public) or `dismissed` (operator-only, with a reason on record).
 *
 * The original article body is *never* mutated by this path: an
 * addendum is rendered as visibly later content under the article,
 * not as an inline rewrite. Only the revision engine (prompt 16)
 * edits original prose.
 */

export type AddendumStatus = "pending" | "published" | "dismissed";

export type AddendumRecord = {
  id: string;
  articleSlug: string;
  noosphereArticleId: string | null;
  findingId: string;
  summary: string;
  body: string;
  status: AddendumStatus;
  reviewerConfig: string;
  createdAt: Date;
  publishedAt: Date | null;
  dismissedAt: Date | null;
  dismissedReason: string;
};

export type CreateAddendumInput = {
  articleSlug: string;
  summary: string;
  body?: string;
  noosphereArticleId?: string | null;
  findingId?: string;
  reviewerConfig?: string;
};

const ADDENDUM_SELECT = {
  id: true,
  articleSlug: true,
  noosphereArticleId: true,
  findingId: true,
  summary: true,
  body: true,
  status: true,
  reviewerConfig: true,
  createdAt: true,
  publishedAt: true,
  dismissedAt: true,
  dismissedReason: true,
} as const;

function toRecord(row: {
  id: string;
  articleSlug: string;
  noosphereArticleId: string | null;
  findingId: string;
  summary: string;
  body: string;
  status: string;
  reviewerConfig: string;
  createdAt: Date;
  publishedAt: Date | null;
  dismissedAt: Date | null;
  dismissedReason: string;
}): AddendumRecord {
  return {
    ...row,
    status: row.status as AddendumStatus,
  };
}

/**
 * List the published addenda for a public article slug, oldest-first.
 *
 * "Oldest first" matches the public-page rendering order: the first
 * addendum the firm published is shown above subsequent ones, the
 * same way a printed errata sheet would read top-to-bottom.
 *
 * Failure-mode behaviour: any query error returns an empty list so a
 * missing migration in dev does not 500 the public article page.
 */
export async function listPublishedAddenda(
  slug: string,
): Promise<AddendumRecord[]> {
  try {
    const rows = await db.addendum.findMany({
      where: {
        articleSlug: slug,
        status: "published",
        publishedAt: { not: null },
      },
      orderBy: { publishedAt: "asc" },
      select: ADDENDUM_SELECT,
    });
    return rows.map(toRecord);
  } catch (err) {
    console.error("[addendum] listPublishedAddenda failed:", err);
    return [];
  }
}

/**
 * List all addenda (any status) for a slug — used by the operator
 * triage UI, never by the public page.
 */
export async function listAddendaForOperator(
  tenant: TenantContext,
  slug: string,
): Promise<AddendumRecord[]> {
  const rows = await db.addendum.findMany({
    where: {
      organizationId: tenant.organizationId,
      articleSlug: slug,
    },
    orderBy: { createdAt: "desc" },
    select: ADDENDUM_SELECT,
  });
  return rows.map(toRecord);
}

/**
 * Create a pending addendum from a triaged self-critique finding.
 *
 * The caller is the founder triage flow (after they pick "addend" on
 * an attention-queue item). The created row is `pending` until they
 * publish or dismiss it.
 */
export async function createPendingAddendum(
  tenant: TenantContext,
  input: CreateAddendumInput,
): Promise<AddendumRecord> {
  const summary = input.summary.trim();
  if (!summary) {
    throw new Error("createPendingAddendum: summary is required");
  }
  const row = await db.addendum.create({
    data: {
      organizationId: tenant.organizationId,
      articleSlug: input.articleSlug,
      noosphereArticleId: input.noosphereArticleId ?? null,
      findingId: input.findingId ?? "",
      summary,
      body: input.body ?? "",
      status: "pending",
      reviewerConfig: input.reviewerConfig ?? "",
    },
    select: ADDENDUM_SELECT,
  });
  return toRecord(row);
}

/**
 * Transition a pending addendum to `published`. Idempotent on a row
 * that is already published (returns the existing record); refuses to
 * resurrect a dismissed addendum.
 */
export async function publishAddendum(
  tenant: TenantContext,
  id: string,
  now: Date = new Date(),
): Promise<AddendumRecord> {
  const existing = await db.addendum.findFirst({
    where: { id, organizationId: tenant.organizationId },
    select: ADDENDUM_SELECT,
  });
  if (!existing) {
    throw new Error(`publishAddendum: addendum ${id} not found`);
  }
  if (existing.status === "published") {
    return toRecord(existing);
  }
  if (existing.status === "dismissed") {
    throw new Error(
      `publishAddendum: addendum ${id} was dismissed and cannot be republished`,
    );
  }
  const updated = await db.addendum.update({
    where: { id },
    data: { status: "published", publishedAt: now },
    select: ADDENDUM_SELECT,
  });
  return toRecord(updated);
}

/**
 * Transition a pending addendum to `dismissed`. Refuses to dismiss an
 * already-published addendum (those need a separate retraction flow);
 * requires a non-empty reason so the audit trail is always actionable.
 */
export async function dismissAddendum(
  tenant: TenantContext,
  id: string,
  reason: string,
  now: Date = new Date(),
): Promise<AddendumRecord> {
  const cleanedReason = reason.trim();
  if (!cleanedReason) {
    throw new Error("dismissAddendum: reason is required");
  }
  const existing = await db.addendum.findFirst({
    where: { id, organizationId: tenant.organizationId },
    select: ADDENDUM_SELECT,
  });
  if (!existing) {
    throw new Error(`dismissAddendum: addendum ${id} not found`);
  }
  if (existing.status === "dismissed") {
    return toRecord(existing);
  }
  if (existing.status === "published") {
    throw new Error(
      `dismissAddendum: addendum ${id} is already published; use a retraction instead`,
    );
  }
  const updated = await db.addendum.update({
    where: { id },
    data: {
      status: "dismissed",
      dismissedAt: now,
      dismissedReason: cleanedReason,
    },
    select: ADDENDUM_SELECT,
  });
  return toRecord(updated);
}

/**
 * Format an addendum's published date in the firm's house style
 * ("On May 8, 2026 the firm re-reviewed this article…"). Exposed so
 * the rendering components and any future RSS/email surfaces share
 * the same phrasing.
 */
export function formatAddendumDate(date: Date): string {
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}
