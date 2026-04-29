import type { NextRequest } from "next/server";

import { proxyToCurrents } from "@/lib/currentsApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ id: string; session: string }> },
) {
  const { id, session } = await ctx.params;
  return proxyToCurrents(
    req,
    `/v1/currents/${encodeURIComponent(id)}/follow-up/${encodeURIComponent(session)}/messages`,
  );
}
