import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { clientIpFor } from "@/lib/currentsFingerprint";
import {
  checkPublicAskRateLimit,
  hashQueryBucket,
  publicAsk,
} from "@/lib/publicAsk";
import { publicCorsHeaders } from "@/lib/publicCors";
import { challengeOrReject } from "@/lib/publicChallenge";

/**
 * Public inquiry endpoint.
 *
 * Anonymous, read-only. The reader posts a free-text question; we
 * return the firm's relevant conclusions, opinions, articles, and
 * open questions. No generation, no LLM rewriting — see
 * `lib/publicAsk.ts` for the visibility and snippet contract.
 *
 * Logging policy: we log a 12-hex bucket id for the query (sha256
 * over a salt + normalised query, truncated). Raw queries never
 * touch any persistent surface a reader could later read back. The
 * bucket lets us coarsely aggregate abuse / load without enabling
 * reconstruction.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 4_000;

export function OPTIONS(req: NextRequest) {
  return new NextResponse(null, { status: 204, headers: publicCorsHeaders(req) });
}

export async function POST(req: NextRequest) {
  const cors = publicCorsHeaders(req);

  const ip = clientIpFor(req);
  const rate = checkPublicAskRateLimit(ip);
  if (!rate.ok) {
    return NextResponse.json(
      { error: "Too many requests. Try again shortly." },
      {
        status: 429,
        headers: {
          ...cors,
          "Retry-After": String(rate.retryAfterSec),
        },
      },
    );
  }

  const challengeFail = challengeOrReject(req, ip);
  if (challengeFail) {
    return NextResponse.json(challengeFail.body, { status: challengeFail.status, headers: cors });
  }

  let body: unknown = null;
  try {
    const contentLength = Number(req.headers.get("content-length") ?? "0");
    if (contentLength > MAX_BODY_BYTES) {
      return NextResponse.json({ error: "Request body too large" }, { status: 413, headers: cors });
    }
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body must be valid JSON" }, { status: 400, headers: cors });
  }

  const query =
    body && typeof body === "object" && !Array.isArray(body)
      ? (body as { query?: unknown }).query
      : null;
  if (typeof query !== "string" || query.trim().length === 0) {
    return NextResponse.json({ error: "query is required" }, { status: 400, headers: cors });
  }

  let response;
  try {
    response = await publicAsk(query);
  } catch (error) {
    // Hashed bucket only — never the raw query.
    console.error("[public ask] retrieval failed", {
      bucket: hashQueryBucket(query),
      error: error instanceof Error ? error.message : "unknown",
    });
    return NextResponse.json({ error: "Retrieval failed" }, { status: 500, headers: cors });
  }

  return NextResponse.json(response, { status: 200, headers: cors });
}
