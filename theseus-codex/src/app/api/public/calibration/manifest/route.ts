import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { withApiHandler } from "@/lib/api/handler";
import {
  PUBLIC_CALIBRATION_SCHEMA_VERSION,
  type CalibrationFilter,
  loadPublicCalibrationManifest,
} from "@/lib/calibrationData";
import { publicCorsHeaders } from "@/lib/publicCors";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public calibration manifest endpoint.
 *
 * Returns the full data backing `/calibration` so external auditors can
 * verify the published numbers without running the firm's tooling.
 * Schema version surfaces both as `meta.schemaVersion` (canonical) and
 * the `X-Schema-Version` header (mirror for cache-key consumers).
 *
 * Honest-by-construction: the SHA-256 `resolutionSetHash` over the
 * canonicalized resolved-prediction set appears both in `data` and as
 * the `X-Resolution-Set-Hash` response header — a discrepancy with the
 * `/calibration` page is detectable from the headers alone.
 *
 * Optional filters (URL query params): `domain`, `method`, `version`.
 *
 * Legacy alias: `X-Theseus-Envelope: legacy` or `?envelope=legacy`
 * returns the raw manifest body during the migration window.
 */
export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  return new NextResponse(null, { status: 204, headers });
}

export const GET = withApiHandler(
  async (req) => {
    const url = new URL(req.url);
    const filter: CalibrationFilter = {
      domain: url.searchParams.get("domain"),
      methodName: url.searchParams.get("method"),
      methodVersion: url.searchParams.get("version"),
    };
    const manifest = await loadPublicCalibrationManifest(filter);
    return {
      data: manifest,
      meta: {
        schemaVersion: manifest.schemaVersion ?? PUBLIC_CALIBRATION_SCHEMA_VERSION,
        generatedAt: manifest.generatedAt,
      },
      legacy: manifest,
      headers: {
        "Cache-Control": "public, max-age=60, s-maxage=300",
        "X-Resolution-Set-Hash": manifest.resolutionSetHash,
        "X-Schema-Version": String(manifest.schemaVersion ?? PUBLIC_CALIBRATION_SCHEMA_VERSION),
      },
    };
  },
  { cors: true, corsMethods: "GET, OPTIONS" },
);
