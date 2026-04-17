import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { db } from "@/lib/db";
import { publicCorsHeaders } from "@/lib/publicCors";

const KINDS = new Set(["counter_evidence", "counter_argument", "clarification", "agreement_extension"]);

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
    select: { id: true, organizationId: true },
  });
  if (!pub) {
    return NextResponse.json({ error: "Unknown published conclusion" }, { status: 404, headers: cors });
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

  return NextResponse.json({ ok: true, id: row.id }, { status: 201, headers: cors });
}
