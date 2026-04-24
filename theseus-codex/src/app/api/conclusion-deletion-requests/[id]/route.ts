import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";

type PatchBody = {
  action?: "accept" | "decline" | "cancel";
  decision?: string;
};

/**
 * Accept / decline / cancel a conclusion-deletion request.
 *
 * Authorisation rules (implemented below):
 *   - accept / decline: only the conclusion's attributed founder OR an
 *     admin in the same org.
 *   - cancel: only the original requester, only while the request is
 *     still `pending`.
 *
 * On accept: the Conclusion is hard-deleted. FK cascades take care of
 * ConclusionSource; we additionally purge Contradiction and
 * OpenQuestion rows that reference this conclusion via claimAId /
 * claimBId (those are untyped string fields so Prisma won't cascade).
 */
export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // Accept / decline / cancel are all corpus-state mutations.
  // (The next layer down still enforces fine-grained authorisation —
  // only the attributed founder or an admin can accept; only the
  // requester can cancel — see body of the handler.)
  if (!canWrite(tenant.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }
  const { id } = await ctx.params;
  const body = (await req.json()) as PatchBody;

  const request = await db.conclusionDeletionRequest.findUnique({
    where: { id },
    include: {
      conclusion: {
        select: {
          id: true,
          organizationId: true,
          attributedFounderId: true,
        },
      },
      requester: { select: { id: true } },
    },
  });
  if (!request || request.conclusion.organizationId !== tenant.organizationId) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  if (body.action === "cancel") {
    if (request.requester.id !== tenant.founderId) {
      return NextResponse.json({ error: "Only the requester may cancel" }, { status: 403 });
    }
    if (request.status !== "pending") {
      return NextResponse.json({ error: "Request is not pending" }, { status: 400 });
    }
    await db.conclusionDeletionRequest.update({
      where: { id },
      data: { status: "cancelled", respondedAt: new Date() },
    });
    return NextResponse.json({ ok: true, status: "cancelled" });
  }

  if (body.action !== "accept" && body.action !== "decline") {
    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  }

  const founder = await db.founder.findUnique({
    where: { id: tenant.founderId },
    select: { role: true },
  });
  const isAdmin = founder?.role === "admin";
  const isAttributed =
    request.conclusion.attributedFounderId === tenant.founderId;
  if (!isAdmin && !isAttributed) {
    return NextResponse.json(
      { error: "Only the attributed founder or an admin may decide" },
      { status: 403 },
    );
  }
  if (request.status !== "pending") {
    return NextResponse.json({ error: "Request is not pending" }, { status: 400 });
  }

  const conclusionId = request.conclusion.id;

  if (body.action === "accept") {
    // Cascade-clean derived artifacts that reference this conclusion by
    // a raw string column (no FK → no cascade) BEFORE deleting the
    // conclusion itself. Contradiction.claim{A,B}Id and
    // OpenQuestion.claim{A,B}Id are the two known cases.
    const [contradictionsDel, openQuestionsDel] = await db.$transaction([
      db.contradiction.deleteMany({
        where: {
          organizationId: tenant.organizationId,
          OR: [{ claimAId: conclusionId }, { claimBId: conclusionId }],
        },
      }),
      db.openQuestion.deleteMany({
        where: {
          organizationId: tenant.organizationId,
          OR: [{ claimAId: conclusionId }, { claimBId: conclusionId }],
        },
      }),
    ]);

    // Deleting the Conclusion cascades ConclusionSource,
    // PublicationReview (onDelete: Cascade), and
    // ConclusionDeletionRequest (including this very row).
    await db.conclusion.delete({ where: { id: conclusionId } });

    await db.auditEvent.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        action: "conclusion_deletion_accepted",
        detail: JSON.stringify({
          conclusionId,
          requestId: id,
          decision: body.decision || null,
          cascadeDeletes: {
            contradictions: contradictionsDel.count,
            openQuestions: openQuestionsDel.count,
          },
        }),
      },
    });

    return NextResponse.json({ ok: true, status: "accepted" });
  }

  // Decline branch
  await db.conclusionDeletionRequest.update({
    where: { id },
    data: {
      status: "declined",
      decision: body.decision || null,
      respondedAt: new Date(),
    },
  });
  await db.auditEvent.create({
    data: {
      organizationId: tenant.organizationId,
      founderId: tenant.founderId,
      action: "conclusion_deletion_declined",
      detail: JSON.stringify({ conclusionId, requestId: id, decision: body.decision || null }),
    },
  });
  return NextResponse.json({ ok: true, status: "declined" });
}
