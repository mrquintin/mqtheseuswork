import { randomUUID } from "crypto";

import { clientIpFor, fingerprintFor } from "@/lib/currentsFingerprint";
import type {
  BetsResponse,
  CalibrationResponse,
  ForecastListResponse,
  MarketListResponse,
  PortfolioSummary,
  PublicBet,
  PublicFollowupMessage,
  PublicForecast,
  PublicForecastSource,
  PublicMarket,
  PublicResolution,
} from "@/lib/forecastsTypes";

export const FORECASTS_BACKEND = (
  process.env.FORECASTS_API_URL ??
  process.env.CURRENTS_API_URL ??
  "http://127.0.0.1:8088"
).replace(/\/+$/, "");

export const FORECASTS_PROXY_TIMEOUT_MS = Number.parseInt(
  process.env.FORECASTS_PROXY_TIMEOUT_MS ?? "30000",
  10,
);

export interface ListForecastsParams {
  since?: string | Date | null;
  topic?: string | null;
  status?: string | null;
  limit?: number | null;
  seeded?: boolean | null;
}

export interface ListMarketsParams {
  source?: string | null;
  category?: string | null;
  status?: string | null;
  since?: string | Date | null;
  limit?: number | null;
}

export interface ListBetsParams {
  limit?: number | null;
  offset?: number | null;
}

type StreamingRequestInit = RequestInit & { duplex?: "half" };

function serializeParam(value: string | Date | number | boolean): string {
  if (value instanceof Date) return value.toISOString();
  return String(value);
}

type SearchParamValue = string | Date | number | boolean | null | undefined;

function searchParamsFor(params: object): URLSearchParams {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params) as [string, SearchParamValue][]) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, serializeParam(value));
  }
  return search;
}

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

