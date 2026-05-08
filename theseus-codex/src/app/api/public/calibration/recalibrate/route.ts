import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { publicCorsHeaders } from "@/lib/publicCors";
import { recalibrate } from "@/lib/recalibration";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public recalibration endpoint.
 *
 * `GET /api/public/calibration/recalibrate?p=<float>&domain=<str>` returns
 * the calibrated probability the public scorecard would show alongside
 * the firm's stated `p`, plus the id and fit lineage of the
 * `CalibrationModel` row used to produce it. When the domain has no
 * active model, or when the active model has fewer than
 * `THESEUS_RECALIBRATION_MIN_SAMPLES` resolutions, the response carries
 * `calibrated: null` and a status that the UI uses to render the
 * "uncalibrated — small sample" tag.
 *
 * The endpoint is read-only and always returns the raw `p` it was given,
 * even when no model is available, so the caller does not need a
 * separate fallback path.
 */
export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  return new NextResponse(null, { status: 204, headers });
}

function parseProbability(raw: string | null): number | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return null;
  if (n < 0 || n > 1) return null;
  return n;
}

export async function GET(req: NextRequest) {
  const corsHeaders = new Headers(publicCorsHeaders(req));
  corsHeaders.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  const url = new URL(req.url);
  const p = parseProbability(url.searchParams.get("p"));
  const domain = (url.searchParams.get("domain") ?? "").trim();
  const conclusionId = url.searchParams.get("conclusion_id")?.trim() || undefined;
  const organizationId = url.searchParams.get("org_id")?.trim() || undefined;
  if (p === null) {
    return NextResponse.json(
      { error: "missing_or_invalid_p", detail: "?p must be a finite probability in [0, 1]" },
      { status: 400, headers: corsHeaders },
    );
  }
  if (!domain) {
    return NextResponse.json(
      { error: "missing_domain", detail: "?domain is required — calibration is per-domain by design" },
      { status: 400, headers: corsHeaders },
    );
  }
  try {
    const result = await recalibrate(p, domain, { organizationId, conclusionId });
    const headers = new Headers(corsHeaders);
    headers.set("Content-Type", "application/json");
    headers.set("Cache-Control", "public, max-age=60, s-maxage=300");
    if (result.modelId) headers.set("X-Calibration-Model-Id", result.modelId);
    return NextResponse.json(result, { status: 200, headers });
  } catch (error) {
    console.error("[public calibration recalibrate] failed:", error);
    return NextResponse.json(
      { error: "recalibration_unavailable" },
      { status: 500, headers: corsHeaders },
    );
  }
}
