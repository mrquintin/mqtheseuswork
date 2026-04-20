import { NextResponse } from "next/server";

import { getFounder } from "@/lib/auth";
import { enqueuePublicationReview, listPublicationQueue } from "@/lib/publicationService";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";

export async function GET() {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const reviews = await listPublicationQueue(founder.organizationId);
  return NextResponse.json({ reviews });
}

export async function POST(req: Request) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // Enqueueing for publication review is a write — viewers can see
  // the queue (GET above) but can't add to it.
  if (!canWrite(founder.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }

  const body = (await req.json().catch(() => null)) as { conclusionId?: string } | null;
  if (!body?.conclusionId) {
    return NextResponse.json({ error: "conclusionId required" }, { status: 400 });
  }

  try {
    const created = await enqueuePublicationReview({
      organizationId: founder.organizationId,
      conclusionId: body.conclusionId,
    });
    return NextResponse.json(created);
  } catch (e) {
    const message = e instanceof Error ? e.message : "enqueue failed";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
