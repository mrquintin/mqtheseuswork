/**
 * GET /api/library — org-wide upload inventory.
 *
 * Every founder in the org can see every upload (public transparency
 * into the firm's collective input). Per-row ownership + request state
 * is included so the UI can decide whether to render "Delete" (owner)
 * vs. "Request deletion" (non-owner).
 *
 * Filters supported via query params:
 *   ?q=           free-text match on title / originalName (case-insensitive)
 *   ?author=      restrict to uploads by a specific founderId
 *   ?published=1  only published posts
 *   ?status=      upload status ("pending" | "processing" | "queued_offline"
 *                 | "ingested" | "failed")
 *
 * Deleted rows never appear here — the whole point of soft-delete is
 * that they're invisible on every surface.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";

export async function GET(req: Request) {
  const founder = await getFounderFromAuth(req);
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const url = new URL(req.url);
  const q = (url.searchParams.get("q") || "").trim();
  const author = (url.searchParams.get("author") || "").trim();
  const published = url.searchParams.get("published");
  const status = (url.searchParams.get("status") || "").trim();

  const where: Record<string, unknown> = {
    organizationId: founder.organizationId,
    deletedAt: null,
  };
  if (author) where.founderId = author;
  if (status) where.status = status;
  if (published === "1") where.publishedAt = { not: null };
  if (q) {
    where.OR = [
      { title: { contains: q, mode: "insensitive" } },
      { originalName: { contains: q, mode: "insensitive" } },
      { description: { contains: q, mode: "insensitive" } },
    ];
  }

  const uploads = await db.upload.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 250, // library is a browsing surface — 250 rows is plenty
    select: {
      id: true,
      title: true,
      originalName: true,
      sourceType: true,
      mimeType: true,
      fileSize: true,
      status: true,
      publishedAt: true,
      slug: true,
      createdAt: true,
      founderId: true,
      founder: { select: { id: true, name: true } },
      deletionRequests: {
        where: { status: "pending" },
        select: {
          id: true,
          status: true,
          reason: true,
          createdAt: true,
          requesterId: true,
          requester: { select: { id: true, name: true } },
        },
      },
    },
  });

  // Convenience: annotate each row with `youOwn` + whether `you`ve
  // already raised a request on this upload (avoid UI double-dispatch).
  const rows = uploads.map((u) => ({
    ...u,
    youOwn: u.founderId === founder.id,
    yourPendingRequestId:
      u.deletionRequests.find((r) => r.requesterId === founder.id)?.id || null,
  }));

  return NextResponse.json({
    you: { id: founder.id, name: founder.name },
    count: rows.length,
    rows,
  });
}
