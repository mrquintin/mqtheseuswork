import { NextResponse } from "next/server";
import fs from "fs/promises";
import path from "path";
import { getFounder } from "@/lib/auth";

function reflectionsRoot(): string | null {
  const raw = process.env.DIALECTIC_REFLECTIONS_DIR?.trim();
  return raw && raw.length > 0 ? raw : null;
}

function safeSessionId(id: string): string | null {
  if (!/^[a-zA-Z0-9_-]{6,120}$/.test(id)) return null;
  return id;
}

/**
 * GET /api/sessions/:id/reflection — load `session_*_reflection.json` from DIALECTIC_REFLECTIONS_DIR.
 */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  const root = reflectionsRoot();
  if (!root) {
    return NextResponse.json(
      { error: "DIALECTIC_REFLECTIONS_DIR is not configured on this server." },
      { status: 503 },
    );
  }
  const { id } = await params;
  const sid = safeSessionId(id);
  if (!sid) {
    return NextResponse.json({ error: "Invalid session id" }, { status: 400 });
  }
  const file = path.join(root, `${sid}_reflection.json`);
  try {
    const raw = await fs.readFile(file, "utf-8");
    const data = JSON.parse(raw) as unknown;
    return NextResponse.json({ ok: true, data });
  } catch {
    return NextResponse.json({ error: "Reflection file not found" }, { status: 404 });
  }
}

/**
 * POST body: { interventionId, valueRating?: "high_value"|"low_value"|"annoying", engagement?: "engaged"|"ignored"|"dismissed" }
 */
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  const root = reflectionsRoot();
  if (!root) {
    return NextResponse.json(
      { error: "DIALECTIC_REFLECTIONS_DIR is not configured on this server." },
      { status: 503 },
    );
  }
  const { id } = await params;
  const sid = safeSessionId(id);
  if (!sid) {
    return NextResponse.json({ error: "Invalid session id" }, { status: 400 });
  }
  let body: {
    interventionId?: string;
    valueRating?: string;
    engagement?: string;
  };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  if (!body.interventionId) {
    return NextResponse.json({ error: "interventionId required" }, { status: 400 });
  }
  const file = path.join(root, `${sid}_reflection.json`);
  let raw: string;
  try {
    raw = await fs.readFile(file, "utf-8");
  } catch {
    return NextResponse.json({ error: "Reflection file not found" }, { status: 404 });
  }
  const doc = JSON.parse(raw) as {
    interventions?: Array<{
      id: string;
      value_rating?: string;
      engagement?: string;
    }>;
  };
  const rows = doc.interventions ?? [];
  const row = rows.find((r) => r.id === body.interventionId);
  if (!row) {
    return NextResponse.json({ error: "Intervention not found" }, { status: 404 });
  }
  if (body.valueRating) {
    row.value_rating = body.valueRating;
  }
  if (body.engagement) {
    row.engagement = body.engagement;
  }
  await fs.writeFile(file, JSON.stringify(doc, null, 2), "utf-8");
  return NextResponse.json({ ok: true });
}
