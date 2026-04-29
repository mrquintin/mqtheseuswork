import { randomUUID } from "crypto";

import type {
  PublicFollowupMessage,
  PublicOpinion,
  PublicSource,
} from "@/lib/currentsTypes";
import { clientIpFor } from "@/lib/currentsFingerprint";

export const BACKEND = (process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088").replace(/\/+$/, "");

export interface ListCurrentsParams {
  since?: string | Date | null;
  until?: string | Date | null;
  topic?: string | null;
  stance?: string | null;
  limit?: number | null;
}

type StreamingRequestInit = RequestInit & { duplex?: "half" };

function serializeParam(value: string | Date | number): string {
  if (value instanceof Date) return value.toISOString();
  return String(value);
}

function searchParamsFor(params: ListCurrentsParams): URLSearchParams {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, serializeParam(value));
  }
  return search;
}

export function currentsBackendUrl(path: string, search?: string | URLSearchParams): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${BACKEND}${normalizedPath}`);
  if (search instanceof URLSearchParams) {
    url.search = search.toString();
  } else if (search) {
    url.search = search.startsWith("?") ? search.slice(1) : search;
  }
  return url.toString();
}

async function fetchJson<T>(path: string, search?: URLSearchParams): Promise<T> {
  const res = await fetch(currentsBackendUrl(path, search), {
    method: "GET",
    headers: { accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Currents API ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export async function listCurrents(params: ListCurrentsParams): Promise<{ items: PublicOpinion[] }> {
  return fetchJson<{ items: PublicOpinion[] }>("/v1/currents", searchParamsFor(params));
}

export async function getCurrent(id: string): Promise<PublicOpinion> {
  return fetchJson<PublicOpinion>(`/v1/currents/${encodeURIComponent(id)}`);
}

export async function getCurrentSources(id: string): Promise<PublicSource[]> {
  return fetchJson<PublicSource[]>(`/v1/currents/${encodeURIComponent(id)}/sources`);
}

export async function getFollowupMessages(
  id: string,
  session: string,
  search?: string,
): Promise<{ items: PublicFollowupMessage[]; next_before: string | null }> {
  return fetchJson<{ items: PublicFollowupMessage[]; next_before: string | null }>(
    `/v1/currents/${encodeURIComponent(id)}/follow-up/${encodeURIComponent(session)}/messages`,
    search ? new URLSearchParams(search) : undefined,
  );
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

function upstreamUnavailable(error: unknown): Response {
  const message = error instanceof Error ? error.message : "unknown upstream failure";
  return new Response(JSON.stringify({ error: "currents_upstream_unavailable", detail: message }), {
    status: 502,
    headers: { "content-type": "application/json" },
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
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: proxiedSseHeaders(upstream),
  });
}

export async function proxyToCurrents(
  req: Request,
  path: string,
  options: {
    method?: "GET" | "POST";
    body?: BodyInit | null;
    headers?: Headers;
    sse?: boolean;
  } = {},
): Promise<Response> {
  const sourceUrl = new URL(req.url);
  const init: StreamingRequestInit = {
    method: options.method ?? req.method,
    headers: options.headers ?? passThroughHeaders(req),
    cache: "no-store",
    redirect: "manual",
    signal: req.signal,
  };

  if (options.body !== undefined) {
    init.body = options.body;
    if (options.body) init.duplex = "half";
  }

  try {
    const upstream = await fetch(currentsBackendUrl(path, sourceUrl.search), init);
    return options.sse ? proxySseResponse(upstream) : proxyResponse(upstream);
  } catch (error) {
    return upstreamUnavailable(error);
  }
}
