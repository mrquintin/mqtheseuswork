import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
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
 * Schema is versioned via the top-level `schemaVersion` field — pin
 * against it.
 *
 * Honest-by-construction: includes the SHA-256 `resolutionSetHash` over
 * the canonicalized resolved-prediction set. The same hash that appears
 * on the page appears here, so a discrepancy is detectable.
 *
 * Optional filters (URL query params): `domain`, `method`, `version`.
 * Filters narrow the decile views; aggregate Brier and the reliability
 * curve come from the published nightly manifest as-is so the public
 * cohort cannot be sliced into vanity subsets without leaving a trail.
 */
export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  return new NextResponse(null, { status: 204, headers });
}

export async function GET(req: NextRequest) {
  const corsHeaders = new Headers(publicCorsHeaders(req));
  corsHeaders.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  const url = new URL(req.url);
  const filter: CalibrationFilter = {
    domain: url.searchParams.get("domain"),
    methodName: url.searchParams.get("method"),
    methodVersion: url.searchParams.get("version"),
  };
  try {
    const manifest = await loadPublicCalibrationManifest(filter);
    const headers = new Headers(corsHeaders);
    headers.set("Cache-Control", "public, max-age=60, s-maxage=300");
    headers.set("Content-Type", "application/json");
    headers.set("X-Resolution-Set-Hash", manifest.resolutionSetHash);
    headers.set("X-Schema-Version", String(manifest.schemaVersion));
    return NextResponse.json(manifest, { status: 200, headers });
  } catch (error) {
    console.error("[public calibration manifest] failed:", error);
    return NextResponse.json(
      { error: "manifest unavailable" },
      { status: 500, headers: corsHeaders },
    );
  }
}
