import type { NextRequest } from "next/server";

import { proxyToForecastsOperator } from "@/lib/forecastsOperatorApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return proxyToForecastsOperator(
    req,
    `/v1/operator/forecasts/${encodeURIComponent(id)}/authorize-live`,
    { method: "POST" },
  );
}
