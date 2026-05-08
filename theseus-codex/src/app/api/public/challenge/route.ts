import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { clientIpFor } from "@/lib/currentsFingerprint";
import { publicCorsHeaders } from "@/lib/publicCors";
import { CHALLENGE_HEADER_NAME, issueChallengeToken } from "@/lib/publicChallenge";

/**
 * Public anti-bot challenge endpoint. Front-end calls GET on form
 * mount, includes the returned token in `X-Theseus-Challenge` on
 * the subsequent POST to `/ask` or `/subscribe`. See
 * `src/lib/publicChallenge.ts` and `docs/security/Threat_Model.md`.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function OPTIONS(req: NextRequest) {
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  headers.set("Access-Control-Expose-Headers", CHALLENGE_HEADER_NAME);
  return new NextResponse(null, { status: 204, headers });
}

export function GET(req: NextRequest) {
  const ip = clientIpFor(req);
  const token = issueChallengeToken(ip);
  const headers = new Headers(publicCorsHeaders(req));
  headers.set("Cache-Control", "no-store");
  headers.set("Access-Control-Expose-Headers", CHALLENGE_HEADER_NAME);
  headers.set(CHALLENGE_HEADER_NAME, token);
  return NextResponse.json({ token, header: CHALLENGE_HEADER_NAME }, { status: 200, headers });
}
