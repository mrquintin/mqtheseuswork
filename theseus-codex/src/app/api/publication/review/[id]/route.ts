import { NextResponse } from "next/server";
import { revalidatePath, revalidateTag } from "next/cache";

import { getFounder } from "@/lib/auth";
import { applyPublicationReviewAction, type PublicationReviewAction } from "@/lib/publicationService";
import {
  PUBLIC_HOME_ARTICLES_TAG,
  PUBLIC_HOME_CONCLUSIONS_TAG,
} from "@/lib/publicSurface";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";

// Homepage SLO: every published article / conclusion shows up on `/`
// within 60 seconds. Publication review is the only path that mints a
// new PublishedConclusion row, so this is where we tell Next.js to
// blow away its homepage cache. Documented in
// `docs/operator/public_surfacing.md`.
function revalidateHomepageAfterPublish(slug: string | undefined) {
  try {
    revalidatePath("/");
  } catch {
    /* best-effort */
  }
  if (slug) {
    try {
      revalidatePath(`/c/${slug}`);
    } catch {
      /* best-effort */
    }
  }
  try {
    revalidateTag(PUBLIC_HOME_ARTICLES_TAG, "default");
  } catch {
    /* best-effort */
  }
  try {
    revalidateTag(PUBLIC_HOME_CONCLUSIONS_TAG, "default");
  } catch {
    /* best-effort */
  }
}

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
    if (body.action === "publish") {
      const slug = typeof result.slug === "string" ? result.slug : undefined;
      revalidateHomepageAfterPublish(slug);
    }
    return NextResponse.json(result);
  } catch (e) {
    const message = e instanceof Error ? e.message : "review action failed";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
