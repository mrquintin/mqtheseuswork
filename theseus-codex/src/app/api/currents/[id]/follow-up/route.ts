import type { NextRequest } from "next/server";

import { passThroughHeaders, proxyToCurrents } from "@/lib/currentsApi";
import { fingerprintFor } from "@/lib/currentsFingerprint";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const headers = passThroughHeaders(req);
  headers.set("x-client-id", fingerprintFor(req));

  return proxyToCurrents(req, `/v1/currents/${encodeURIComponent(id)}/follow-up`, {
    method: "POST",
    headers,
    body: req.body,
    sse: true,
  });
}
