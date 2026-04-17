import { Prisma } from "@prisma/client";
import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";

type AdvRow = {
  id: string;
  conclusion_id: string;
  cluster_fingerprint: string;
  payload_json: string;
};

export async function GET() {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rows = await db.$queryRaw<AdvRow[]>(Prisma.sql`
    SELECT id, conclusion_id, cluster_fingerprint, payload_json
    FROM adversarial_challenge
    ORDER BY created_at DESC
    LIMIT 200
  `);

  const parsed = rows.map((r) => {
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(r.payload_json) as Record<string, unknown>;
    } catch {
      /* ignore */
    }
    const status = (payload.status as string) || "pending";
    const staleRaw = payload.stale_after ?? payload.staleAfter;
    const stale =
      staleRaw != null &&
      typeof staleRaw === "string" &&
      new Date(staleRaw as string).getTime() < Date.now();
    return {
      id: r.id,
      conclusionId: r.conclusion_id,
      clusterFingerprint: r.cluster_fingerprint,
      tradition: (payload.tradition as string) || "",
      objectionText: (payload.objection_text as string) || "",
      status,
      finalVerdict: (payload.final_verdict as string) || "",
      stale,
      humanOverride: payload.human_override ?? null,
    };
  });

  return NextResponse.json({ challenges: parsed });
}
