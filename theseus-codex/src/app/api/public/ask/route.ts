import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ApiError } from "@/lib/api/envelope";
import { withApiHandler } from "@/lib/api/handler";
import { clientIpFor } from "@/lib/currentsFingerprint";
import {
  checkPublicAskRateLimit,
  classifyQuery,
  hashQueryBucket,
  publicAsk,
  submitPublicResearchSuggestion,
} from "@/lib/publicAsk";
import type { PublicAskResponse, ResearchSuggestionResult } from "@/lib/publicAsk";
import { publicCorsHeaders } from "@/lib/publicCors";
import { challengeOrReject } from "@/lib/publicChallenge";

/**
 * Public inquiry endpoint.
 *
 * Anonymous, read-only retrieval. The reader posts a free-text
 * question; we classify it, retrieve the firm's relevant conclusions,
 * opinions, articles, and open questions (diversified via MMR), and
 * return them with freshness signals. No generation, no LLM rewriting
 * — see `lib/publicAsk.ts` for the visibility and snippet contract.
 *
 * The one write this endpoint accepts is a research suggestion from
 * the enriched no-result panel (`{ suggestion: { title, ... } }`) —
 * stored verbatim, not generated.
 *
 * Logging policy: we log a 12-hex bucket id for the query (sha256
 * over a salt + normalised query, truncated) plus the query class.
 * Raw query strings never touch any persistent surface a reader could
 * later read back; the in-process query log keeps raw strings at most
 * 24h (enforced by the retention runner, Round 17 prompt 46) and the
 * persistent surface only ever sees the bucket.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 4_000;

export function OPTIONS(req: NextRequest) {
  return new NextResponse(null, { status: 204, headers: publicCorsHeaders(req) });
}

export const POST = withApiHandler<PublicAskResponse | ResearchSuggestionResult>(
  async (req) => {
    const ip = clientIpFor(req);
    const rate = checkPublicAskRateLimit(ip);
    if (!rate.ok) {
      throw new ApiError("rate_limited", "Too many requests. Try again shortly.", {
        headers: { "Retry-After": String(rate.retryAfterSec) },
      });
    }

    const challengeFail = challengeOrReject(req, ip);
    if (challengeFail) {
      const message =
        (challengeFail.body as { error?: string })?.error ?? "Challenge required";
      const code = challengeFail.status === 428 ? "challenge_required" : "forbidden";
      throw new ApiError(code, message, { status: challengeFail.status });
    }

    const contentLength = Number(req.headers.get("content-length") ?? "0");
    if (contentLength > MAX_BODY_BYTES) {
      throw new ApiError("body_too_large", "Request body too large");
    }

    let body: unknown;
    try {
      body = await req.json();
    } catch {
      throw new ApiError("bad_json", "Body must be valid JSON");
    }

    const obj =
      body && typeof body === "object" && !Array.isArray(body)
        ? (body as Record<string, unknown>)
        : {};

    // Write path: a research suggestion from the enriched no-result
    // panel. Stored verbatim — no generation, no logging of any search
    // query alongside it.
    if (obj.suggestion && typeof obj.suggestion === "object") {
      const suggestion = obj.suggestion as Record<string, unknown>;
      const title = suggestion.title;
      if (typeof title !== "string" || title.trim().length === 0) {
        throw new ApiError("validation_error", "suggestion.title is required");
      }
      try {
        const result = await submitPublicResearchSuggestion({
          title,
          summary: typeof suggestion.summary === "string" ? suggestion.summary : undefined,
          rationale:
            typeof suggestion.rationale === "string" ? suggestion.rationale : undefined,
        });
        return { data: result, legacy: result };
      } catch (error) {
        const message = error instanceof Error ? error.message : "unknown";
        if (/title/i.test(message)) {
          throw new ApiError("validation_error", message);
        }
        console.error("[public ask] suggestion write failed", { error: message });
        throw new ApiError("internal_error", "Could not save suggestion");
      }
    }

    // Read path: a retrieval query.
    const query = obj.query;
    if (typeof query !== "string" || query.trim().length === 0) {
      throw new ApiError("validation_error", "query is required");
    }

    try {
      const response = await publicAsk(query);
      // Bucket + class only — never the raw query. See the logging
      // policy note above.
      console.info("[public ask] query", {
        bucket: response.queryBucket,
        class: response.queryClass,
        noResult: response.noResult,
      });
      return { data: response, legacy: response };
    } catch (error) {
      console.error("[public ask] retrieval failed", {
        bucket: hashQueryBucket(query),
        class: classifyQuery(query),
        error: error instanceof Error ? error.message : "unknown",
      });
      throw new ApiError("internal_error", "Retrieval failed");
    }
  },
  { cors: true, corsMethods: "POST, OPTIONS" },
);
