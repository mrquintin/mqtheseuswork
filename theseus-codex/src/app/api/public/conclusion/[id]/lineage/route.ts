import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { db } from "@/lib/db";
import { filterPublic } from "@/lib/lineage";
import { assembleLineage } from "@/lib/lineage-server";
import { publicCorsHeaders } from "@/lib/publicCors";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public lineage for a conclusion.
 *
 * Strategy:
 *   1. Resolve the conclusion id → organisation via PublishedConclusion.
 *      Only conclusions that have an associated published snapshot are
 *      addressable here; an unpublished id 404s rather than leaking that
 *      a private record exists.
 *   2. Assemble the full lineage and apply `filterPublic()`. Private
 *      nodes (drift, revision, peer review, unpublished methodology) are
 *      dropped — not redacted — so the JSON shape never gestures at them.
 *
 * No auth, read-only. CORS open to the public origin; cache-control
 * mirrors the methodology manifest (60s edge / 5min CDN).
 */

export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  return new NextResponse(null, { status: 204, headers });
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const corsHeaders = new Headers(publicCorsHeaders(req));
  corsHeaders.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  const { id } = await ctx.params;

  // Address the conclusion either by its own id OR by a published-
  // conclusion slug — the founder UI links by id, the public site by slug.
  const direct = await db.publishedConclusion.findFirst({
    where: { sourceConclusionId: id },
    select: { organizationId: true, sourceConclusionId: true },
    orderBy: { publishedAt: "desc" },
  });
  const viaSlug = direct
    ? null
    : await db.publishedConclusion.findFirst({
        where: { slug: id },
        select: { organizationId: true, sourceConclusionId: true },
        orderBy: { publishedAt: "desc" },
      });
  const target = direct ?? viaSlug;
  if (!target) {
    return NextResponse.json(
      { error: "Not found" },
      { status: 404, headers: corsHeaders },
    );
  }

  try {
    const full = await assembleLineage({
      conclusionId: target.sourceConclusionId,
      organizationId: target.organizationId,
    });
    const headers = new Headers(corsHeaders);
    headers.set("Cache-Control", "public, max-age=60, s-maxage=300");
    headers.set("Content-Type", "application/json");
    return NextResponse.json(filterPublic(full), { status: 200, headers });
  } catch (err) {
    const status = (err as { status?: number })?.status ?? 500;
    if (status === 404) {
      return NextResponse.json(
        { error: "Not found" },
        { status: 404, headers: corsHeaders },
      );
    }
    console.error("[public lineage] failed:", err);
    return NextResponse.json(
      { error: "lineage_unavailable" },
      { status: 500, headers: corsHeaders },
    );
  }
}
