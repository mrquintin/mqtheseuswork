import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";

/**
 * GET /api/upload/:id — poll status and streamed process log.
 */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { id } = await params;

  const upload = await db.upload.findFirst({
    // `deletedAt: null` hides soft-deleted rows from the polling UI —
    // the row still exists in the DB (for audit) but is no longer
    // surfaced to any founder or the public blog.
    //
    // Private rows are also filtered so a peer can't hit this endpoint
    // with a guessed id and read the content. The owner still sees
    // their own private rows (the `OR` clause below).
    where: {
      id,
      organizationId: founder.organizationId,
      deletedAt: null,
      OR: [
        { visibility: { not: "private" } },
        { founderId: founder.id },
      ],
    },
    select: {
      id: true,
      founderId: true,
      organizationId: true,
      title: true,
      status: true,
      processLog: true,
      claimsCount: true,
      methodCount: true,
      substCount: true,
      principleCount: true,
      errorMessage: true,
      slug: true,
      publishedAt: true,
      createdAt: true,
      updatedAt: true,
    },
  });

  if (!upload) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const sameOrg = upload.organizationId === founder.organizationId;
  if (!sameOrg) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  if (upload.founderId !== founder.id && founder.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // Derive a publicUrl when the upload has been published. The slug is
  // stable (we never rewrite it once assigned), so the public URL can
  // be constructed deterministically without another DB lookup. The
  // client uses this to render a "view post" link on successfully
  // ingested rows in the upload queue.
  const publicUrl =
    upload.publishedAt && upload.slug ? `/post/${upload.slug}` : null;

  return NextResponse.json({ ...upload, publicUrl });
}
