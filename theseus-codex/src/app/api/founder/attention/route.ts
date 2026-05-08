import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";
import {
  ATTENTION_QUEUES,
  type AttentionQueueId,
  listAttentionForFounder,
  resolveSnoozeRequest,
} from "@/lib/attention";

/**
 * Unified attention queue API.
 *
 * GET  /api/founder/attention  → ranked list across every queue.
 * POST /api/founder/attention  → record a snooze or dismiss action.
 *
 * The dashboard renders the GET payload as its primary surface; the
 * Snooze and Dismiss affordances on each row POST to this same route.
 * Snoozes longer than 14 days are rewritten as dismissals with reason
 * "deferred indefinitely" — see `resolveSnoozeRequest` in
 * `src/lib/attention.ts`.
 */

export async function GET() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const listing = await listAttentionForFounder(tenant);
  return NextResponse.json({
    generatedAt: listing.generatedAt.toISOString(),
    items: listing.items.map((item) => ({
      queue: item.queue,
      queueLabel: item.queueLabel,
      itemId: item.itemId,
      severity: item.severity,
      ageMs: listing.generatedAt.getTime() - item.createdAt.getTime(),
      createdAt: item.createdAt.toISOString(),
      preview: item.preview,
      link: item.link,
    })),
    dismissalRates: listing.dismissalRates,
  });
}

type ActionBody = {
  queue?: string;
  itemId?: string;
  action?: string;
  snoozedUntil?: string;
  reason?: string;
};

export async function POST(req: Request) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: ActionBody;
  try {
    body = (await req.json()) as ActionBody;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const queue = (body.queue ?? "").trim() as AttentionQueueId;
  const itemId = (body.itemId ?? "").trim();
  const action = (body.action ?? "").trim();
  const reason = (body.reason ?? "").toString();

  if (!itemId || !(ATTENTION_QUEUES as readonly string[]).includes(queue)) {
    return NextResponse.json({ error: "invalid_queue_or_item" }, { status: 400 });
  }

  const now = new Date();

  if (action === "dismiss") {
    if (!reason.trim()) {
      return NextResponse.json({ error: "reason_required" }, { status: 400 });
    }
    await db.attentionAction.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        queue,
        itemId,
        action: "dismiss",
        snoozedUntil: null,
        reason: reason.trim(),
      },
    });
    return NextResponse.json({ ok: true, action: "dismiss" });
  }

  if (action === "unsnooze") {
    await db.attentionAction.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        queue,
        itemId,
        action: "unsnooze",
        snoozedUntil: null,
        reason: "",
      },
    });
    return NextResponse.json({ ok: true, action: "unsnooze" });
  }

  if (action === "snooze") {
    const requestedUntil = body.snoozedUntil ? new Date(body.snoozedUntil) : null;
    if (!requestedUntil || Number.isNaN(requestedUntil.getTime())) {
      return NextResponse.json({ error: "snoozedUntil_required" }, { status: 400 });
    }
    const resolved = resolveSnoozeRequest(requestedUntil, now);
    if (resolved.kind === "dismiss") {
      await db.attentionAction.create({
        data: {
          organizationId: tenant.organizationId,
          founderId: tenant.founderId,
          queue,
          itemId,
          action: "dismiss",
          snoozedUntil: null,
          reason: resolved.reason,
        },
      });
      return NextResponse.json({
        ok: true,
        action: "dismiss",
        rewrittenFromSnooze: true,
        reason: resolved.reason,
      });
    }
    await db.attentionAction.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        queue,
        itemId,
        action: "snooze",
        snoozedUntil: resolved.snoozedUntil,
        reason: reason.trim(),
      },
    });
    return NextResponse.json({
      ok: true,
      action: "snooze",
      snoozedUntil: resolved.snoozedUntil.toISOString(),
    });
  }

  return NextResponse.json({ error: "unknown_action" }, { status: 400 });
}
