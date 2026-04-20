import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Mark a conclusion as dismissed from *this* founder's dashboard.
 * No effect on other founders or on the conclusion itself — it's a
 * pure per-user UI preference.
 */
export async function POST(req: Request) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { conclusionId } = (await req.json()) as { conclusionId?: string };
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

  await db.dashboardDismissal.upsert({
    where: {
      founderId_conclusionId: {
        founderId: tenant.founderId,
        conclusionId,
      },
    },
    update: {},
    create: {
      founderId: tenant.founderId,
      conclusionId,
    },
  });

  return NextResponse.json({ ok: true });
}

export async function DELETE(req: Request) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { conclusionId } = (await req.json()) as { conclusionId?: string };
  if (!conclusionId) {
    return NextResponse.json({ error: "conclusionId required" }, { status: 400 });
  }
  await db.dashboardDismissal.deleteMany({
    where: {
      founderId: tenant.founderId,
      conclusionId,
    },
  });
  return NextResponse.json({ ok: true });
}