function hasPathBoundary(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`);
}

export function isPublicForecastsPath(path: string): boolean {
  const normalizedPath = normalizePath(path);
  if (normalizedPath === "/v1/operator" || normalizedPath.includes("/v1/operator/")) {
    return false;
  }
  return (
    hasPathBoundary(normalizedPath, "/v1/forecasts") ||
    hasPathBoundary(normalizedPath, "/v1/markets") ||
    hasPathBoundary(normalizedPath, "/v1/portfolio")
  );
}

export function forecastsBackendUrl(path: string, search?: string | URLSearchParams): string {
  const normalizedPath = normalizePath(path);
  if (!isPublicForecastsPath(normalizedPath)) {
    throw new Error(`public forecasts proxy refused upstream path: ${normalizedPath}`);
  }

  const url = new URL(`${FORECASTS_BACKEND}${normalizedPath}`);
  if (search instanceof URLSearchParams) {
    url.search = search.toString();
  } else if (search) {
    url.search = search.startsWith("?") ? search.slice(1) : search;
  }
  return url.toString();
}

function timeoutFor(signal: AbortSignal, timeoutMs: number) {
  const controller = new AbortController();
  let timedOut = false;
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const abortFromRequest = () => controller.abort(signal.reason);
  if (signal.aborted) {
    abortFromRequest();
  } else {
    signal.addEventListener("abort", abortFromRequest, { once: true });
    if (Number.isFinite(timeoutMs) && timeoutMs > 0) {
      timeoutId = setTimeout(() => {
        timedOut = true;
        controller.abort(new Error("forecasts upstream timeout"));
      }, timeoutMs);
    }
  }

  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    cleanup: () => {
      if (timeoutId !== null) clearTimeout(timeoutId);
      signal.removeEventListener("abort", abortFromRequest);
    },
  };
}

async function fetchJson<T>(path: string, search?: URLSearchParams): Promise<T> {
  const timeout = timeoutFor(new AbortController().signal, FORECASTS_PROXY_TIMEOUT_MS);
  try {
    const res = await fetch(forecastsBackendUrl(path, search), {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
      signal: timeout.signal,
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`Forecasts API ${res.status}${detail ? `: ${detail}` : ""}`);
    }
    return res.json() as Promise<T>;
  } finally {
    timeout.cleanup();
  }
}

export function passThroughHeaders(req: Request): Headers {
  const headers = new Headers();
  const userAgent = req.headers.get("user-agent");
  const contentType = req.headers.get("content-type");
  const ip = clientIpFor(req);

  if (userAgent) headers.set("user-agent", userAgent);
  if (contentType) headers.set("content-type", contentType);
  if (ip !== "unknown") headers.set("x-forwarded-for", ip);
  headers.set("x-request-id", req.headers.get("x-request-id") || randomUUID());

  return headers;
}

export function passThroughHeadersWithFingerprint(req: Request): Headers {
  const headers = passThroughHeaders(req);
  headers.set("x-client-id", fingerprintFor(req));
  return headers;
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

function publicRefusal(): Response {
  return new Response(JSON.stringify({ error: "forecast_proxy_not_found" }), {
    status: 404,
    headers: { "content-type": "application/json" },
  });
}

function upstreamUnavailable(error: unknown, timedOut: boolean): Response {
  const message = error instanceof Error ? error.message : "unknown upstream failure";
  return new Response(
    JSON.stringify({
      error: timedOut ? "forecasts_upstream_timeout" : "forecasts_upstream_unavailable",
      detail: message,
    }),
    {
      status: timedOut ? 504 : 502,
      headers: { "content-type": "application/json" },
    },
  );
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

export function proxyResponse(upstream: Response): Response {
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: proxiedJsonHeaders(upstream),
  });
}

export function proxySseResponse(upstream: Response): Response {
  if (!upstream.ok) return proxyResponse(upstream);
  return new Response(chunkForwardingStream(upstream.body), {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: proxiedSseHeaders(upstream),
  });
}

export async function proxyToForecasts(
  req: Request,
  path: string,
  options: {
    method?: "GET" | "POST";
    body?: BodyInit | null;
    headers?: Headers;
    sse?: boolean;
  } = {},
): Promise<Response> {
  if (!isPublicForecastsPath(path)) return publicRefusal();

  const sourceUrl = new URL(req.url);
  const timeout = options.sse ? null : timeoutFor(req.signal, FORECASTS_PROXY_TIMEOUT_MS);
  const init: StreamingRequestInit = {
    method: options.method ?? req.method,
    headers: options.headers ?? passThroughHeaders(req),
    cache: "no-store",
    redirect: "manual",
    signal: timeout?.signal ?? req.signal,
  };

  if (options.body !== undefined) {
    init.body = options.body;
    if (options.body) init.duplex = "half";
  }

  try {
    const upstream = await fetch(forecastsBackendUrl(path, sourceUrl.search), init);
    return options.sse ? proxySseResponse(upstream) : proxyResponse(upstream);
  } catch (error) {
    return upstreamUnavailable(error, Boolean(timeout?.didTimeout()));
  } finally {
    timeout?.cleanup();
  }
}

export async function listForecasts(params: ListForecastsParams = {}): Promise<ForecastListResponse> {
  return fetchJson<ForecastListResponse>("/v1/forecasts", searchParamsFor(params));
}

export async function getForecast(id: string): Promise<PublicForecast> {
  return fetchJson<PublicForecast>(`/v1/forecasts/${encodeURIComponent(id)}`);
}

export async function getForecastSources(id: string): Promise<PublicForecastSource[]> {
  return fetchJson<PublicForecastSource[]>(`/v1/forecasts/${encodeURIComponent(id)}/sources`);
}

export async function getForecastResolution(id: string): Promise<PublicResolution> {
  return fetchJson<PublicResolution>(`/v1/forecasts/${encodeURIComponent(id)}/resolution`);
}

export async function getForecastBets(id: string): Promise<PublicBet[]> {
  return fetchJson<PublicBet[]>(`/v1/forecasts/${encodeURIComponent(id)}/bets`);
}

export async function getForecastFollowupMessages(
  id: string,
  session: string,
  search?: string,
): Promise<{ items: PublicFollowupMessage[]; next_before: string | null }> {
  return fetchJson<{ items: PublicFollowupMessage[]; next_before: string | null }>(
    `/v1/forecasts/${encodeURIComponent(id)}/follow-up/${encodeURIComponent(session)}/messages`,
    search ? new URLSearchParams(search) : undefined,
  );
}

export async function listMarkets(params: ListMarketsParams = {}): Promise<MarketListResponse> {
  return fetchJson<MarketListResponse>("/v1/markets", searchParamsFor(params));
}

export async function getMarket(id: string): Promise<PublicMarket> {
  return fetchJson<PublicMarket>(`/v1/markets/${encodeURIComponent(id)}`);
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  return fetchJson<PortfolioSummary>("/v1/portfolio");
}

export async function getPortfolioCalibration(): Promise<CalibrationResponse> {
  return fetchJson<CalibrationResponse>("/v1/portfolio/calibration");
}

export async function getPortfolioBets(params: ListBetsParams = {}): Promise<BetsResponse> {
  return fetchJson<BetsResponse>("/v1/portfolio/bets", searchParamsFor(params));
}
