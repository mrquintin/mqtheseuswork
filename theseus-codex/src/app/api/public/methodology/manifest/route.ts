import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { withApiHandler } from "@/lib/api/handler";
import {
  MANIFEST_SCHEMA_VERSION,
  buildMethodologyManifest,
} from "@/lib/methodologyManifest";
import { publicCorsHeaders } from "@/lib/publicCors";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public methodology manifest endpoint.
 *
 * Returns the public-visible methodology graph: methods, edges,
 * public failure modes, and publish-gated track records. Stable
 * schema versioned via `meta.schemaVersion` — pin against it.
 *
 * No authentication, read-only. Visibility is enforced upstream in
 * `buildMethodologyManifest` (public failure modes only,
 * published-conclusion join, MIN_PUBLISHABLE_SAMPLE gate).
 *
 * Legacy alias (Round 17 → unified envelope migration): callers can
 * pass `X-Theseus-Envelope: legacy` or `?envelope=legacy` to receive
 * the raw manifest body during the one-week deprecation window. The
 * legacy response carries `Deprecation: true`.
 */
export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  return new NextResponse(null, { status: 204, headers });
}

export const GET = withApiHandler(
  async () => {
    const manifest = await buildMethodologyManifest();
    return {
      data: manifest,
      meta: {
        schemaVersion: MANIFEST_SCHEMA_VERSION,
        generatedAt: manifest.generatedAt,
      },
      legacy: manifest,
      headers: {
        "Cache-Control": "public, max-age=60, s-maxage=300",
      },
    };
  },
  { cors: true, corsMethods: "GET, OPTIONS" },
);
