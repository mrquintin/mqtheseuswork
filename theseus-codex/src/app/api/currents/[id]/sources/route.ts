import type { NextRequest } from "next/server";

import { proxyToCurrents } from "@/lib/currentsApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return proxyToCurrents(req, `/v1/currents/${encodeURIComponent(id)}/sources`);
}
