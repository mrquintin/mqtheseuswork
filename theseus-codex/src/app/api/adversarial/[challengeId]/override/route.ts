import { Prisma } from "@prisma/client";
import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";

type AdvRow = { payload_json: string; conclusion_id: string };

export async function POST(
  req: Request,
  { params }: { params: Promise<{ challengeId: string }> },
) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // Human override on an adversarial challenge can demote a
  // conclusion to "open" tier — clear corpus mutation that viewers
  // shouldn't have access to.
  if (!canWrite(founder.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }

  const { challengeId } = await params;
  const body = (await req.json()) as {
    kind?: "addressed" | "fatal";
    pointer?: string;
    notes?: string;
  };

  if (!body.kind || !["addressed", "fatal"].includes(body.kind)) {
    return NextResponse.json({ error: "kind must be addressed or fatal" }, { status: 400 });
  }

  const found = await db.$queryRaw<AdvRow[]>(Prisma.sql`
    SELECT payload_json, conclusion_id FROM adversarial_challenge WHERE id = ${challengeId} LIMIT 1
  `);
  const row = found[0];
  if (!row) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(row.payload_json) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid stored payload" }, { status: 500 });
  }

  payload.human_override = {
    kind: body.kind,
    pointer: body.pointer || "",
    notes: body.notes || "",
    founder_label: founder.name,
  };
  payload.status = body.kind === "addressed" ? "addressed" : "fatal";

  const outJson = JSON.stringify(payload);
  const isPg = Boolean(process.env.DATABASE_URL?.startsWith("postgresql"));
  if (isPg) {
    await db.$executeRawUnsafe(
      `UPDATE adversarial_challenge SET payload_json = $1::jsonb, updated_at = NOW() WHERE id = $2`,
      outJson,
      challengeId,
    );
  } else {
    await db.$executeRaw(
      Prisma.sql`UPDATE adversarial_challenge SET payload_json = ${outJson}, updated_at = datetime('now') WHERE id = ${challengeId}`,
    );
  }

  if (body.kind === "fatal" && row.conclusion_id) {
    const cons = await db.conclusion.findFirst({
      where: {
        organizationId: founder.organizationId,
        OR: [{ noosphereId: row.conclusion_id }, { id: row.conclusion_id }],
      },
    });
    if (cons) {
      const rationale = `${cons.rationale || ""} | adversarial_human_fatal (${challengeId})`.trim();
      await db.conclusion.update({
        where: { id: cons.id },
        data: { confidenceTier: "open", rationale: rationale.slice(0, 8000) },
      });
    }
  }

  return NextResponse.json({ ok: true });
}
