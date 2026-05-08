"use server";

/**
 * Server actions for the critiques moderation workspace.
 *
 * These actions are the *only* code paths that flip a critique's
 * status or queue/confirm a bounty. They mirror the helpers in
 * `src/lib/critiquesApi.ts` and route them through tenancy + form
 * inputs.
 *
 * Bounty rule: confirmation is its own action, never bundled with
 * acceptance, so the founder always opts in twice (accept → confirm).
 */

import { revalidatePath } from "next/cache";

import { db } from "@/lib/db";
import {
  acceptCritique,
  attachAddendumToCritique,
  attachRevisionToCritique,
  cancelBountyPayout,
  confirmBountyPayout,
  decideCritique,
  type BountyPayoutMode,
  type CritiqueSeverityLabel,
} from "@/lib/critiquesApi";
import { requireTenantContext } from "@/lib/tenant";

const QUEUE_PATH = "/critiques/queue";
const PUBLIC_PATH = "/critiques";

function field(form: FormData, name: string): string {
  const v = form.get(name);
  return typeof v === "string" ? v : "";
}

function severityLabelFromForm(form: FormData): CritiqueSeverityLabel {
  const raw = field(form, "severityLabel").trim();
  if (raw === "low" || raw === "medium" || raw === "high") return raw;
  return "";
}

function payoutModeFromForm(form: FormData): BountyPayoutMode {
  const raw = field(form, "bountyPayoutMode").trim();
  return raw === "charity" ? "charity" : "self";
}

