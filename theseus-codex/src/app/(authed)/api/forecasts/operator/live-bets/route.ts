import type { NextRequest } from "next/server";

import { proxyToForecastsOperator } from "@/lib/forecastsOperatorApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  return proxyToForecastsOperator(req, "/v1/operator/live-bets", { method: "GET" });
}
