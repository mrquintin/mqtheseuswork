import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { updateReadingQueueStatus } from "@/lib/noosphereLiteratureBridge";

const ALLOWED = new Set(["queued", "reading", "engaged", "not_relevant", "skipped"]);

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { id } = await params;
  let body: { status?: string; notes?: string };
  try {
    body = (await req.json()) as { status?: string; notes?: string };
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const status = body.status || "";
  if (!ALLOWED.has(status)) {
    return NextResponse.json({ error: "Invalid status" }, { status: 400 });
  }
  const r = await updateReadingQueueStatus(id, status as "queued" | "reading" | "engaged" | "not_relevant" | "skipped", body.notes);
  if (!r.ok) {
    return NextResponse.json({ error: r.error || "Noosphere update failed" }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}
