/**
 * POST /api/uploads/:id/delete — OWNER-ONLY direct deletion.
 *
 * The only path to soft-delete an upload without going through a
 * DeletionRequest. Rules:
 *
 *   * Caller must be authenticated.
 *   * Caller must belong to the upload's organization.
 *   * Caller must be the upload's `founderId`. If not, the request
 *     returns 403 with instructions pointing at the peer request API.
 *
 * On success:
 *   * `Upload.deletedAt = now()`.
 *   * `Upload.publishedAt = null` (so the row can't stay on the blog
 *     while hidden from the library — keeps the two surfaces in sync).
 *   * Any pending `DeletionRequest` rows for this upload are moved to
 *     `status='cancelled'` with a decision note so requesters aren't
 *     left waiting on a response that will never come.
 *   * An `AuditEvent` records the deletion.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { sanitizeAndCap } from "@/lib/sanitizeText";

export async function POST(
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
      reason?: string;
    };
    const reason = body.reason
      ? sanitizeAndCap(body.reason, 1000)
      : null;

    const upload = await db.upload.findUnique({
      where: { id },
      select: {
        id: true,
        organizationId: true,
        founderId: true,
        title: true,
        deletedAt: true,
      },
    });
    if (!upload) {
      return NextResponse.json({ error: "Upload not found" }, { status: 404 });
    }
    if (upload.organizationId !== founder.organizationId) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }
    if (upload.founderId !== founder.id) {
      return NextResponse.json(
        {
          error:
            "Only the uploader can delete this directly. Open a " +
            "DeletionRequest (POST /api/deletion-requests) instead; the " +
            "owner can accept or decline.",
        },
        { status: 403 },
      );
    }
    if (upload.deletedAt) {
      return NextResponse.json(
        { error: "Upload is already deleted." },
        { status: 410 },
      );
    }

    // Soft-delete in a single transaction so the "cancel pending
    // requests" side-effect stays consistent with the deletion itself.
    const now = new Date();
    await db.$transaction([
      db.upload.update({
        where: { id },
        data: {
          deletedAt: now,
          publishedAt: null, // yank from the public blog too
        },
      }),
      db.deletionRequest.updateMany({
        where: { uploadId: id, status: "pending" },
        data: {
          status: "cancelled",
          decision: "Owner deleted the upload directly.",
          respondedAt: now,
        },
      }),
      db.auditEvent.create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId: id,
          action: "delete",
          detail: sanitizeAndCap(
            reason
              ? `Owner soft-deleted upload "${upload.title}" — reason: ${reason}`
              : `Owner soft-deleted upload "${upload.title}"`,
            2000,
          ),
        },
      }),
    ]);

    return NextResponse.json({
      ok: true,
      id,
      deletedAt: now.toISOString(),
    });
  } catch (error) {
    console.error("upload/delete error:", error);
    return NextResponse.json(
      {
        error:
          `Delete failed: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
