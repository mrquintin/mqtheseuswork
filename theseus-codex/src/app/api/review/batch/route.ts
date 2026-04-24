import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { pushReviewResolutionToNoosphere } from "@/lib/pushReviewToNoosphere";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";

type Verdict = "cohere" | "contradict" | "unresolved";

/**
 * Batch resolution endpoint. Updates every review item in one
 * transaction so the Codex side never ends up in a half-resolved state.
 * Noosphere sync is attempted per-row afterwards; failures are
 * captured in an AuditEvent (instead of fire-and-forget) so drift
 * between the Codex and Noosphere is observable and retriable from
 * /api/review/retry-sync.
 */
export async function POST(req: Request) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // Same gate as the per-item review endpoint: viewers don't vote.
  if (!canWrite(founder.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }

  const body = (await req.json()) as {
    ids?: string[];
    verdict?: Verdict;
    overrule?: boolean;
    note?: string;
  };

  const ids = body.ids ?? [];
  const verdict = body.verdict;
  const overrule = Boolean(body.overrule);
  const note = body.note ?? "";

  if (ids.length === 0 || !verdict || !["cohere", "contradict", "unresolved"].includes(verdict)) {
    return NextResponse.json({ error: "ids and verdict required" }, { status: 400 });
  }

  // Scope to this tenant's rows only: a malicious client could POST a
  // list that includes another org's review ids. `updateMany` combined
  // with an organizationId filter silently drops any cross-tenant rows.
  const scopedItems = await db.reviewItem.findMany({
    where: { id: { in: ids }, organizationId: founder.organizationId },
    select: { id: true, noosphereId: true, aggregatorVerdict: true },
  });
  const scopedIds = scopedItems.map((it) => it.id);

  if (scopedIds.length === 0) {
    return NextResponse.json({ ok: true, count: 0 });
  }

  await db.reviewItem.updateMany({
    where: { id: { in: scopedIds }, organizationId: founder.organizationId },
    data: {
      status: "done",
      humanVerdict: verdict,
      humanOverrule: overrule,
      resolutionNote: note,
      resolvedAt: new Date(),
      resolvedByFounderId: founder.id,
    },
  });

  const syncFailures: { id: string; error: string }[] = [];
  for (const item of scopedItems) {
    if (!item.noosphereId) continue;
    try {
      const result = await pushReviewResolutionToNoosphere({
        reviewId: item.noosphereId,
        verdict,
        overrule,
        aggregatorVerdict: item.aggregatorVerdict,
        founderId: founder.noosphereId || founder.id,
        note,
      });
      if (!result.ok) {
        syncFailures.push({ id: item.id, error: result.stderr });
      }
    } catch (err) {
      syncFailures.push({ id: item.id, error: String(err) });
    }
  }

  if (syncFailures.length > 0) {
    await db.auditEvent.create({
      data: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        action: "noosphere_batch_sync_failed",
        detail: JSON.stringify({ failedIds: syncFailures.map((f) => f.id) }),
      },
    });
  }

  return NextResponse.json({
    ok: true,
    count: scopedIds.length,
    syncFailures: syncFailures.length,
  });
}
