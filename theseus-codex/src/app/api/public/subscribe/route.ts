import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ApiError } from "@/lib/api/envelope";
import { withApiHandler } from "@/lib/api/handler";
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

type SubscribePayload = {
  status: "active" | "pending";
  message: string;
};

export const POST = withApiHandler<SubscribePayload>(
  async (req) => {
    const ip = clientIpFor(req);
    const ipRate = checkSubscribeIpRateLimit(ip);
    if (!ipRate.ok) {
      throw new ApiError(
        "rate_limited",
        "Too many subscribe requests from this network. Try again later.",
        { headers: { "Retry-After": String(ipRate.retryAfterSec) } },
      );
    }

    const challengeFail = challengeOrReject(req, ip);
    if (challengeFail) {
      const message =
        (challengeFail.body as { error?: string })?.error ?? "Challenge required";
      const code = challengeFail.status === 428 ? "challenge_required" : "forbidden";
      throw new ApiError(code, message, { status: challengeFail.status });
    }

    const body = (await req.json().catch(() => null)) as
      | { email?: string; scope?: string; scopeKey?: string; cadence?: string }
      | null;
    if (!body) {
      throw new ApiError("bad_json", "JSON body required");
    }

    const scope = body.scope as SubscriberScope | undefined;
    if (!scope || !SUBSCRIBER_SCOPES.includes(scope)) {
      throw new ApiError("validation_error", "invalid scope");
    }
    const cadence = (body.cadence as SubscriberCadence | undefined) ?? "weekly";
    if (!SUBSCRIBER_CADENCES.includes(cadence)) {
      throw new ApiError("validation_error", "invalid cadence");
    }

    const organizationId = await resolvePublicOrganizationId();
    if (!organizationId) {
      throw new ApiError("service_unavailable", "no public organization configured");
    }

    const email = String(body.email || "").trim().toLowerCase();
    const recent = await db.subscriber.count({
      where: {
        organizationId,
        email,
        createdAt: { gte: new Date(Date.now() - RATE_LIMIT_WINDOW_MS) },
      },
    });
    if (recent >= RATE_LIMIT_MAX) {
      throw new ApiError(
        "rate_limited",
        "too many subscribe requests for this email today",
      );
    }

    const result = await createOrReviveSubscriber(organizationId, {
      email: body.email ?? "",
      scope,
      scopeKey: body.scopeKey,
      cadence,
    });

    if (!result.ok) {
      throw new ApiError("validation_error", result.error, {
        status: result.status ?? 400,
      });
    }

    if (result.status === "active") {
      const payload: SubscribePayload = {
        status: "active",
        message: "Already subscribed and confirmed.",
      };
      return {
        data: payload,
        legacy: { ok: true, status: "active", message: payload.message },
      };
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

    const payload: SubscribePayload = {
      status: "pending",
      message:
        "Check your inbox to confirm. Nothing is added to the list until you click the confirm link.",
    };
    return {
      data: payload,
      legacy: { ok: true, status: "pending", message: payload.message },
    };
  },
  { cors: true, corsMethods: "POST, OPTIONS" },
);
