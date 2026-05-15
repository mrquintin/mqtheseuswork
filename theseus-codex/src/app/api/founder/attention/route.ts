import { ApiError } from "@/lib/api/envelope";
import { withApiHandler } from "@/lib/api/handler";
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
 * Responses use the standard envelope:
 *   `{ ok: true, data: ..., meta: { generatedAt } }`
 *
 * Snoozes longer than 14 days are rewritten as dismissals with reason
 * "deferred indefinitely" — see `resolveSnoozeRequest` in
 * `src/lib/attention.ts`.
 */

type AttentionListing = {
  generatedAt: string;
  items: Array<{
    queue: string;
    queueLabel: string;
    itemId: string;
    severity: string;
    ageMs: number;
    createdAt: string;
    preview: string;
    link: string;
  }>;
  dismissalRates: Awaited<ReturnType<typeof listAttentionForFounder>>["dismissalRates"];
};

export const GET = withApiHandler<AttentionListing>(async () => {
  const tenant = await requireTenantContext();
  if (!tenant) {
    throw new ApiError("unauthorized", "Unauthorized");
  }
  const listing = await listAttentionForFounder(tenant);
  const generatedAt = listing.generatedAt.toISOString();
  const items = listing.items.map((item) => ({
    queue: item.queue,
    queueLabel: item.queueLabel,
    itemId: item.itemId,
    severity: item.severity,
    ageMs: listing.generatedAt.getTime() - item.createdAt.getTime(),
    createdAt: item.createdAt.toISOString(),
    preview: item.preview,
    link: item.link,
  }));
  const data: AttentionListing = {
    generatedAt,
    items,
    dismissalRates: listing.dismissalRates,
  };
  return {
    data,
    meta: { generatedAt },
    legacy: data,
  };
});

type ActionBody = {
  queue?: string;
  itemId?: string;
  action?: string;
  snoozedUntil?: string;
  reason?: string;
};

type AttentionAction =
  | { action: "dismiss"; rewrittenFromSnooze?: boolean; reason?: string }
  | { action: "snooze"; snoozedUntil: string }
  | { action: "unsnooze" };

export const POST = withApiHandler<AttentionAction>(async (req) => {
  const tenant = await requireTenantContext();
  if (!tenant) {
    throw new ApiError("unauthorized", "Unauthorized");
  }

  let body: ActionBody;
  try {
    body = (await req.json()) as ActionBody;
  } catch {
    throw new ApiError("bad_json", "invalid_json");
  }

  const queue = (body.queue ?? "").trim() as AttentionQueueId;
  const itemId = (body.itemId ?? "").trim();
  const action = (body.action ?? "").trim();
  const reason = (body.reason ?? "").toString();

  if (!itemId || !(ATTENTION_QUEUES as readonly string[]).includes(queue)) {
    throw new ApiError("validation_error", "invalid_queue_or_item");
  }

  const now = new Date();

  if (action === "dismiss") {
    if (!reason.trim()) {
      throw new ApiError("validation_error", "reason_required");
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
    const payload: AttentionAction = { action: "dismiss" };
    return { data: payload, legacy: { ok: true, ...payload } };
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
    const payload: AttentionAction = { action: "unsnooze" };
    return { data: payload, legacy: { ok: true, ...payload } };
  }

  if (action === "snooze") {
    const requestedUntil = body.snoozedUntil ? new Date(body.snoozedUntil) : null;
    if (!requestedUntil || Number.isNaN(requestedUntil.getTime())) {
      throw new ApiError("validation_error", "snoozedUntil_required");
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
      const payload: AttentionAction = {
        action: "dismiss",
        rewrittenFromSnooze: true,
        reason: resolved.reason,
      };
      return { data: payload, legacy: { ok: true, ...payload } };
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
    const payload: AttentionAction = {
      action: "snooze",
      snoozedUntil: resolved.snoozedUntil.toISOString(),
    };
    return { data: payload, legacy: { ok: true, ...payload } };
  }

  throw new ApiError("validation_error", "unknown_action");
});
