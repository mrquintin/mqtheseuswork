import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { updateReadingQueueStatus } from "@/lib/noosphereLiteratureBridge";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";

const ALLOWED = new Set(["queued", "reading", "engaged", "not_relevant", "skipped"]);

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // Reading-queue status (queued / reading / engaged / not_relevant /
  // skipped) is shared org state — viewers see it but don't change
  // the shared collective workflow.
  if (!canWrite(founder.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
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
