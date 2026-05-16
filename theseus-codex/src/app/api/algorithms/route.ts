import { NextResponse, type NextRequest } from "next/server";

import {
  listPublicAlgorithms,
  type ListPublicAlgorithmsParams,
  type PublicAlgorithmStatus,
} from "@/lib/algorithmsPublicApi";
import { getFounder } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public list endpoint backing the `/algorithms` index page.
 *
 * Anonymous reads are served against the founder's organisation — the
 * surface is single-tenant in spirit, but the route still resolves the
 * org ID through the tenant context so a future multi-tenant
 * deployment can swap the resolver without touching the page.
 */
export async function GET(req: NextRequest) {
  const founder = await getFounder().catch(() => null);
  // The public page resolves the organisation via the auth helper for
  // founder-authenticated browsers, and falls back to the
  // PUBLIC_ORGANIZATION_ID env for anonymous reads.
  const organizationId =
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    "";
  if (!organizationId) {
    return NextResponse.json({ algorithms: [] });
  }

  const params = req.nextUrl.searchParams;
  const statusRaw = params.get("status");
  let status: ListPublicAlgorithmsParams["status"] = "ACTIVE";
  if (statusRaw === "ALL") status = "ALL";
  else if (
    statusRaw === "ACTIVE" ||
    statusRaw === "PAUSED" ||
    statusRaw === "RETIRED"
  )
    status = statusRaw as PublicAlgorithmStatus;

  const algorithms = await listPublicAlgorithms(organizationId, {
    status,
    sourcePrincipleId: params.get("principle"),
  });
  return NextResponse.json({ algorithms });
}
