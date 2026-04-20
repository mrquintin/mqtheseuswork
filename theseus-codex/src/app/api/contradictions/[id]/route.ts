import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { id } = await ctx.params;
  const body = (await req.json()) as {
    action?: "resolve" | "dismiss";
    resolution?: string;
  };
  if (body.action !== "resolve" && body.action !== "dismiss") {
    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  }

  const existing = await db.contradiction.findFirst({
    where: { id, organizationId: tenant.organizationId },
    select: { id: true, status: true },
  });
  if (!existing) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const newStatus = body.action === "resolve" ? "resolved" : "dismissed";

  const updated = await db.contradiction.update({
    where: { id },
    data: {
      status: newStatus,
      resolution: body.resolution || null,
      resolvedById: tenant.founderId,
      resolvedAt: new Date(),
    },
  });

  await db.auditEvent.create({
    data: {
      organizationId: tenant.organizationId,
      founderId: tenant.founderId,
      action:
        body.action === "resolve"
          ? "contradiction_resolved"
          : "contradiction_dismissed",
      detail: JSON.stringify({
        contradictionId: id,
        resolution: body.resolution || null,
      }),
    },
  });

  return NextResponse.json({ ok: true, contradiction: updated });
}
