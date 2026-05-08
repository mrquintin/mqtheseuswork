import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { db } from "@/lib/db";
import { publicCorsHeaders } from "@/lib/publicCors";
import { notifyFounderOfResponse } from "@/lib/responsesEmail";

const KINDS = new Set(["counter_evidence", "counter_argument", "clarification", "agreement_extension"]);
const RATE_LIMIT_WINDOW_MS = 24 * 60 * 60 * 1000;
const RATE_LIMIT_MAX = 5;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function OPTIONS(req: NextRequest) {
  return new NextResponse(null, { status: 204, headers: publicCorsHeaders(req) });
}

export async function POST(req: NextRequest) {
  const cors = publicCorsHeaders(req);
  const body = (await req.json().catch(() => null)) as
    | {
        publishedConclusionId?: string;
        kind?: string;
        body?: string;
        citationUrl?: string;
        submitterEmail?: string;
        orcid?: string;
        pseudonymous?: boolean;
      }
    | null;

  if (!body?.publishedConclusionId || !body.kind || !body.body) {
    return NextResponse.json({ error: "publishedConclusionId, kind, and body are required" }, { status: 400, headers: cors });
  }
  if (!KINDS.has(body.kind)) {
    return NextResponse.json({ error: "Invalid kind" }, { status: 400, headers: cors });
  }
  const text = String(body.body).trim();
  if (text.length < 20) {
    return NextResponse.json({ error: "body must be at least 20 characters" }, { status: 400, headers: cors });
  }
  const email = String(body.submitterEmail ?? "").trim();
  if (!email || !email.includes("@")) {
    return NextResponse.json({ error: "submitterEmail is required" }, { status: 400, headers: cors });
  }

  const pub = await db.publishedConclusion.findFirst({
    where: { id: body.publishedConclusionId },
    select: { id: true, organizationId: true, slug: true, version: true, payloadJson: true },
  });
  if (!pub) {
    return NextResponse.json({ error: "Unknown published conclusion" }, { status: 404, headers: cors });
  }

  const recentCount = await db.publicResponse.count({
    where: {
      publishedConclusionId: pub.id,
      submitterEmail: email,
      createdAt: { gte: new Date(Date.now() - RATE_LIMIT_WINDOW_MS) },
    },
  });
  if (recentCount >= RATE_LIMIT_MAX) {
    return NextResponse.json({ error: "Too many responses for this conclusion. Try again later." }, { status: 429, headers: cors });
  }

  const row = await db.publicResponse.create({
    data: {
      organizationId: pub.organizationId,
      publishedConclusionId: pub.id,
      kind: body.kind,
      body: text,
      citationUrl: String(body.citationUrl ?? "").trim(),
      submitterEmail: email,
      orcid: String(body.orcid ?? "").trim(),
      pseudonymous: Boolean(body.pseudonymous),
      status: "pending",
    },
  });

  void notifyFounderOfResponse(row, pub).catch((error) => {
    console.error("[public responses] founder notification failed:", error);
  });

  return NextResponse.json({ ok: true, id: row.id }, { status: 200, headers: cors });
}
