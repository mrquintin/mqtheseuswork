import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { db } from "@/lib/db";
import { publicCorsHeaders } from "@/lib/publicCors";
import { createCritique } from "@/lib/critiquesApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const RATE_LIMIT_WINDOW_MS = 24 * 60 * 60 * 1000;
const RATE_LIMIT_MAX = 5;

export function OPTIONS(req: NextRequest) {
  return new NextResponse(null, { status: 204, headers: publicCorsHeaders(req) });
}

type CritiqueBody = {
  articleSlug?: string;
  publishedConclusionId?: string | null;
  targetClaim?: string;
  counterEvidence?: string;
  derivationMethod?: string;
  citations?: string;
  submitterEmail?: string;
  displayName?: string;
  publicUrl?: string;
  bio?: string;
  orcid?: string;
};

export async function POST(req: NextRequest) {
  const cors = publicCorsHeaders(req);
  const body = (await req.json().catch(() => null)) as CritiqueBody | null;
  if (!body) {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400, headers: cors });
  }

  const slug = String(body.articleSlug ?? "").trim();
  if (!slug) {
    return NextResponse.json({ error: "articleSlug is required" }, { status: 400, headers: cors });
  }

  // Resolve the article's organization. Critiques can target either a
  // PublishedConclusion (slug + version unique) or a generated-article
  // post (Upload.slug, also unique). We try both in order.
  let organizationId: string | null = null;
  let publishedConclusionId: string | null = null;

  if (body.publishedConclusionId) {
    const pub = await db.publishedConclusion.findFirst({
      where: { id: String(body.publishedConclusionId) },
      select: { id: true, organizationId: true, slug: true },
    });
    if (pub) {
      organizationId = pub.organizationId;
      publishedConclusionId = pub.id;
    }
  }

  if (!organizationId) {
    const pub = await db.publishedConclusion.findFirst({
      where: { slug },
      orderBy: { version: "desc" },
      select: { id: true, organizationId: true },
    });
    if (pub) {
      organizationId = pub.organizationId;
      publishedConclusionId = pub.id;
    }
  }

  if (!organizationId) {
    const upload = await db.upload.findFirst({
      where: { slug },
      select: { organizationId: true },
    });
    if (upload) organizationId = upload.organizationId;
  }

  if (!organizationId) {
    return NextResponse.json(
      { error: "Unknown article" },
      { status: 404, headers: cors },
    );
  }

  const submitterEmail = String(body.submitterEmail ?? "").trim();
  if (!submitterEmail.includes("@")) {
    return NextResponse.json(
      { error: "submitterEmail is required" },
      { status: 400, headers: cors },
    );
  }

  const recentCount = await db.critiqueSubmission.count({
    where: {
      organizationId,
      submitterEmail,
      createdAt: { gte: new Date(Date.now() - RATE_LIMIT_WINDOW_MS) },
    },
  });
  if (recentCount >= RATE_LIMIT_MAX) {
    return NextResponse.json(
      { error: "Rate limit exceeded. Try again later." },
      { status: 429, headers: cors },
    );
  }

  try {
    const row = await createCritique({
      organizationId,
      articleSlug: slug,
      publishedConclusionId,
      targetClaim: String(body.targetClaim ?? ""),
      counterEvidence: String(body.counterEvidence ?? ""),
      derivationMethod: String(body.derivationMethod ?? ""),
      citations: String(body.citations ?? ""),
      submitterEmail,
      displayName: String(body.displayName ?? ""),
      publicUrl: String(body.publicUrl ?? ""),
      bio: String(body.bio ?? ""),
      orcid: String(body.orcid ?? ""),
    });
    return NextResponse.json({ ok: true, id: row.id }, { status: 200, headers: cors });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to record critique";
    return NextResponse.json({ error: message }, { status: 400, headers: cors });
  }
}
