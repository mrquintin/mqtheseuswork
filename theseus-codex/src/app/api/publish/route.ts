/**
 * Toggle a previously-created Upload between published (public blog
 * post) and unpublished (private founder artifact).
 *
 * POST body:
 *   { upload_id: string, publish: boolean, blogExcerpt?: string,
 *     authorBio?: string }
 *
 * Auth: session cookie OR Bearer API key. The upload must belong to
 * the caller's organization.
 *
 * Side effects:
 *   - `publish=true`: sets publishedAt=now(), mints a slug if the row
 *     doesn't have one yet. Re-publishing preserves the existing slug
 *     so external links don't break.
 *   - `publish=false`: clears publishedAt but KEEPS slug so that if
 *     the founder re-publishes later the same URL still works. (The
 *     public index filter is `publishedAt IS NOT NULL`, so a cleared
 *     timestamp is sufficient to hide the post.)
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { sanitizeAndCap } from "@/lib/sanitizeText";
import { pickAvailableSlug } from "@/lib/slugify";

export async function POST(req: Request) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }

    const body = (await req.json().catch(() => ({}))) as {
      upload_id?: string;
      uploadId?: string;
      publish?: boolean;
      blogExcerpt?: string;
      authorBio?: string;
    };
    const uploadId = body.upload_id || body.uploadId;
    if (!uploadId) {
      return NextResponse.json(
        { error: "upload_id is required" },
        { status: 400 },
      );
    }
    if (typeof body.publish !== "boolean") {
      return NextResponse.json(
        { error: "publish (boolean) is required" },
        { status: 400 },
      );
    }

    const existing = await db.upload.findUnique({
      where: { id: uploadId },
      select: {
        id: true,
        organizationId: true,
        title: true,
        slug: true,
        publishedAt: true,
      },
    });
    if (!existing) {
      return NextResponse.json({ error: "Upload not found" }, { status: 404 });
    }
    if (existing.organizationId !== founder.organizationId) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    if (body.publish) {
      // Generate a slug only if the row doesn't already have one. On
      // re-publish we keep the old URL so shares continue to resolve.
      let slug = existing.slug;
      if (!slug) {
        slug = await pickAvailableSlug(existing.title, async (candidate) => {
          const other = await db.upload.findUnique({
            where: { slug: candidate },
            select: { id: true },
          });
          return other !== null && other.id !== existing.id;
        });
      }
      const updated = await db.upload.update({
        where: { id: uploadId },
        data: {
          publishedAt: new Date(),
          slug,
          blogExcerpt: body.blogExcerpt
            ? sanitizeAndCap(body.blogExcerpt, 400)
            : undefined, // leave unchanged if omitted
          authorBio: body.authorBio
            ? sanitizeAndCap(body.authorBio, 160)
            : undefined,
        },
        select: {
          id: true,
          slug: true,
          publishedAt: true,
        },
      });
      await db.auditEvent
        .create({
          data: {
            organizationId: founder.organizationId,
            founderId: founder.id,
            uploadId,
            action: "publish",
            detail: `published as /post/${updated.slug}`,
          },
        })
        .catch(() => {});
      return NextResponse.json({
        ok: true,
        slug: updated.slug,
        publishedAt: updated.publishedAt,
        publicUrl: `/post/${updated.slug}`,
      });
    }

    // Unpublish — clear timestamp, keep slug.
    await db.upload.update({
      where: { id: uploadId },
      data: { publishedAt: null },
    });
    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId,
          action: "unpublish",
          detail: `unpublished${existing.slug ? ` (was /post/${existing.slug})` : ""}`,
        },
      })
      .catch(() => {});
    return NextResponse.json({
      ok: true,
      slug: existing.slug,
      publishedAt: null,
      publicUrl: null,
    });
  } catch (error) {
    console.error("publish error:", error);
    return NextResponse.json(
      {
        error:
          `Publish toggle failed: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
