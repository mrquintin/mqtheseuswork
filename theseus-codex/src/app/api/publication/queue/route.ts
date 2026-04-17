import { NextResponse } from "next/server";

import { getFounder } from "@/lib/auth";
import { enqueuePublicationReview, listPublicationQueue } from "@/lib/publicationService";

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
