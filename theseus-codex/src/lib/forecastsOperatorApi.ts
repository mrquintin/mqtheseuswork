import { createHash, createHmac, randomUUID } from "crypto";

import { getFounder as getFounderFromSessionCookie } from "@/lib/auth";
import { clientIpFor } from "@/lib/currentsFingerprint";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";
import type {
  OperatorBet,
  OperatorKillSwitchState,
  OperatorLiveBetsResponse,
  PublicForecast,
} from "@/lib/forecastsTypes";

export const FORECASTS_OPERATOR_BACKEND = (
  process.env.FORECASTS_API_URL ??
  process.env.CURRENTS_API_URL ??
  "http://127.0.0.1:8088"
).replace(/\/+$/, "");

const OPERATOR_HEADER = "x-forecasts-operator";
const OPERATOR_TIMESTAMP_HEADER = "x-forecasts-timestamp";

type StreamingRequestInit = RequestInit & { duplex?: "half" };

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

export function isOperatorForecastsPath(path: string): boolean {
  const normalizedPath = normalizePath(path);
  return normalizedPath === "/v1/operator" || normalizedPath.startsWith("/v1/operator/");
}

function operatorBackendUrl(path: string, search?: string | URLSearchParams): string {
  const normalizedPath = normalizePath(path);
  if (!isOperatorForecastsPath(normalizedPath)) {
    throw new Error(`operator forecasts proxy refused upstream path: ${normalizedPath}`);
  }

  const url = new URL(`${FORECASTS_OPERATOR_BACKEND}${normalizedPath}`);
  if (search instanceof URLSearchParams) {
    url.search = search.toString();
  } else if (search) {
    url.search = search.startsWith("?") ? search.slice(1) : search;
  }
  return url.toString();
}

function jsonError(error: string, status: number): Response {
  return new Response(JSON.stringify({ error }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function proxiedJsonHeaders(upstream: Response): Headers {
  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  const cacheControl = upstream.headers.get("cache-control");
  const retryAfter = upstream.headers.get("retry-after");

  if (contentType) headers.set("content-type", contentType);
  if (cacheControl) headers.set("cache-control", cacheControl);
  if (retryAfter) headers.set("retry-after", retryAfter);
  return headers;
}

function proxiedSseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  headers.set("content-type", upstream.headers.get("content-type") || "text/event-stream; charset=utf-8");
  headers.set("cache-control", "no-cache, no-transform");
  headers.set("connection", "keep-alive");
  headers.set("x-accel-buffering", "no");
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) headers.set("retry-after", retryAfter);
  return headers;
}

function chunkForwardingStream(body: ReadableStream<Uint8Array> | null): ReadableStream<Uint8Array> | null {
  if (body === null) return null;
  const reader = body.getReader();
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }
      if (value) controller.enqueue(value);
    },
    async cancel(reason) {
      await reader.cancel(reason);
    },
  });
}

function proxyResponse(upstream: Response): Response {
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: proxiedJsonHeaders(upstream),
  });
}

function proxySseResponse(upstream: Response): Response {
  if (!upstream.ok) return proxyResponse(upstream);
  return new Response(chunkForwardingStream(upstream.body), {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: proxiedSseHeaders(upstream),
  });
}

function computeOperatorHmac(
  secret: string,
  options: {
    timestamp: string;
    path: string;
    body: Uint8Array;
  },
): string {
  const bodyHash = createHash("sha256").update(options.body).digest("hex");
  const message = [options.timestamp, normalizePath(options.path), bodyHash].join("\n");
  return createHmac("sha256", secret).update(message, "utf8").digest("hex");
}

function signedOperatorHeaders(req: Request, path: string, body: Uint8Array): Headers | Response {
  const secret = process.env.FORECASTS_OPERATOR_SECRET?.trim();
  if (!secret) return jsonError("operator_secret_not_configured", 500);

  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  const accept = req.headers.get("accept");
  const userAgent = req.headers.get("user-agent");
  const ip = clientIpFor(req);
  const timestamp = String(Date.now() / 1000);
  const digest = computeOperatorHmac(secret, {
    timestamp,
    path,
    body,
  });

  if (contentType) headers.set("content-type", contentType);
  if (accept) headers.set("accept", accept);
  if (userAgent) headers.set("user-agent", userAgent);
  if (ip !== "unknown") headers.set("x-forwarded-for", ip);
  headers.set("x-request-id", req.headers.get("x-request-id") || randomUUID());
  headers.set(OPERATOR_TIMESTAMP_HEADER, timestamp);
  headers.set(OPERATOR_HEADER, digest);
  return headers;
}

export async function getFounderFromSession() {
  return getFounderFromSessionCookie();
}

function operatorCsrfToken(founderId: string): string {
  return process.env.FORECASTS_OPERATOR_CSRF_TOKEN?.trim() || `founder:${founderId}`;
}

async function readBodyForSigning(
  req: Request,
  method: string,
  founder: { id: string },
): Promise<Uint8Array> {
  if (method === "GET" || method === "HEAD") return new Uint8Array();
  const raw = await req.arrayBuffer();
  const text = new TextDecoder().decode(raw).trim();
  let payload: Record<string, unknown> = {};
  if (text) {
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        payload = parsed as Record<string, unknown>;
      }
    } catch {
      payload = {};
    }
  }
  payload.operator_id = founder.id;
  payload.csrf_token = operatorCsrfToken(founder.id);
  return new TextEncoder().encode(JSON.stringify(payload));
}

function exactArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function upstreamUnavailable(error: unknown): Response {
  const message = error instanceof Error ? error.message : "unknown upstream failure";
  return new Response(JSON.stringify({ error: "forecasts_operator_upstream_unavailable", detail: message }), {
    status: 502,
    headers: { "content-type": "application/json" },
  });
}

export async function proxyToForecastsOperator(
  req: Request,
  path: string,
  options: {
    method?: "GET" | "POST";
    sse?: boolean;
  } = {},
): Promise<Response> {
  const founder = await getFounderFromSession();
  if (!founder) return jsonError("Not authenticated", 401);
  if (!canWrite(founder.role)) {
    return new Response(JSON.stringify(WRITE_FORBIDDEN_RESPONSE), {
      status: 403,
      headers: { "content-type": "application/json" },
    });
  }
  if (!isOperatorForecastsPath(path)) return jsonError("forecast_operator_proxy_not_found", 404);

  const sourceUrl = new URL(req.url);
  const method = options.method ?? req.method;
  const bodyBytes = await readBodyForSigning(req, method, { id: founder.id });
  const headers = signedOperatorHeaders(req, path, bodyBytes);
  if (headers instanceof Response) return headers;

  const init: StreamingRequestInit = {
    method,
    headers,
    cache: "no-store",
    redirect: "manual",
    signal: req.signal,
  };

  if (method !== "GET" && method !== "HEAD") {
    init.body = new Blob([exactArrayBuffer(bodyBytes)]);
    if (bodyBytes.byteLength > 0) init.duplex = "half";
  }

  try {
    const upstream = await fetch(operatorBackendUrl(path, sourceUrl.search), init);
    return options.sse ? proxySseResponse(upstream) : proxyResponse(upstream);
  } catch (error) {
    return upstreamUnavailable(error);
  }
}

async function fetchOperatorJson<T>(path: string, search?: URLSearchParams): Promise<T> {
  const secret = process.env.FORECASTS_OPERATOR_SECRET?.trim();
  if (!secret) throw new Error("FORECASTS_OPERATOR_SECRET is not configured");
  const body = new Uint8Array();
  const timestamp = String(Date.now() / 1000);
  const headers = new Headers({
    accept: "application/json",
    [OPERATOR_TIMESTAMP_HEADER]: timestamp,
    [OPERATOR_HEADER]: computeOperatorHmac(secret, { timestamp, path, body }),
  });
  const res = await fetch(operatorBackendUrl(path, search), {
    method: "GET",
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Forecasts operator API ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export async function listOperatorLiveBets(params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  return fetchOperatorJson<OperatorLiveBetsResponse>("/v1/operator/live-bets", search);
}

export async function authorizeLiveForecast(
  id: string,
  body: { operator_id: string; csrf_token: string },
): Promise<PublicForecast> {
  return postOperatorJson<PublicForecast>(`/v1/operator/forecasts/${encodeURIComponent(id)}/authorize-live`, body);
}

export async function confirmLiveBet(
  id: string,
  betId: string,
  body: { operator_id: string; csrf_token: string },
): Promise<OperatorBet> {
  return postOperatorJson<OperatorBet>(
    `/v1/operator/forecasts/${encodeURIComponent(id)}/bets/${encodeURIComponent(betId)}/confirm`,
    body,
  );
}

export async function cancelLiveBet(
  id: string,
  betId: string,
  body: { operator_id: string; csrf_token: string },
): Promise<OperatorBet> {
  return postOperatorJson<OperatorBet>(
    `/v1/operator/forecasts/${encodeURIComponent(id)}/bets/${encodeURIComponent(betId)}/cancel`,
    body,
  );
}

export async function engageKillSwitch(body: {
  operator_id: string;
  reason: string;
  note?: string | null;
  csrf_token: string;
}): Promise<OperatorKillSwitchState> {
  return postOperatorJson<OperatorKillSwitchState>("/v1/operator/kill-switch/engage", body);
}

export async function disengageKillSwitch(body: {
  operator_id: string;
  note: string;
  csrf_token: string;
}): Promise<OperatorKillSwitchState> {
  return postOperatorJson<OperatorKillSwitchState>("/v1/operator/kill-switch/disengage", body);
}

async function postOperatorJson<T>(path: string, body: object): Promise<T> {
  const secret = process.env.FORECASTS_OPERATOR_SECRET?.trim();
  if (!secret) throw new Error("FORECASTS_OPERATOR_SECRET is not configured");
  const rawJson = JSON.stringify(body);
  const raw = new TextEncoder().encode(rawJson);
  const timestamp = String(Date.now() / 1000);
  const headers = new Headers({
    accept: "application/json",
    "content-type": "application/json",
    [OPERATOR_TIMESTAMP_HEADER]: timestamp,
    [OPERATOR_HEADER]: computeOperatorHmac(secret, { timestamp, path, body: raw }),
  });
  const res = await fetch(operatorBackendUrl(path), {
    method: "POST",
    headers,
    body: rawJson,
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Forecasts operator API ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}
