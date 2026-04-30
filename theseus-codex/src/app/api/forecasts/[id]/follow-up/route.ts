import type { NextRequest } from "next/server";

import { passThroughHeadersWithFingerprint, proxyToForecasts } from "@/lib/forecastsApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;

  return proxyToForecasts(req, `/v1/forecasts/${encodeURIComponent(id)}/follow-up`, {
    method: "POST",
    headers: passThroughHeadersWithFingerprint(req),
    body: req.body,
    sse: true,
  });
}
