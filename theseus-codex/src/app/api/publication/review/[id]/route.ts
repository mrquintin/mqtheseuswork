import { NextResponse } from "next/server";

import { getFounder } from "@/lib/auth";
import { applyPublicationReviewAction, type PublicationReviewAction } from "@/lib/publicationService";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // Approving / rejecting / requesting revision on a publication
  // review is a corpus mutation — viewers can read the queue but
  // can't move items through it. (publicationService also gates on
  // role for the publish step itself; this is the outer gate.)
  if (!canWrite(founder.role)) {
    return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
  }

  const { id } = await ctx.params;
  const body = (await req.json().catch(() => null)) as PublicationReviewAction | null;
  if (!body || typeof body !== "object" || !("action" in body) || typeof body.action !== "string") {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  try {
    const result = await applyPublicationReviewAction({
      organizationId: founder.organizationId,
      founderId: founder.id,
      role: founder.role,
      reviewId: id,
      body,
    });
    return NextResponse.json(result);
  } catch (e) {
    const message = e instanceof Error ? e.message : "review action failed";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
