"use server";

/**
 * Server actions for the response-triage workspace.
 *
 * Each action checks tenancy, mutates one row, and revalidates the
 * affected paths. The actions deliberately do not branch on label —
 * the founder is the gatekeeper, not the classifier. We do enforce
 * the consent-symmetry rule (a public reply requires both
 * `PublicResponse.publishConsent` AND `publishConfirmed=true` here)
 * because that protects the responder from a unilateral publish.
 */

import { revalidatePath } from "next/cache";

import { db } from "@/lib/db";
import { sendMail } from "@/lib/mail";
import { conclusionPublicUrl, conclusionTitle, notifyFromAddress } from "@/lib/responsesEmail";
import { TRIAGE_LABELS, type TriageLabel } from "@/lib/responseTriageApi";
import { requireTenantContext } from "@/lib/tenant";

const QUEUE_PATH = "/responses/queue";

function field(form: FormData, name: string): string {
  const v = form.get(name);
  return typeof v === "string" ? v : "";
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function loadTriage(triageId: string, organizationId: string) {
  const row = await db.responseTriage.findFirst({
    where: { id: triageId, organizationId },
    include: {
      publicResponse: {
        include: {
          published: { select: { slug: true, version: true, payloadJson: true } },
        },
      },
    },
  });
  if (!row) throw new Error(`Triage row ${triageId} not found.`);
  return row;
}

export async function archiveTriageAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const triageId = field(formData, "triageId");
  if (!triageId) throw new Error("triageId is required.");
  const note = field(formData, "archiveNote").trim();

  await db.responseTriage.updateMany({
    where: { id: triageId, organizationId: tenant.organizationId },
    data: { archivedAt: new Date(), archiveNote: note },
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/responses/${triageId}`);
}

export async function restoreTriageAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const triageId = field(formData, "triageId");
  if (!triageId) throw new Error("triageId is required.");

  await db.responseTriage.updateMany({
    where: { id: triageId, organizationId: tenant.organizationId },
    data: { archivedAt: null, archiveNote: "" },
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/responses/${triageId}`);
}

export async function overrideTriageLabelAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const triageId = field(formData, "triageId");
  const manualLabel = field(formData, "manualLabel");
  const manualReason = field(formData, "manualReason");
  if (!triageId) throw new Error("triageId is required.");
  if (manualLabel && !TRIAGE_LABELS.includes(manualLabel as TriageLabel)) {
    throw new Error(`Unknown triage label: ${manualLabel}`);
  }

  await db.responseTriage.updateMany({
    where: { id: triageId, organizationId: tenant.organizationId },
    data: {
      manualLabel,
      manualReason: manualReason.trim(),
    },
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/responses/${triageId}`);
}

export async function replyPrivateAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const triageId = field(formData, "triageId");
  const body = field(formData, "body").trim();
  if (!triageId || !body) throw new Error("triageId and reply body are required.");

  const row = await loadTriage(triageId, tenant.organizationId);
  if (row.publicResponse.pseudonymous || !row.publicResponse.submitterEmail) {
    throw new Error("Cannot reply privately to a pseudonymous responder.");
  }

  await db.publicReply.upsert({
    where: { publicResponseId: row.publicResponseId },
    create: {
      organizationId: tenant.organizationId,
      publicResponseId: row.publicResponseId,
      founderId: tenant.founderId,
      visibility: "private",
      body,
      publishConfirmed: false,
    },
    update: {
      body,
      visibility: "private",
      publishConfirmed: false,
      publishConfirmedAt: null,
      founderId: tenant.founderId,
    },
  });

  const title = conclusionTitle({
    id: row.publicResponse.publishedConclusionId,
    slug: row.publicResponse.published.slug,
    payloadJson: row.publicResponse.published.payloadJson,
  });
  const url = conclusionPublicUrl({
    id: row.publicResponse.publishedConclusionId,
    slug: row.publicResponse.published.slug,
    version: row.publicResponse.published.version,
  });
  const replyText = `${body}\n\n— Theseus Codex (${url})\n`;
  await sendMail({
    to: row.publicResponse.submitterEmail,
    from: notifyFromAddress(),
    subject: `Re: your Theseus response on "${title.slice(0, 80)}"`,
    text: replyText,
    html: `<p style="white-space:pre-wrap">${escapeHtml(body)}</p><p>— Theseus Codex (<a href="${escapeHtml(url)}">${escapeHtml(url)}</a>)</p>`,
    headers: { "X-Theseus-Reply-Type": "private" },
  });

  await db.publicResponse.updateMany({
    where: { id: row.publicResponseId, organizationId: tenant.organizationId },
    data: { status: "engaged" },
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/responses/${triageId}`);
}

export async function promotePublicReplyAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const triageId = field(formData, "triageId");
  const body = field(formData, "body").trim();
  if (!triageId || !body) throw new Error("triageId and reply body are required.");

  const row = await loadTriage(triageId, tenant.organizationId);
  if (!row.publicResponse.publishConsent) {
    throw new Error(
      "The responder did not consent to publication. Use the private reply primitive instead.",
    );
  }

  await db.publicReply.upsert({
    where: { publicResponseId: row.publicResponseId },
    create: {
      organizationId: tenant.organizationId,
      publicResponseId: row.publicResponseId,
      founderId: tenant.founderId,
      visibility: "public",
      body,
      publishConfirmed: true,
      publishConfirmedAt: new Date(),
    },
    update: {
      body,
      visibility: "public",
      publishConfirmed: true,
      publishConfirmedAt: new Date(),
      founderId: tenant.founderId,
    },
  });

  await db.publicResponse.updateMany({
    where: { id: row.publicResponseId, organizationId: tenant.organizationId },
    data: { status: "approved" },
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/responses/${triageId}`);
  revalidatePath(`/c/${encodeURIComponent(row.publicResponse.published.slug)}`);
}

export async function promoteToReviewAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const triageId = field(formData, "triageId");
  const note = field(formData, "note").trim();
  if (!triageId) throw new Error("triageId is required.");

  const row = await loadTriage(triageId, tenant.organizationId);
  if (!row.impliedObjection) {
    throw new Error(
      "No implied objection on this response. Re-classify or fill in the implied objection first.",
    );
  }

  // The conclusion's review queue is shared with the publication
  // pipeline. We open a ReviewItem of kind "reader_objection" so the
  // peer-review surface picks it up in the same severity-sorted
  // bucket as swarm objections (prompt 22).
  // The conclusion-level review queue stores its rows in `ReviewItem`,
  // which is schema-shaped around contradicting claim pairs (claimAId
  // / claimBId). A reader objection isn't a paired-claim diff, so we
  // don't synthesise placeholder claim ids — instead the
  // `promotedToReview` flag on the `PublicReply` is the queue marker,
  // and the conclusion detail page picks it up alongside swarm
  // objections via the same severity rubric (prompt 22).
  void note;

  await db.publicReply.upsert({
    where: { publicResponseId: row.publicResponseId },
    create: {
      organizationId: tenant.organizationId,
      publicResponseId: row.publicResponseId,
      founderId: tenant.founderId,
      visibility: "private",
      body: row.impliedObjection,
      promotedToReview: true,
    },
    update: {
      promotedToReview: true,
      founderId: tenant.founderId,
    },
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/responses/${triageId}`);
  revalidatePath(`/peer-review`);
}

export async function triggerRevisionAction(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const triageId = field(formData, "triageId");
  const claimId = field(formData, "claimId").trim();
  const weightStr = field(formData, "weight").trim();
  if (!triageId || !claimId) {
    throw new Error("triageId and claimId are required to route to the revision engine.");
  }
  const weight = Number(weightStr || "-0.5");
  if (!Number.isFinite(weight)) throw new Error(`Invalid weight: ${weightStr}`);

  const row = await loadTriage(triageId, tenant.organizationId);
  if (!row.impliedObjection) {
    throw new Error("No implied objection on this response — cannot route to revision engine.");
  }

  // The codex stores the input as a RevisionEvent with a single
  // RevisionInput batch. The Python engine consumes the same shape.
  // We persist the input here; the engine picks it up on its next run.
  const inputs = [
    {
      claim_id: claimId,
      weight: Math.max(-1, Math.min(1, weight)),
      new_evidence: row.impliedObjection,
    },
  ];
  const event = await db.revisionEvent.create({
    data: {
      organizationId: tenant.organizationId,
      planId: `triage_${row.id}`,
      founderId: tenant.founderId,
      inputsJson: JSON.stringify(inputs),
      planJson: "{}",
      preConfidenceSnapshot: "{}",
      affectedConclusionIds: "[]",
      typedConfirmation: false,
    },
    select: { id: true },
  });

  await db.publicReply.upsert({
    where: { publicResponseId: row.publicResponseId },
    create: {
      organizationId: tenant.organizationId,
      publicResponseId: row.publicResponseId,
      founderId: tenant.founderId,
      visibility: "private",
      body: row.impliedObjection,
      triggeredRevisionId: event.id,
    },
    update: {
      triggeredRevisionId: event.id,
      founderId: tenant.founderId,
    },
  });

  revalidatePath(QUEUE_PATH);
  revalidatePath(`/responses/${triageId}`);
}
