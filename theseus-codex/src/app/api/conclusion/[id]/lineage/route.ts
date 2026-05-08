import { NextResponse } from "next/server";

import { assembleLineage } from "@/lib/lineage";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

/**
 * Founder-only lineage for a conclusion. Returns the full Lineage —
 * private nodes included — for rendering inside the (authed) workspace.
 *
 * Auth gate: must be a signed-in member of the conclusion's organization.
 * The `requireTenantContext()` call returns null for unauthenticated
 * callers; we 401 there. The Prisma query inside `assembleLineage` is
 * scoped by `organizationId`, so a cross-tenant id surfaces as 404.
 */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { id } = await ctx.params;
  try {
    const lineage = await assembleLineage({
      conclusionId: id,
      organizationId: tenant.organizationId,
    });
    return NextResponse.json(lineage);
  } catch (err) {
    const status = (err as { status?: number })?.status ?? 500;
    if (status === 404) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json(
      { error: "lineage_assembly_failed" },
      { status: 500 },
    );
  }
}
