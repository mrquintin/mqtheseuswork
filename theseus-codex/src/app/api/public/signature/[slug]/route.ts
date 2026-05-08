import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { db } from "@/lib/db";
import { publicCorsHeaders } from "@/lib/publicCors";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public signature endpoint for a published conclusion.
 *
 * GET /api/public/signature/<slug>?version=<n>
 *
 * Returns the signature.json artifact (canonical input + Ed25519 signature
 * + key fingerprint) that the noosphere CLI minted at publish time. The
 * web app does not hold private keys; it only stores and serves the
 * signature.
 *
 * Readers can re-verify by running:
 *   noosphere ledger verify-publication <slug> --from-url <this URL>
 */

export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  return new NextResponse(null, { status: 204, headers });
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ slug: string }> },
) {
  const corsHeaders = new Headers(publicCorsHeaders(req));
  corsHeaders.set("Access-Control-Allow-Methods", "GET, OPTIONS");

  const { slug } = await ctx.params;
  const url = new URL(req.url);
  const versionRaw = url.searchParams.get("version");
  const version = versionRaw ? Number(versionRaw) : null;

  const where: { slug: string; version?: number } = { slug };
  if (version !== null) {
    if (!Number.isFinite(version) || !Number.isInteger(version) || version < 1) {
      return NextResponse.json(
        { error: "Invalid version" },
        { status: 400, headers: corsHeaders },
      );
    }
    where.version = version;
  }

  const sig = await db.publicationSignature.findFirst({
    where,
    orderBy: { version: "desc" },
  });

  if (!sig) {
    return NextResponse.json(
      { error: "Not found", reason: "no_signature_for_slug" },
      { status: 404, headers: corsHeaders },
    );
  }

  let payload: Record<string, unknown> | null = null;
  try {
    payload = JSON.parse(sig.payloadJson) as Record<string, unknown>;
  } catch {
    payload = null;
  }

  const body = payload ?? {
    schema: "theseus.publicationSignature.v1",
    slug: sig.slug,
    version: sig.version,
    canonicalHash: sig.canonicalHash,
    signatureHex: sig.signatureHex,
    keyFingerprint: sig.keyFingerprint,
    signedAt: sig.signedAt,
  };

  const headers = new Headers(corsHeaders);
  headers.set("Cache-Control", "public, max-age=60, s-maxage=300");
  headers.set("Content-Type", "application/json");
  return NextResponse.json(body, { status: 200, headers });
}
