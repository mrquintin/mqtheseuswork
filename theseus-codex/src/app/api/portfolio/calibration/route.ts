import type { NextRequest } from "next/server";

import { proxyToForecasts } from "@/lib/forecastsApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  return proxyToForecasts(req, "/v1/portfolio/calibration");
}
