/**
 * PATCH  /api/deletion-requests/:id — owner accept or decline.
 * DELETE /api/deletion-requests/:id — requester cancels own pending req.
 *
 * PATCH body: `{ action: "accept" | "decline", decision?: string }`.
 *   * `accept`  → soft-deletes the upload + marks request accepted.
 *   * `decline` → marks request declined + records `decision` note.
 *
 * Only the UPLOAD's owner can accept or decline. Only the REQUESTER
 * can cancel (and only while the request is still pending). Every
 * other flip is a 403.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { sanitizeAndCap } from "@/lib/sanitizeText";
import {
  cascadeDeleteUploadArtifacts,
  formatCascadeCounts,
} from "@/lib/uploadDeleteCascade";

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }

    const { id } = await params;
    const body = (await req.json().catch(() => ({}))) as {
      action?: string;
      decision?: string;
    };
    const action = (body.action || "").toLowerCase();
    if (action !== "accept" && action !== "decline") {
      return NextResponse.json(
        { error: 'action must be "accept" or "decline"' },
        { status: 400 },
      );
    }
    const decision = body.decision
      ? sanitizeAndCap(body.decision, 1000)
      : null;

    const request_ = await db.deletionRequest.findUnique({
      where: { id },
      select: {
        id: true,
        status: true,
        uploadId: true,
        requesterId: true,
        upload: {
          select: {
            id: true,
            organizationId: true,
            founderId: true,
            title: true,
            deletedAt: true,
          },
        },
      },
    });
    if (!request_) {
      return NextResponse.json(
        { error: "Deletion request not found" },
        { status: 404 },
      );
    }
    if (request_.upload.organizationId !== founder.organizationId) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }
    if (request_.upload.founderId !== founder.id) {
      return NextResponse.json(
        {
          error:
            "Only the upload's owner can accept or decline a deletion request.",
        },
        { status: 403 },
      );
    }
    if (request_.status !== "pending") {
      return NextResponse.json(
        {
          error: `This request is already ${request_.status} — no further action possible.`,
        },
        { status: 409 },
      );
    }

    const now = new Date();

    if (action === "accept") {
      // Accept = soft-delete the upload AND mark this request accepted
      // AND cancel any OTHER pending requests on the same upload (they
      // all asked for the same outcome; no reason to keep them live)
      // AND cascade-delete any derived artifacts (ConclusionSource
      // links, orphaned Conclusions, Contradictions/OpenQuestions whose
      // claim references now dangle, ResearchSuggestions sourced by
      // this upload). All atomic.
      const cascade = await db.$transaction(async (tx) => {
        await tx.upload.update({
          where: { id: request_.uploadId },
          data: {
            deletedAt: now,
            publishedAt: null,
          },
        });
        await tx.deletionRequest.update({
          where: { id },
          data: {
            status: "accepted",
            decision,
            respondedAt: now,
          },
        });
        await tx.deletionRequest.updateMany({
          where: {
            uploadId: request_.uploadId,
            status: "pending",
            id: { not: id },
          },
          data: {
            status: "cancelled",
            decision: "Superseded by owner's acceptance of another request.",
            respondedAt: now,
          },
        });
        const counts = await cascadeDeleteUploadArtifacts(
          tx,
          request_.uploadId,
        );
        const cascadeDetail = formatCascadeCounts(counts);
        await tx.auditEvent.create({
          data: {
            organizationId: founder.organizationId,
            founderId: founder.id,
            uploadId: request_.uploadId,
            action: "deletion_request_accept",
            detail: sanitizeAndCap(
              decision
                ? `Accepted deletion request for "${request_.upload.title}" — ${decision} · ${cascadeDetail}`
                : `Accepted deletion request for "${request_.upload.title}" · ${cascadeDetail}`,
              2000,
            ),
          },
        });
        return counts;
      });
      return NextResponse.json({
        ok: true,
        status: "accepted",
        uploadDeletedAt: now.toISOString(),
        cascade,
      });
    }

    // Decline path: leave the upload alone, record the decision.
    await db.$transaction([
      db.deletionRequest.update({
        where: { id },
        data: {
          status: "declined",
          decision,
          respondedAt: now,
        },
      }),
      db.auditEvent.create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId: request_.uploadId,
          action: "deletion_request_decline",
          detail: sanitizeAndCap(
            decision
              ? `Declined deletion request for "${request_.upload.title}" — ${decision}`
              : `Declined deletion request for "${request_.upload.title}"`,
            2000,
          ),
        },
      }),
    ]);
    return NextResponse.json({ ok: true, status: "declined" });
  } catch (error) {
    console.error("deletion-requests PATCH error:", error);
    return NextResponse.json(
      {
        error: `Action failed: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}

export async function DELETE(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }
    const { id } = await params;

    const request_ = await db.deletionRequest.findUnique({
      where: { id },
      select: {
        id: true,
        status: true,
        requesterId: true,
        uploadId: true,
        upload: { select: { organizationId: true, title: true } },
      },
    });
    if (!request_) {
      return NextResponse.json(
        { error: "Deletion request not found" },
        { status: 404 },
      );
    }
    if (request_.upload.organizationId !== founder.organizationId) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }
    if (request_.requesterId !== founder.id) {
      return NextResponse.json(
        { error: "Only the requester can cancel this request." },
        { status: 403 },
      );
    }
    if (request_.status !== "pending") {
      return NextResponse.json(
        {
          error: `This request is already ${request_.status} — cancellation is only valid for pending requests.`,
        },
        { status: 409 },
      );
    }

    const now = new Date();
    await db.$transaction([
      db.deletionRequest.update({
        where: { id },
        data: {
          status: "cancelled",
          respondedAt: now,
          decision: "Cancelled by requester.",
        },
      }),
      db.auditEvent.create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId: request_.uploadId,
          action: "deletion_request_cancel",
          detail: `Cancelled deletion request for "${request_.upload.title}"`,
        },
      }),
    ]);

    return NextResponse.json({ ok: true, status: "cancelled" });
  } catch (error) {
    console.error("deletion-requests DELETE error:", error);
    return NextResponse.json(
      {
        error: `Cancel failed: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