export async function acceptCritiqueAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const critiqueId = field(formData, "critiqueId");
  if (!critiqueId) throw new Error("critiqueId is required.");
  const severityLabel = severityLabelFromForm(formData);
  if (!severityLabel) throw new Error("severityLabel is required (low | medium | high).");
  const severityValue = Number(field(formData, "severityValue") || "0");
  const queueBounty = field(formData, "queueBounty") === "1";

  const amountRaw = field(formData, "bountyAmountUsd").trim();
  const bountyAmountUsd = amountRaw ? Number(amountRaw) : undefined;

  await acceptCritique({
    organizationId: tenant.organizationId,
    critiqueId,
    founderId: tenant.founderId,
    severityLabel,
    severityValue: Number.isFinite(severityValue) ? severityValue : 0,
    moderatorNote: field(formData, "moderatorNote"),
    queueBounty,
    bountyAmountUsd,
    bountyPayoutMode: payoutModeFromForm(formData),
    bountyDestination: field(formData, "bountyDestination"),
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
  revalidatePath(PUBLIC_PATH);
}

export async function partialCritiqueAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  const critiqueId = field(formData, "critiqueId");
  if (!critiqueId) throw new Error("critiqueId is required.");

  await decideCritique({
    organizationId: tenant.organizationId,
    critiqueId,
    founderId: tenant.founderId,
    status: "partial",
    moderatorNote: field(formData, "moderatorNote"),
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
}

export async function rejectCritiqueAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  const critiqueId = field(formData, "critiqueId");
  if (!critiqueId) throw new Error("critiqueId is required.");

  await decideCritique({
    organizationId: tenant.organizationId,
    critiqueId,
    founderId: tenant.founderId,
    status: "rejected",
    moderatorNote: field(formData, "moderatorNote"),
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
}

export async function archiveCritiqueAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  const critiqueId = field(formData, "critiqueId");
  if (!critiqueId) throw new Error("critiqueId is required.");

  await decideCritique({
    organizationId: tenant.organizationId,
    critiqueId,
    founderId: tenant.founderId,
    status: "archived",
    moderatorNote: field(formData, "moderatorNote"),
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
}

/**
 * Confirm a queued bounty payout. Distinct from acceptance so the
 * founder must consent twice — accepting the critique queues the
 * payout, confirming releases it to the firm's payouts pipeline. The
 * codex still does not send money.
 */
export async function confirmBountyAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  const critiqueId = field(formData, "critiqueId");
  if (!critiqueId) throw new Error("critiqueId is required.");

  await confirmBountyPayout({
    organizationId: tenant.organizationId,
    critiqueId,
    founderId: tenant.founderId,
    externalRef: field(formData, "externalRef"),
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
}

export async function cancelBountyAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  const critiqueId = field(formData, "critiqueId");
  if (!critiqueId) throw new Error("critiqueId is required.");

  await cancelBountyPayout(
    tenant.organizationId,
    critiqueId,
    field(formData, "cancellationNote"),
  );

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
}

/**
 * Route an accepted critique to the revision engine (prompt 16). Stores
 * the critique's counter-evidence as a `RevisionInput` batch keyed by
 * the founder-supplied claim id and weight.
 */
export async function triggerCritiqueRevisionAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  const critiqueId = field(formData, "critiqueId");
  const claimId = field(formData, "claimId").trim();
  const weightStr = field(formData, "weight").trim();
  if (!critiqueId || !claimId) {
    throw new Error("critiqueId and claimId are required.");
  }
  const weight = Number(weightStr || "-0.5");
  if (!Number.isFinite(weight)) throw new Error(`Invalid weight: ${weightStr}`);

  const critique = await db.critiqueSubmission.findFirst({
    where: { id: critiqueId, organizationId: tenant.organizationId },
    select: { id: true, counterEvidence: true, status: true },
  });
  if (!critique) throw new Error("Unknown critique submission");
  if (critique.status !== "accepted") {
    throw new Error("Only accepted critiques can be routed to the revision engine.");
  }

  const inputs = [
    {
      claim_id: claimId,
      weight: Math.max(-1, Math.min(1, weight)),
      new_evidence: critique.counterEvidence,
    },
  ];
  const event = await db.revisionEvent.create({
    data: {
      organizationId: tenant.organizationId,
      planId: `critique_${critique.id}`,
      founderId: tenant.founderId,
      inputsJson: JSON.stringify(inputs),
      planJson: "{}",
      preConfidenceSnapshot: "{}",
      affectedConclusionIds: "[]",
      typedConfirmation: false,
    },
    select: { id: true },
  });

  await attachRevisionToCritique(tenant.organizationId, critique.id, event.id);

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
}

/**
 * Generate an `Addendum` for the critique's article that records the
 * critic's contribution. Mirrors the prompt-43 flow: the addendum is
 * a dated block; the original prose is not edited.
 */
export async function attachAddendumAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  const critiqueId = field(formData, "critiqueId");
  const summary = field(formData, "summary").trim();
  if (!critiqueId || !summary) {
    throw new Error("critiqueId and summary are required.");
  }

  const critique = await db.critiqueSubmission.findFirst({
    where: { id: critiqueId, organizationId: tenant.organizationId },
    select: {
      id: true,
      articleSlug: true,
      counterEvidence: true,
      status: true,
      displayName: true,
      submitterEmail: true,
    },
  });
  if (!critique) throw new Error("Unknown critique submission");
  if (critique.status !== "accepted") {
    throw new Error("Only accepted critiques can produce an article addendum.");
  }

  const credit = critique.displayName.trim() || critique.submitterEmail.split("@")[0] || "an outside critic";
  const addendum = await db.addendum.create({
    data: {
      organizationId: tenant.organizationId,
      articleSlug: critique.articleSlug,
      findingId: `critique:${critique.id}`,
      summary,
      body: `${critique.counterEvidence}\n\n— Contributed by ${credit} (see /critiques).`,
      status: "published",
      publishedAt: new Date(),
      reviewerConfig: "open-critique:v1",
    },
    select: { id: true },
  });

  await attachAddendumToCritique(tenant.organizationId, critique.id, addendum.id);

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/critiques/${critiqueId}`);
  revalidatePath(`/post/${encodeURIComponent(critique.articleSlug)}`);
}
