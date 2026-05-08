import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { buildMethodologyManifest } from "@/lib/methodologyManifest";
import { publicCorsHeaders } from "@/lib/publicCors";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public methodology manifest endpoint.
 *
 * Returns the public-visible methodology graph: methods, edges,
 * public failure modes, and publish-gated track records. Stable
 * schema versioned via the top-level `v` field — pin against it.
 *
 * No authentication, read-only. Visibility is enforced upstream in
 * `buildMethodologyManifest` (public failure modes only,
 * published-conclusion join, MIN_PUBLISHABLE_SAMPLE gate). Do not add
 * organization-scoped fields here.
 */
export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  return new NextResponse(null, { status: 204, headers });
}

export async function GET(req: NextRequest) {
  const corsHeaders = new Headers(publicCorsHeaders(req));
  corsHeaders.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  try {
    const manifest = await buildMethodologyManifest();
    const headers = new Headers(corsHeaders);
    headers.set("Cache-Control", "public, max-age=60, s-maxage=300");
    headers.set("Content-Type", "application/json");
    return NextResponse.json(manifest, { status: 200, headers });
  } catch (error) {
    console.error("[public methodology manifest] failed:", error);
    return NextResponse.json(
      { error: "manifest unavailable" },
      { status: 500, headers: corsHeaders },
    );
  }
}
