import { NextResponse, type NextRequest } from "next/server";

import {
  calibrationSeries,
  getPublicAlgorithm,
  listInvocationsForAlgorithm,
} from "@/lib/algorithmsPublicApi";
import { getFounder } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const founder = await getFounder().catch(() => null);
  const organizationId =
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    "";
  if (!organizationId) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  const algorithm = await getPublicAlgorithm(organizationId, id);
  if (!algorithm) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  const limitRaw = req.nextUrl.searchParams.get("invocationsLimit");
  const limit = (() => {
    const n = Number(limitRaw ?? "20");
    if (!Number.isFinite(n)) return 20;
    return Math.max(1, Math.min(200, Math.floor(n)));
  })();
  const invocations = await listInvocationsForAlgorithm(id, limit);
  const allInvocations = await listInvocationsForAlgorithm(id, 500);
  return NextResponse.json({
    algorithm,
    invocations,
    calibration: calibrationSeries(allInvocations),
  });
}
