import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Per-founder dashboard dismissal. Hides a conclusion from the current
 * founder's homepage only; other founders in the same org still see it.
 * This is a UI preference, not a deletion — the conclusion row remains
 * in the firm's canon and shows up everywhere else (e.g. /conclusions).
 *
 * The server action on /dashboard writes directly via Prisma; this HTTP
 * endpoint exists for parity (scripts, future clients) and uses the
 * same upsert-on-unique-constraint trick to stay idempotent.
 */
export async function POST(req: Request) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (!canWrite(tenant.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }

  const body = (await req.json().catch(() => ({}))) as {
    conclusionId?: string;
  };
  const { conclusionId } = body;
  if (!conclusionId) {
    return NextResponse.json(
      { error: "conclusionId required" },
      { status: 400 },
    );
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
