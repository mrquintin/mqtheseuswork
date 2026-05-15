import { randomUUID } from "node:crypto";

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { publicCorsHeaders } from "@/lib/publicCors";

import {
  ApiError,
  type ApiFailure,
  type ApiMeta,
  type ApiSuccess,
  statusForErrorCode,
} from "./envelope";

/**
 * Per-route adapter that wraps a Next.js handler in the unified
 * envelope, normalises errors, attaches a correlation id, and
 * (optionally) serves a legacy alias body for the one-week migration
 * window required by `docs/architecture/API_Envelope_Contract.md`.
 *
 * Handlers return `RouteResult<T>` describing the success payload.
 * For failures, throw `ApiError`. Anything else thrown is logged with
 * the correlation id and surfaces as `internal_error`.
 */

export const LEGACY_HEADER = "x-theseus-envelope";
export const LEGACY_QUERY = "envelope";
export const CORRELATION_HEADER = "x-correlation-id";

export type RouteResult<T> = {
  data: T;
  meta?: ApiMeta;
  /**
   * If present, served as the response body when the caller opts into
   * the legacy alias (header `X-Theseus-Envelope: legacy` or
   * `?envelope=legacy`). Omit on routes that didn't exist before this
   * envelope landed.
   */
  legacy?: unknown;
  headers?: Record<string, string>;
  status?: number;
};

export type ApiHandlerContext = {
  correlationId: string;
};

export type ApiHandler<T> = (
  req: NextRequest,
  ctx: ApiHandlerContext,
) => Promise<RouteResult<T>> | RouteResult<T>;

export type WithApiHandlerOptions = {
  /** Apply `publicCorsHeaders(req)` to every response. Default: false. */
  cors?: boolean;
  /**
   * ISO-8601 date sent as the `Sunset` header on legacy-alias responses.
   * If unset, only `Deprecation: true` is emitted.
   */
  legacySunset?: string;
  /**
   * Extra CORS methods to advertise on the response when `cors: true`.
   * Defaults to `"POST, OPTIONS"`, matching `publicCorsHeaders`.
   */
  corsMethods?: string;
};

function isLegacyAlias(req: NextRequest): boolean {
  const header = req.headers.get(LEGACY_HEADER);
  if (header && header.trim().toLowerCase() === "legacy") return true;
  try {
    const url = new URL(req.url);
    if (url.searchParams.get(LEGACY_QUERY)?.toLowerCase() === "legacy") return true;
  } catch {
    // ignore — Next gives us a parsable URL, but tests sometimes pass raw Requests.
  }
  return false;
}

function applyCors(req: NextRequest, headers: Headers, opts: WithApiHandlerOptions): void {
  if (!opts.cors) return;
  const cors = publicCorsHeaders(req);
  for (const [k, v] of Object.entries(cors)) headers.set(k, v as string);
  if (opts.corsMethods) headers.set("Access-Control-Allow-Methods", opts.corsMethods);
}

function applyLegacyHeaders(headers: Headers, opts: WithApiHandlerOptions): void {
  headers.set("Deprecation", "true");
  if (opts.legacySunset) headers.set("Sunset", opts.legacySunset);
  headers.set(
    "Link",
    '<https://theseus.dev/docs/api/envelope>; rel="deprecation"; type="text/html"',
  );
}

function buildSuccess<T>(result: RouteResult<T>): ApiSuccess<T> {
  return result.meta
    ? { ok: true, data: result.data, meta: result.meta }
    : { ok: true, data: result.data };
}

function buildFailure(err: ApiError, correlationId: string): ApiFailure {
  return {
    ok: false,
    error: {
      code: err.code,
      message: err.message,
      ...(err.details !== undefined ? { details: err.details } : {}),
      correlationId,
    },
  };
}

export function withApiHandler<T>(
  handler: ApiHandler<T>,
  opts: WithApiHandlerOptions = {},
): (req: NextRequest) => Promise<NextResponse> {
  return async function wrapped(req: NextRequest): Promise<NextResponse> {
    const correlationId = randomUUID();
    const baseHeaders = new Headers();
    applyCors(req, baseHeaders, opts);
    baseHeaders.set(CORRELATION_HEADER, correlationId);

    try {
      const result = await handler(req, { correlationId });
      const headers = new Headers(baseHeaders);
      if (result.headers) {
        for (const [k, v] of Object.entries(result.headers)) headers.set(k, v);
      }
      headers.set("Content-Type", "application/json");

      if (isLegacyAlias(req)) {
        applyLegacyHeaders(headers, opts);
        const body = result.legacy !== undefined ? result.legacy : result.data;
        return NextResponse.json(body, { status: result.status ?? 200, headers });
      }

      return NextResponse.json(buildSuccess(result), {
        status: result.status ?? 200,
        headers,
      });
    } catch (error) {
      const headers = new Headers(baseHeaders);
      headers.set("Content-Type", "application/json");

      if (error instanceof ApiError) {
        if (error.extraHeaders) {
          for (const [k, v] of Object.entries(error.extraHeaders)) headers.set(k, v);
        }
        if (isLegacyAlias(req)) {
          applyLegacyHeaders(headers, opts);
          return NextResponse.json(
            { error: error.message },
            { status: error.status, headers },
          );
        }
        return NextResponse.json(buildFailure(error, correlationId), {
          status: error.status,
          headers,
        });
      }

      console.error("[api handler] uncaught", {
        correlationId,
        error: error instanceof Error ? error.message : String(error),
      });
      const internal = new ApiError(
        "internal_error",
        "Internal server error",
      );
      if (isLegacyAlias(req)) {
        applyLegacyHeaders(headers, opts);
        return NextResponse.json(
          { error: internal.message },
          { status: internal.status, headers },
        );
      }
      return NextResponse.json(buildFailure(internal, correlationId), {
        status: statusForErrorCode(internal.code),
        headers,
      });
    }
  };
}
