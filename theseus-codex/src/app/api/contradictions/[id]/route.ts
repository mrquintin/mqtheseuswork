import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Round 19 prompt 19 — source-driven contradiction lifecycle.
 *
 * The manual "resolve" / "dismiss" path is REMOVED. Contradictions are
 * first-class entities that persist until new sources resolve them, or
 * the founder confirms a synthesis principle subsumes both sides
 * (terminal, requires explicit confirmation).
 *
 * Surviving actions on this route:
 *   - acknowledge → STANDING (records the contradiction is genuine)
 *   - dispute     → DISPUTED_AS_ERROR (terminal; logs calibration signal)
 *   - accept-subsumption  → SUBSUMED_BY_SYNTHESIS (founder confirms a
 *     pending synthesis candidate; the synthesis engine + auto-resolver
 *     populate the candidate)
 *   - reject-subsumption  → clear the pending candidate (status stays)
 *
 * The dropped actions ("resolve", "dismiss") return 404 so any old
 * client cache or hand-rolled curl call sees the surface is gone.
 */
export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (!canWrite(tenant.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }
  const { id } = await ctx.params;
  const body = (await req.json()) as {
    action?: string;
    resolution?: string;
    reason?: string;
    subsumingPrincipleId?: string;
  };

  // Removed surface — the manual-resolve / dismiss path no longer exists.
  // Per the founder's directive: "resolved only by the sources themselves."
  if (body.action === "resolve" || body.action === "dismiss") {
    return NextResponse.json(
      {
        error:
          "manual resolution removed; contradictions resolve via source ingestion. " +
          "Use 'acknowledge' to mark STANDING or 'dispute' to flag detection error.",
      },
      { status: 404 },
    );
  }

  const validActions = new Set([
    "acknowledge",
    "dispute",
    "accept-subsumption",
    "reject-subsumption",
  ]);
  if (!body.action || !validActions.has(body.action)) {
    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  }

  const existing = await db.contradiction.findFirst({
    where: { id, organizationId: tenant.organizationId },
    select: { id: true, status: true, detectionMethod: true },
  });
  if (!existing) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const lifecycle = await db.contradictionLifecycle.findUnique({
    where: { contradictionId: id },
  });
  const events: Array<Record<string, unknown>> = lifecycle
    ? parseEvents(lifecycle.eventsJson)
    : [
        {
          at: new Date().toISOString(),
          status_before: null,
          status_after: "DETECTED",
          rationale: "contradiction detected by engine",
          triggering_source_ids: [],
          supported_principle_id: null,
          subsuming_principle_id: null,
          score_change: null,
        },
      ];

  // ACKNOWLEDGE → STANDING
  if (body.action === "acknowledge") {
    if (lifecycle?.currentStatus === "STANDING") {
      return NextResponse.json({ ok: true, lifecycle });
    }
    if (
      lifecycle?.currentStatus === "DISPUTED_AS_ERROR" ||
      lifecycle?.currentStatus === "SUBSUMED_BY_SYNTHESIS"
    ) {
      return NextResponse.json(
        { error: `lifecycle is terminal (${lifecycle.currentStatus})` },
        { status: 409 },
      );
    }
    const now = new Date();
    const prev = lifecycle?.currentStatus ?? "DETECTED";
    events.push({
      at: now.toISOString(),
      status_before: prev,
      status_after: "STANDING",
      rationale: `founder (${tenant.founderId}) acknowledged as standing`,
      triggering_source_ids: [],
      supported_principle_id: lifecycle?.supportedPrincipleId ?? null,
      subsuming_principle_id: null,
      score_change: null,
    });
    const updated = await db.contradictionLifecycle.upsert({
      where: { contradictionId: id },
      create: {
        contradictionId: id,
        organizationId: tenant.organizationId,
        currentStatus: "STANDING",
        lastTransitionAt: now,
        eventsJson: JSON.stringify(events),
      },
      update: {
        currentStatus: "STANDING",
        lastTransitionAt: now,
        eventsJson: JSON.stringify(events),
      },
    });
    // Mirror to the legacy Contradiction row so other operator queues
    // can filter by `status="acknowledged"` until they migrate.
    await db.contradiction.update({
      where: { id },
      data: {
        status: "acknowledged",
        resolvedById: tenant.founderId,
        resolvedAt: now,
      },
    });
    await db.auditEvent.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        action: "contradiction_acknowledged",
        detail: JSON.stringify({
          contradictionId: id,
          detectionMethod: existing.detectionMethod,
        }),
      },
    });
    return NextResponse.json({ ok: true, lifecycle: updated });
  }

  // DISPUTE → DISPUTED_AS_ERROR (terminal)
  if (body.action === "dispute") {
    const reason = (body.reason || "").trim();
    if (!reason) {
      return NextResponse.json(
        { error: "Dispute reason is required" },
        { status: 400 },
      );
    }
    if (
      lifecycle?.currentStatus === "DISPUTED_AS_ERROR" ||
      lifecycle?.currentStatus === "SUBSUMED_BY_SYNTHESIS"
    ) {
      return NextResponse.json(
        { error: `lifecycle is terminal (${lifecycle.currentStatus})` },
        { status: 409 },
      );
    }
    const now = new Date();
    const prev = lifecycle?.currentStatus ?? "DETECTED";
    events.push({
      at: now.toISOString(),
      status_before: prev,
      status_after: "DISPUTED_AS_ERROR",
      rationale: `founder (${tenant.founderId}) disputed as detection error: ${reason}`,
      triggering_source_ids: [],
      supported_principle_id: null,
      subsuming_principle_id: null,
      score_change: null,
    });
    const dispute = await db.contradictionDispute.create({
      data: {
        contradictionId: id,
        organizationId: tenant.organizationId,
        detectionMethod: existing.detectionMethod ?? "",
        disputedById: tenant.founderId,
        reason,
      },
    });
    const updated = await db.contradictionLifecycle.upsert({
      where: { contradictionId: id },
      create: {
        contradictionId: id,
        organizationId: tenant.organizationId,
        currentStatus: "DISPUTED_AS_ERROR",
        lastTransitionAt: now,
        eventsJson: JSON.stringify(events),
      },
      update: {
        currentStatus: "DISPUTED_AS_ERROR",
        lastTransitionAt: now,
        eventsJson: JSON.stringify(events),
      },
    });
    await db.contradiction.update({
      where: { id },
      data: {
        status: "disputed",
        disputeCount: { increment: 1 },
        lastDisputeAt: now,
        resolvedById: tenant.founderId,
        resolvedAt: now,
        resolution: `DISPUTED: ${reason}`,
      },
    });
    await db.auditEvent.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        action: "contradiction_disputed",
        detail: JSON.stringify({
          contradictionId: id,
          disputeId: dispute.id,
          detectionMethod: existing.detectionMethod,
          reason,
        }),
      },
    });
    return NextResponse.json({
      ok: true,
      lifecycle: updated,
      dispute,
    });
  }

  // ACCEPT-SUBSUMPTION → SUBSUMED_BY_SYNTHESIS (terminal)
  if (body.action === "accept-subsumption") {
    const subsuming = (body.subsumingPrincipleId || "").trim();
    if (!subsuming) {
      return NextResponse.json(
        { error: "subsumingPrincipleId is required" },
        { status: 400 },
      );
    }
    if (!lifecycle || !lifecycle.pendingSubsumptionPrincipleId) {
      return NextResponse.json(
        { error: "no pending subsumption candidate to accept" },
        { status: 409 },
      );
    }
    if (lifecycle.pendingSubsumptionPrincipleId !== subsuming) {
      return NextResponse.json(
        { error: "subsumingPrincipleId does not match the pending candidate" },
        { status: 409 },
      );
    }
    const now = new Date();
    events.push({
      at: now.toISOString(),
      status_before: lifecycle.currentStatus,
      status_after: "SUBSUMED_BY_SYNTHESIS",
      rationale: `founder (${tenant.founderId}) confirmed synthesis principle ${subsuming} subsumes both sides`,
      triggering_source_ids: [subsuming],
      supported_principle_id: null,
      subsuming_principle_id: subsuming,
      score_change: null,
    });
    const updated = await db.contradictionLifecycle.update({
      where: { contradictionId: id },
      data: {
        currentStatus: "SUBSUMED_BY_SYNTHESIS",
        lastTransitionAt: now,
        eventsJson: JSON.stringify(events),
        subsumingPrincipleId: subsuming,
        pendingSubsumptionPrincipleId: null,
      },
    });
    await db.auditEvent.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        action: "contradiction_subsumption_accepted",
        detail: JSON.stringify({
          contradictionId: id,
          subsumingPrincipleId: subsuming,
        }),
      },
    });
    return NextResponse.json({ ok: true, lifecycle: updated });
  }

  // REJECT-SUBSUMPTION → clear candidate, status stays
  if (body.action === "reject-subsumption") {
    if (!lifecycle || !lifecycle.pendingSubsumptionPrincipleId) {
      return NextResponse.json(
        { error: "no pending subsumption candidate to reject" },
        { status: 409 },
      );
    }
    const now = new Date();
    const candidate = lifecycle.pendingSubsumptionPrincipleId;
    events.push({
      at: now.toISOString(),
      status_before: lifecycle.currentStatus,
      status_after: lifecycle.currentStatus,
      rationale: `founder (${tenant.founderId}) rejected synthesis candidate ${candidate}${
        body.reason ? `: ${body.reason.trim()}` : ""
      }`,
      triggering_source_ids: [candidate],
      supported_principle_id: lifecycle.supportedPrincipleId,
      subsuming_principle_id: null,
      score_change: null,
    });
    const updated = await db.contradictionLifecycle.update({
      where: { contradictionId: id },
      data: {
        lastTransitionAt: now,
        eventsJson: JSON.stringify(events),
        pendingSubsumptionPrincipleId: null,
      },
    });
    await db.auditEvent.create({
      data: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        action: "contradiction_subsumption_rejected",
        detail: JSON.stringify({
          contradictionId: id,
          candidatePrincipleId: candidate,
          reason: body.reason || null,
        }),
      },
    });
    return NextResponse.json({ ok: true, lifecycle: updated });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}

function parseEvents(raw: string | null): Array<Record<string, unknown>> {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as Array<Record<string, unknown>>;
  } catch {
    /* fall through */
  }
  return [];
}
