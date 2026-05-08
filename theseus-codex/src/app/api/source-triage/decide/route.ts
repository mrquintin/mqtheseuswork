import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";

const ALLOWED = new Set(["confirmed", "overridden", "dismissed"]);

export async function POST(req: NextRequest) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const form = await req.formData();
  const id = (form.get("id") as string | null)?.trim();
  const decision = (form.get("decision") as string | null)?.trim();
  const note = ((form.get("note") as string | null) ?? "").toString();

  if (!id || !decision || !ALLOWED.has(decision)) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }

  const item = await db.sourceTriageItem.findUnique({ where: { id } });
  if (!item || item.organizationId !== founder.organizationId) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  if (item.decision !== "pending") {
    return NextResponse.json({ error: "already_decided" }, { status: 409 });
  }

  await db.sourceTriageItem.update({
    where: { id },
    data: {
      decision,
      decisionNote: note || null,
      decidedById: founder.id,
      decidedAt: new Date(),
    },
  });

  return NextResponse.redirect(new URL("/source-triage", req.url), 303);
}
