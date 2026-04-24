/**
 * POST /api/upload/:id/retry — reset a failed upload to `pending`.
 *
 * The retry button in the dashboard detail row calls this. We
 * deliberately keep it narrow:
 *
 *   * Only rows in `status='failed'` may be retried. Retrying
 *     `processing` or `extracting` would race the noosphere runner
 *     and could produce duplicate Conclusions (the Wave-0 bug).
 *   * We ONLY flip the status + clear the error/extraction fields;
 *     we don't trigger a dispatch from here. The local runner and the
 *     GitHub Actions cron both sweep `status='pending'` on their own
 *     cycles, so the row gets picked up within ~10 minutes at worst
 *     without risking a double-dispatch.
 *   * Viewers can read but not retry — `canWrite` gate.
 *
 * Returns `{ ok: true, id }` on success. Non-`failed` statuses give
 * 409 with `currentStatus` so the client can show a precise message.
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";
import { sanitizeAndCap } from "@/lib/sanitizeText";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const founder = await getFounderFromAuth(req);
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  if (!canWrite(founder.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }

  const { id } = await params;

  const upload = await db.upload.findUnique({
    where: { id },
    select: {
      id: true,
      organizationId: true,
      founderId: true,
      status: true,
      deletedAt: true,
      visibility: true,
      processLog: true,
    },
  });
  if (!upload || upload.deletedAt) {
    return NextResponse.json({ error: "Upload not found" }, { status: 404 });
  }
  if (upload.organizationId !== founder.organizationId) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  // Private rows stay private to their owner even under retry — an
  // admin in the org can't reset someone else's private upload.
  if (upload.visibility === "private" && upload.founderId !== founder.id) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  if (upload.status !== "failed") {
    return NextResponse.json(
      {
        error: "Only failed uploads can be retried.",
        currentStatus: upload.status,
      },
      { status: 409 },
    );
  }

  const retryNote = `\n— Retry requested by ${founder.name} at ${new Date().toISOString()} —\n`;
  await db.upload.update({
    where: { id },
    data: {
      status: "pending",
      errorMessage: null,
      extractionMethod: null,
      // Preserve the previous run's log so the founder can still read
      // what went wrong. The noosphere runner appends on top of this on
      // its next cycle.
      processLog: sanitizeAndCap(upload.processLog + retryNote, 8_000),
    },
  });

  await db.auditEvent.create({
    data: {
      organizationId: founder.organizationId,
      founderId: founder.id,
      uploadId: id,
      action: "upload.retry",
      detail: "Reset failed upload to pending; awaiting noosphere pickup.",
    },
  });

  return NextResponse.json({ ok: true, id });
}
