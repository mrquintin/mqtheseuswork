import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ApiError } from "@/lib/api/envelope";
import { withApiHandler } from "@/lib/api/handler";
import { db } from "@/lib/db";
import { publicCorsHeaders } from "@/lib/publicCors";
import { createCritique } from "@/lib/critiquesApi";
import {
  isPilotWindowOpen,
  loadPilotConfig,
  resolveReviewerSlug,
} from "@/lib/critiquePilot";

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
  /**
   * Round-17 prompt 44 pilot token. Carried by the per-reviewer
   * pre-shared link as either a body field or a `?pilot=` query
   * parameter. Unrecognized or absent tokens leave the submission
   * untagged (no silent promotion).
   */
  pilotToken?: string;
  /**
   * Explicit consent for the critic to be named on the public
   * hall-of-fame at /critiques. Pilot intake form requires opt-in
   * before any public attribution.
   */
  hallOfFameConsent?: boolean;
};

export const POST = withApiHandler<{ id: string }>(
  async (req) => {
    const body = (await req.json().catch(() => null)) as CritiqueBody | null;
    if (!body) {
      throw new ApiError("bad_json", "Invalid JSON body");
    }

    const slug = String(body.articleSlug ?? "").trim();
    if (!slug) {
      throw new ApiError("validation_error", "articleSlug is required");
    }

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
      throw new ApiError("not_found", "Unknown article");
    }

    const submitterEmail = String(body.submitterEmail ?? "").trim();
    if (!submitterEmail.includes("@")) {
      throw new ApiError("validation_error", "submitterEmail is required");
    }

    const recentCount = await db.critiqueSubmission.count({
      where: {
        organizationId,
        submitterEmail,
        createdAt: { gte: new Date(Date.now() - RATE_LIMIT_WINDOW_MS) },
      },
    });
    if (recentCount >= RATE_LIMIT_MAX) {
      throw new ApiError("rate_limited", "Rate limit exceeded. Try again later.");
    }

    // ── Round-17 prompt 44 — pilot tagging ──
    // The per-reviewer link carries a token in either the JSON body
    // or the `?pilot=` query string. Resolve it once here so the
    // critique row gets the pilot tag, the reviewer slug, and the
    // expedited queue ordering on the founder side. An unrecognized
    // token is treated as non-pilot (the submission still records,
    // just without pilot priority — silent promotion would let any
    // outsider claim pilot status).
    const pilotConfig = loadPilotConfig();
    const url = new URL(req.url);
    const tokenFromQuery = url.searchParams.get("pilot");
    const tokenFromBody = typeof body.pilotToken === "string" ? body.pilotToken : "";
    const pilotToken = (tokenFromBody || tokenFromQuery || "").trim();
    const reviewerSlug = resolveReviewerSlug(pilotConfig, pilotToken);
    const pilotTag = reviewerSlug && isPilotWindowOpen(pilotConfig.window) ? pilotConfig.tag : "";
    const pilotReviewerSlug = pilotTag ? (reviewerSlug ?? "") : "";

    let row;
    try {
      row = await createCritique({
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
        pilotTag,
        pilotReviewerSlug,
        hallOfFameConsent: Boolean(body.hallOfFameConsent),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to record critique";
      throw new ApiError("validation_error", message);
    }

    return {
      data: { id: row.id },
      legacy: { ok: true, id: row.id },
    };
  },
  { cors: true, corsMethods: "POST, OPTIONS" },
);
