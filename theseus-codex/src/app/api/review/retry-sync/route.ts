import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { pushReviewResolutionToNoosphere } from "@/lib/pushReviewToNoosphere";

/**
 * Retry endpoint for a review item whose initial Noosphere sync failed.
 * Eligibility: the item must be tenant-scoped to the caller, marked
 * `done`, have a populated `humanVerdict`, and carry a `noosphereId`
 * — anything else is a caller bug or a genuine missing-mirror case
 * that retry can't fix.
 *
 * Both success and failure paths write an AuditEvent so the retry
 * record stays auditable alongside the original failure row.
 */
export async function POST(req: Request) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { reviewItemId } = (await req.json()) as { reviewItemId?: string };
  if (!reviewItemId) {
    return NextResponse.json({ error: "reviewItemId required" }, { status: 400 });
  }

  const item = await db.reviewItem.findFirst({
    where: { id: reviewItemId, organizationId: founder.organizationId },
  });
  if (!item) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (!item.noosphereId || item.status !== "done" || !item.humanVerdict) {
    return NextResponse.json({ error: "Item not eligible for retry" }, { status: 400 });
  }

  const verdict = item.humanVerdict as "cohere" | "contradict" | "unresolved";
  const result = await pushReviewResolutionToNoosphere({
    reviewId: item.noosphereId,
    verdict,
    overrule: item.humanOverrule,
    aggregatorVerdict: item.aggregatorVerdict,
    founderId: founder.noosphereId || founder.id,
    note: item.resolutionNote,
  });

  await db.auditEvent.create({
    data: {
      organizationId: founder.organizationId,
      founderId: founder.id,
      action: result.ok ? "noosphere_sync_retried" : "noosphere_sync_retry_failed",
      detail: JSON.stringify({
        reviewItemId,
        success: result.ok,
        error: result.ok ? undefined : result.stderr,
      }),
    },
  });

  if (result.ok) {
    return NextResponse.json({ ok: true });
  }
  return NextResponse.json({ ok: false, error: result.stderr }, { status: 500 });
}
