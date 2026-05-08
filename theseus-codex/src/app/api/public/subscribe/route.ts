import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { db } from "@/lib/db";
import { resolvePublicOrganizationId } from "@/lib/conclusionsRead";
import { publicCorsHeaders } from "@/lib/publicCors";
import { clientIpFor } from "@/lib/currentsFingerprint";
import { challengeOrReject } from "@/lib/publicChallenge";
import { checkSubscribeIpRateLimit } from "@/lib/subscribeIpRateLimit";
import {
  SUBSCRIBER_CADENCES,
  SUBSCRIBER_SCOPES,
  createOrReviveSubscriber,
  sendConfirmEmail,
  type SubscriberCadence,
  type SubscriberScope,
} from "@/lib/subscriptions";

const RATE_LIMIT_WINDOW_MS = 24 * 60 * 60 * 1000;
const RATE_LIMIT_MAX = 10;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function OPTIONS(req: NextRequest) {
  return new NextResponse(null, { status: 204, headers: publicCorsHeaders(req) });
}

export async function POST(req: NextRequest) {
  const cors = publicCorsHeaders(req);

  const ip = clientIpFor(req);
  const ipRate = checkSubscribeIpRateLimit(ip);
  if (!ipRate.ok) {
    return NextResponse.json(
      { error: "Too many subscribe requests from this network. Try again later." },
      {
        status: 429,
        headers: { ...cors, "Retry-After": String(ipRate.retryAfterSec) },
      },
    );
  }

  const challengeFail = challengeOrReject(req, ip);
  if (challengeFail) {
    return NextResponse.json(challengeFail.body, { status: challengeFail.status, headers: cors });
  }

  const body = (await req.json().catch(() => null)) as
    | {
        email?: string;
        scope?: string;
        scopeKey?: string;
        cadence?: string;
      }
    | null;
  if (!body) {
    return NextResponse.json({ error: "JSON body required" }, { status: 400, headers: cors });
  }
  const scope = body.scope as SubscriberScope | undefined;
  if (!scope || !SUBSCRIBER_SCOPES.includes(scope)) {
    return NextResponse.json({ error: "invalid scope" }, { status: 400, headers: cors });
  }
  const cadence = (body.cadence as SubscriberCadence | undefined) ?? "weekly";
  if (!SUBSCRIBER_CADENCES.includes(cadence)) {
    return NextResponse.json({ error: "invalid cadence" }, { status: 400, headers: cors });
  }

  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) {
    return NextResponse.json(
      { error: "no public organization configured" },
      { status: 503, headers: cors },
    );
  }

  const recent = await db.subscriber.count({
    where: {
      organizationId,
      email: String(body.email || "").trim().toLowerCase(),
      createdAt: { gte: new Date(Date.now() - RATE_LIMIT_WINDOW_MS) },
    },
  });
  if (recent >= RATE_LIMIT_MAX) {
    return NextResponse.json(
      { error: "too many subscribe requests for this email today" },
      { status: 429, headers: cors },
    );
  }

  const result = await createOrReviveSubscriber(organizationId, {
    email: body.email ?? "",
    scope,
    scopeKey: body.scopeKey,
    cadence,
  });

  if (!result.ok) {
    return NextResponse.json({ error: result.error }, {
      status: result.status ?? 400,
      headers: cors,
    });
  }

  if (result.status === "active") {
    return NextResponse.json(
      { ok: true, status: "active", message: "Already subscribed and confirmed." },
      { status: 200, headers: cors },
    );
  }

  const row = await db.subscriber.findUnique({ where: { id: result.subscriberId } });
  if (row) {
    void sendConfirmEmail({
      to: row.email,
      scope: row.scope as SubscriberScope,
      scopeKey: row.scopeKey,
      confirmToken: row.confirmToken,
      unsubscribeToken: row.unsubscribeToken,
    }).catch((error) => {
      console.error("[public subscribe] confirm email failed", error);
    });
  }

  return NextResponse.json(
    {
      ok: true,
      status: "pending",
      message: "Check your inbox to confirm. Nothing is added to the list until you click the confirm link.",
    },
    { status: 200, headers: cors },
  );
}
