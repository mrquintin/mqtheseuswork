/**
 * GET  /api/deletion-requests — list requests visible to the caller.
 * POST /api/deletion-requests — open a request against another
 *                                founder's upload.
 *
 * Visibility rules for GET:
 *   * As an OWNER: any request targeting an upload the caller uploaded.
 *   * As a REQUESTER: any request the caller opened (any status).
 *   * Requests on soft-deleted uploads are hidden (nothing to act on).
 *
 * Creation rules for POST:
 *   * Caller must not be the upload's owner — owners delete directly.
 *   * Upload must be in the caller's organization.
 *   * Upload must not already be deleted.
 *   * Caller must not already have a pending request on this upload
 *     (unique partial index enforces this at the DB level; we catch
 *     the error and return a friendly 409).
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { sanitizeAndCap } from "@/lib/sanitizeText";

export async function GET(req: Request) {
  const founder = await getFounderFromAuth(req);
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  // Owner-facing queue: requests pending against uploads this founder
  // owns. Ordered oldest-first so nothing gets starved of attention.
  const incoming = await db.deletionRequest.findMany({
    where: {
      status: "pending",
      upload: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        deletedAt: null,
      },
    },
    orderBy: { createdAt: "asc" },
    select: {
      id: true,
      reason: true,
      createdAt: true,
      requester: { select: { id: true, name: true } },
      upload: {
        select: {
          id: true,
          title: true,
          originalName: true,
          createdAt: true,
        },
      },
    },
  });

  // Requester-facing history: everything this founder has opened,
  // regardless of status, so they can see accepted/declined outcomes.
  const outgoing = await db.deletionRequest.findMany({
    where: { requesterId: founder.id },
    orderBy: { createdAt: "desc" },
    take: 100,
    select: {
      id: true,
      status: true,
      reason: true,
      decision: true,
      createdAt: true,
      respondedAt: true,
      upload: {
        select: {
          id: true,
          title: true,
          founder: { select: { id: true, name: true } },
          deletedAt: true,
        },
      },
    },
  });

  return NextResponse.json({
    incoming,
    outgoing,
  });
}

export async function POST(req: Request) {
  const founder = await getFounderFromAuth(req);
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const body = (await req.json().catch(() => ({}))) as {
    upload_id?: string;
    uploadId?: string;
    reason?: string;
  };
  const uploadId = body.upload_id || body.uploadId;
  if (!uploadId) {
    return NextResponse.json(
      { error: "upload_id is required" },
      { status: 400 },
    );
  }
  const reason = body.reason ? sanitizeAndCap(body.reason, 1000) : null;

  const upload = await db.upload.findUnique({
    where: { id: uploadId },
    select: {
      id: true,
      organizationId: true,
      founderId: true,
      title: true,
      deletedAt: true,
      visibility: true,
    },
  });
  if (!upload) {
    return NextResponse.json({ error: "Upload not found" }, { status: 404 });
  }
  if (upload.organizationId !== founder.organizationId) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  if (upload.deletedAt) {
    return NextResponse.json(
      { error: "That upload has already been deleted." },
      { status: 410 },
    );
  }
  // Private uploads that aren't yours: 404, not 403. We deliberately
  // don't leak the existence of peers' private rows through a more
  // specific error code — a peer who guessed the id should get the
  // same response as if the id didn't exist.
  if (upload.visibility === "private" && upload.founderId !== founder.id) {
    return NextResponse.json({ error: "Upload not found" }, { status: 404 });
  }
  if (upload.founderId === founder.id) {
    return NextResponse.json(
      {
        error:
          "You own this upload — delete it directly via POST /api/upload/:id/delete instead of opening a request against yourself.",
      },
      { status: 400 },
    );
  }

  try {
    const created = await db.deletionRequest.create({
      data: {
        uploadId,
        requesterId: founder.id,
        reason,
      },
      select: {
        id: true,
        status: true,
        createdAt: true,
      },
    });

    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId,
          action: "deletion_request_open",
          detail: sanitizeAndCap(
            reason
              ? `Requested deletion of "${upload.title}" — reason: ${reason}`
              : `Requested deletion of "${upload.title}"`,
            2000,
          ),
        },
      })
      .catch(() => {
        /* non-fatal */
      });

    return NextResponse.json({ ok: true, request: created });
  } catch (err) {
    // Unique partial index collision → 409 Conflict.
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("DeletionRequest_active_unique") || msg.includes("Unique")) {
      return NextResponse.json(
        {
          error:
            "You already have a pending deletion request on this upload. Cancel or wait for the owner's response before opening a new one.",
        },
        { status: 409 },
      );
    }
    return NextResponse.json(
      { error: `Failed to open request: ${msg}` },
      { status: 500 },
    );
  }
}
