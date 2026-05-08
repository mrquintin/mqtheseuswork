/**
 * Open-critique API helpers (challenge-this surface).
 *
 * The codex captures structured critiques of specific firm conclusions
 * in `CritiqueSubmission`. They land in a moderation queue distinct
 * from the general `PublicResponse` inbox so invited expert critique
 * does not get diluted by general traffic.
 *
 * Moderation states form an explicit ladder:
 *   pending → accepted   (publish + credit + maybe queue bounty)
 *   pending → partial    (private discussion; not published)
 *   pending → rejected   (with a reason, surfaced to the critic)
 *   any     → archived   (audit-only)
 *
 * Bounty rules (mirrored on the public /critiques page so submitters
 * know what counts):
 *   - Only `accepted` critiques whose severity label is `high` are
 *     bounty-eligible.
 *   - The default bounty is 500 USD; configurable per submission
 *     before founder confirmation.
 *   - The codex never sends money. Confirmation flips the queued row
 *     to `confirmed`; the firm's existing payouts pipeline is the
 *     actual sender.
 */

import { db } from "@/lib/db";

export const CRITIQUE_STATUSES = [
  "pending",
  "accepted",
  "partial",
  "rejected",
  "archived",
] as const;
export type CritiqueStatus = (typeof CRITIQUE_STATUSES)[number];

export const SEVERITY_LABELS = ["", "low", "medium", "high"] as const;
export type CritiqueSeverityLabel = (typeof SEVERITY_LABELS)[number];

export const BOUNTY_PAYOUT_MODES = ["self", "charity"] as const;
export type BountyPayoutMode = (typeof BOUNTY_PAYOUT_MODES)[number];

export const BOUNTY_STATUSES = [
  "pending_founder_confirmation",
  "confirmed",
  "cancelled",
] as const;
export type BountyStatus = (typeof BOUNTY_STATUSES)[number];

export const DEFAULT_BOUNTY_USD = 500;

/** Minimum lengths for the structured critique fields. */
export const MIN_TARGET_CLAIM = 12;
export const MIN_COUNTER_EVIDENCE = 40;
export const MIN_DERIVATION = 20;

export type CreateCritiqueInput = {
  organizationId: string;
  articleSlug: string;
  publishedConclusionId?: string | null;
  targetClaim: string;
  counterEvidence: string;
  derivationMethod: string;
  citations?: string;
  submitterEmail: string;
  displayName?: string;
  publicUrl?: string;
  bio?: string;
  orcid?: string;
};

export type CritiqueRecord = {
  id: string;
  organizationId: string;
  articleSlug: string;
  publishedConclusionId: string | null;
  targetClaim: string;
  counterEvidence: string;
  derivationMethod: string;
  citations: string;
  submitterEmail: string;
  displayName: string;
  publicUrl: string;
  bio: string;
  orcid: string;
  status: CritiqueStatus;
  moderatorNote: string;
  severityLabel: CritiqueSeverityLabel;
  severityValue: number;
  decidedById: string | null;
  decidedAt: Date | null;
  triggeredRevisionId: string | null;
  addendumId: string | null;
  createdAt: Date;
  updatedAt: Date;
};

export type CritiqueWithBounty = CritiqueRecord & {
  bounty: BountyRecord | null;
};

export type BountyRecord = {
  id: string;
  critiqueSubmissionId: string;
  amountUsd: number;
  payoutMode: BountyPayoutMode;
  destination: string;
  status: BountyStatus;
  cancellationNote: string;
  confirmedById: string | null;
  confirmedAt: Date | null;
  externalRef: string;
  createdAt: Date;
  updatedAt: Date;
};

