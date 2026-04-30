import type { NextRequest } from "next/server";

import { proxyToForecasts } from "@/lib/forecastsApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return proxyToForecasts(req, `/v1/forecasts/${encodeURIComponent(id)}/resolution`);
}
