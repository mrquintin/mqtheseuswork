import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Open a "please delete this conclusion" request. Mirrors the
 * DeletionRequest flow for uploads: requester submits a reason, the
 * conclusion's attributed founder (or an admin) later accepts or
 * declines via PATCH /api/conclusion-deletion-requests/[id].
 */
export async function POST(req: Request) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (!canWrite(tenant.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }

  const body = (await req.json()) as { conclusionId?: string; reason?: string };
  const { conclusionId, reason } = body;
  if (!conclusionId) {
    return NextResponse.json({ error: "conclusionId required" }, { status: 400 });
  }

  const conclusion = await db.conclusion.findFirst({
    where: { id: conclusionId, organizationId: tenant.organizationId },
    select: { id: true },
  });
  if (!conclusion) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Prevent duplicate pending requests from the same founder for the
  // same conclusion — same rule as DeletionRequest enforces.
  const existing = await db.conclusionDeletionRequest.findFirst({
    where: {
      conclusionId,
      requesterId: tenant.founderId,
      status: "pending",
    },
  });
  if (existing) {
    return NextResponse.json(
      { error: "A pending request already exists", requestId: existing.id },
      { status: 409 },
    );
  }

  const created = await db.conclusionDeletionRequest.create({
    data: {
      conclusionId,
      requesterId: tenant.founderId,
      reason: reason || null,
    },
  });

  await db.auditEvent.create({
    data: {
      organizationId: tenant.organizationId,
      founderId: tenant.founderId,
      action: "conclusion_deletion_request",
      detail: JSON.stringify({ conclusionId, requestId: created.id, reason }),
    },
  });

  return NextResponse.json({ ok: true, requestId: created.id });
}

export async function GET() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const rows = await db.conclusionDeletionRequest.findMany({
    where: {
      conclusion: { organizationId: tenant.organizationId },
    },
    orderBy: { createdAt: "desc" },
    take: 100,
    include: {
      conclusion: { select: { id: true, text: true, attributedFounderId: true } },
      requester: { select: { id: true, name: true } },
    },
  });
  return NextResponse.json({ requests: rows });
}