type RawCritiqueRow = {
  id: string;
  organizationId: string;
  articleSlug: string;
  publishedConclusionId: string | null;
  targetClaim: string;
  counterEvidence: string;
  derivationMethod: string;
  citations: string;
  submitterEmail: string;
  displayName: string;
  publicUrl: string;
  bio: string;
  orcid: string;
  status: string;
  moderatorNote: string;
  severityLabel: string;
  severityValue: number;
  decidedById: string | null;
  decidedAt: Date | null;
  triggeredRevisionId: string | null;
  addendumId: string | null;
  createdAt: Date;
  updatedAt: Date;
};

type RawBountyRow = {
  id: string;
  critiqueSubmissionId: string;
  amountUsd: number;
  payoutMode: string;
  destination: string;
  status: string;
  cancellationNote: string;
  confirmedById: string | null;
  confirmedAt: Date | null;
  externalRef: string;
  createdAt: Date;
  updatedAt: Date;
};

function toCritique(row: RawCritiqueRow): CritiqueRecord {
  return {
    ...row,
    status: (CRITIQUE_STATUSES as readonly string[]).includes(row.status)
      ? (row.status as CritiqueStatus)
      : "pending",
    severityLabel: (SEVERITY_LABELS as readonly string[]).includes(row.severityLabel)
      ? (row.severityLabel as CritiqueSeverityLabel)
      : "",
  };
}

function toBounty(row: RawBountyRow): BountyRecord {
  return {
    ...row,
    payoutMode: (BOUNTY_PAYOUT_MODES as readonly string[]).includes(row.payoutMode)
      ? (row.payoutMode as BountyPayoutMode)
      : "self",
    status: (BOUNTY_STATUSES as readonly string[]).includes(row.status)
      ? (row.status as BountyStatus)
      : "pending_founder_confirmation",
  };
}

/**
 * Persist a fresh critique submission. Validates required fields and
 * minimum lengths; throws on malformed input so the API route can
 * translate the message to the critic.
 */
export async function createCritique(input: CreateCritiqueInput): Promise<CritiqueRecord> {
  const targetClaim = (input.targetClaim || "").trim();
  const counterEvidence = (input.counterEvidence || "").trim();
  const derivationMethod = (input.derivationMethod || "").trim();
  const submitterEmail = (input.submitterEmail || "").trim();

  if (targetClaim.length < MIN_TARGET_CLAIM) {
    throw new Error(`targetClaim must be at least ${MIN_TARGET_CLAIM} characters`);
  }
  if (counterEvidence.length < MIN_COUNTER_EVIDENCE) {
    throw new Error(`counterEvidence must be at least ${MIN_COUNTER_EVIDENCE} characters`);
  }
  if (derivationMethod.length < MIN_DERIVATION) {
    throw new Error(`derivationMethod must be at least ${MIN_DERIVATION} characters`);
  }
  if (!submitterEmail.includes("@")) {
    throw new Error("submitterEmail is required");
  }
  if (!input.articleSlug.trim()) {
    throw new Error("articleSlug is required");
  }

  const row = (await db.critiqueSubmission.create({
    data: {
      organizationId: input.organizationId,
      articleSlug: input.articleSlug.trim(),
      publishedConclusionId: input.publishedConclusionId ?? null,
      targetClaim,
      counterEvidence,
      derivationMethod,
      citations: (input.citations ?? "").trim(),
      submitterEmail,
      displayName: (input.displayName ?? "").trim(),
      publicUrl: (input.publicUrl ?? "").trim(),
      bio: (input.bio ?? "").trim(),
      orcid: (input.orcid ?? "").trim(),
      status: "pending",
    },
  })) as RawCritiqueRow;
  return toCritique(row);
}

/** Founder queue: every non-archived critique for a tenant. */
export async function listCritiqueQueue(organizationId: string): Promise<CritiqueWithBounty[]> {
  const rows = (await db.critiqueSubmission.findMany({
    where: { organizationId, status: { not: "archived" } },
    orderBy: [{ severityValue: "desc" }, { createdAt: "desc" }],
    include: { bounty: true },
  })) as Array<RawCritiqueRow & { bounty: RawBountyRow | null }>;
  return rows.map((r) => ({
    ...toCritique(r),
    bounty: r.bounty ? toBounty(r.bounty) : null,
  }));
}

/** Single critique for the detail view. */
export async function getCritique(
  organizationId: string,
  id: string,
): Promise<CritiqueWithBounty | null> {
  const row = (await db.critiqueSubmission.findFirst({
    where: { id, organizationId },
    include: { bounty: true },
  })) as (RawCritiqueRow & { bounty: RawBountyRow | null }) | null;
  if (!row) return null;
  return { ...toCritique(row), bounty: row.bounty ? toBounty(row.bounty) : null };
}

/** Public hall-of-fame: accepted critiques only. */
export async function listAcceptedCritiques(): Promise<CritiqueRecord[]> {
  const rows = (await db.critiqueSubmission.findMany({
    where: { status: "accepted" },
    orderBy: { decidedAt: "desc" },
  })) as RawCritiqueRow[];
  return rows.map(toCritique);
}

/** Accepted critiques for a single article (rendered alongside the post). */
export async function listAcceptedCritiquesForArticle(
  articleSlug: string,
): Promise<CritiqueRecord[]> {
  const rows = (await db.critiqueSubmission.findMany({
    where: { articleSlug, status: "accepted" },
    orderBy: { decidedAt: "desc" },
  })) as RawCritiqueRow[];
  return rows.map(toCritique);
}

export type AcceptCritiqueInput = {
  organizationId: string;
  critiqueId: string;
  founderId: string;
  severityLabel: CritiqueSeverityLabel;
  severityValue: number;
  moderatorNote?: string;
  /** When set true and severity is "high", queue a bounty payout row. */
  queueBounty?: boolean;
  bountyAmountUsd?: number;
  bountyPayoutMode?: BountyPayoutMode;
  bountyDestination?: string;
};

/**
 * Mark a critique accepted. If `queueBounty` is true and the severity
 * label is `high`, also creates a `CritiqueBountyPayout` in the
 * `pending_founder_confirmation` state. The bounty row is *queued*,
 * not paid; payment requires a separate explicit
 * `confirmBountyPayout` call.
 */
export async function acceptCritique(input: AcceptCritiqueInput): Promise<CritiqueWithBounty> {
  const updated = (await db.critiqueSubmission.update({
    where: { id: input.critiqueId },
    data: {
      status: "accepted",
      severityLabel: input.severityLabel,
      severityValue: Math.max(0, Math.min(1, input.severityValue)),
      moderatorNote: (input.moderatorNote ?? "").trim(),
      decidedById: input.founderId,
      decidedAt: new Date(),
    },
  })) as RawCritiqueRow;

  let bounty: BountyRecord | null = null;
  if (input.queueBounty && input.severityLabel === "high") {
    const row = (await db.critiqueBountyPayout.upsert({
      where: { critiqueSubmissionId: input.critiqueId },
      create: {
        organizationId: input.organizationId,
        critiqueSubmissionId: input.critiqueId,
        amountUsd: clampAmount(input.bountyAmountUsd ?? DEFAULT_BOUNTY_USD),
        payoutMode: input.bountyPayoutMode ?? "self",
        destination: (input.bountyDestination ?? "").trim(),
        status: "pending_founder_confirmation",
      },
      update: {
        amountUsd: clampAmount(input.bountyAmountUsd ?? DEFAULT_BOUNTY_USD),
        payoutMode: input.bountyPayoutMode ?? "self",
        destination: (input.bountyDestination ?? "").trim(),
        status: "pending_founder_confirmation",
        cancellationNote: "",
      },
    })) as RawBountyRow;
    bounty = toBounty(row);
  }

  return { ...toCritique(updated), bounty };
}

export type DecideCritiqueInput = {
  organizationId: string;
  critiqueId: string;
  founderId: string;
  status: "partial" | "rejected" | "archived";
  moderatorNote?: string;
};

export async function decideCritique(input: DecideCritiqueInput): Promise<CritiqueRecord> {
  const updated = (await db.critiqueSubmission.update({
    where: { id: input.critiqueId },
    data: {
      status: input.status,
      moderatorNote: (input.moderatorNote ?? "").trim(),
      decidedById: input.founderId,
      decidedAt: new Date(),
    },
  })) as RawCritiqueRow;
  return toCritique(updated);
}

export async function attachRevisionToCritique(
  organizationId: string,
  critiqueId: string,
  revisionEventId: string,
): Promise<void> {
  await db.critiqueSubmission.updateMany({
    where: { id: critiqueId, organizationId },
    data: { triggeredRevisionId: revisionEventId },
  });
}

export async function attachAddendumToCritique(
  organizationId: string,
  critiqueId: string,
  addendumId: string,
): Promise<void> {
  await db.critiqueSubmission.updateMany({
    where: { id: critiqueId, organizationId },
    data: { addendumId },
  });
}

export type ConfirmBountyInput = {
  organizationId: string;
  critiqueId: string;
  founderId: string;
  externalRef?: string;
};

/**
 * Confirm a queued bounty payout. This is the ONLY function that
 * flips a bounty out of `pending_founder_confirmation`; every other
 * code path leaves the bounty queued. The codex still does not send
 * money — this only marks the row eligible for the external payouts
 * pipeline to pick up.
 *
 * Throws if the critique is not accepted, severity is not high, or
 * the bounty is already confirmed or cancelled.
 */
export async function confirmBountyPayout(input: ConfirmBountyInput): Promise<BountyRecord> {
  const critique = await getCritique(input.organizationId, input.critiqueId);
  if (!critique) throw new Error("Unknown critique submission");
  if (critique.status !== "accepted") {
    throw new Error("Bounty can only be confirmed for accepted critiques");
  }
  if (critique.severityLabel !== "high") {
    throw new Error("Bounty is gated on high-severity acceptance");
  }
  if (!critique.bounty) {
    throw new Error("No queued bounty for this critique");
  }
  if (critique.bounty.status !== "pending_founder_confirmation") {
    throw new Error(`Bounty is already ${critique.bounty.status}`);
  }

  const updated = (await db.critiqueBountyPayout.update({
    where: { id: critique.bounty.id },
    data: {
      status: "confirmed",
      confirmedById: input.founderId,
      confirmedAt: new Date(),
      externalRef: (input.externalRef ?? "").trim(),
    },
  })) as RawBountyRow;
  return toBounty(updated);
}

export async function cancelBountyPayout(
  organizationId: string,
  critiqueId: string,
  cancellationNote: string,
): Promise<BountyRecord | null> {
  const critique = await getCritique(organizationId, critiqueId);
  if (!critique?.bounty) return null;
  if (critique.bounty.status === "confirmed") {
    throw new Error("Confirmed bounties cannot be cancelled in the codex");
  }
  const updated = (await db.critiqueBountyPayout.update({
    where: { id: critique.bounty.id },
    data: { status: "cancelled", cancellationNote: cancellationNote.trim() },
  })) as RawBountyRow;
  return toBounty(updated);
}

function clampAmount(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_BOUNTY_USD;
  return Math.max(0, Math.min(100_000, Math.round(value)));
}

/**
 * Public-facing display attribution. Pseudonymous critics fall back to
 * "Anonymous" when no displayName is set; non-pseudonymous critics
 * show the email localpart only (the domain is suppressed so a
 * poster's affiliation does not leak through the credit line).
 */
export function critiqueDisplayName(row: CritiqueRecord): string {
  if (row.displayName.trim()) return row.displayName.trim();
  if (!row.submitterEmail) return "Anonymous";
  const at = row.submitterEmail.indexOf("@");
  if (at <= 0) return "Anonymous";
  return row.submitterEmail.slice(0, at);
}
