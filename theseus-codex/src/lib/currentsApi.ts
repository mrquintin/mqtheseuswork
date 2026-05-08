import { randomUUID } from "crypto";

import type {
  PublicFollowupMessage,
  PublicOpinion,
  PublicSource,
  PublicCitation,
} from "@/lib/currentsTypes";
import { clientIpFor } from "@/lib/currentsFingerprint";

export const BACKEND = (process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088").replace(/\/+$/, "");

export interface ListCurrentsParams {
  since?: string | Date | null;
  until?: string | Date | null;
  topic?: string | null;
  stance?: string | null;
  limit?: number | null;
  seeded?: boolean | null;
}

export interface CurrentsHealth {
  x_bearer_present: boolean;
  curated_count: number;
  search_count: number;
  last_cycle_at: string | null;
  events_last_24h: number;
  opinions_last_24h: number;
  disabled_reasons: string[];
}

type StreamingRequestInit = RequestInit & { duplex?: "half" };
type NextFetchOptions = {
  revalidate?: number | false;
  tags?: string[];
};

export interface CurrentsFetchOptions {
  cache?: RequestCache;
  next?: NextFetchOptions;
  signal?: AbortSignal;
}

type NextRequestInit = RequestInit & { next?: NextFetchOptions };

type CitationWire = PublicCitation & {
  conclusion_text?: string | null;
  conclusionText?: string | null;
  conclusion_title?: string | null;
  conclusionTitle?: string | null;
  public_url?: string | null;
  publicUrl?: string | null;
  source_text?: string | null;
  source_visibility?: string | null;
  visibility?: string | null;
};

type SourceWire = PublicSource & {
  conclusion_text?: string | null;
  conclusionText?: string | null;
  conclusion_title?: string | null;
  conclusionTitle?: string | null;
  public_url?: string | null;
  publicUrl?: string | null;
  source_visibility?: string | null;
  visibility?: string | null;
};

interface CitationMetadata {
  conclusionText?: string | null;
  conclusionTitle?: string | null;
  publicUrl?: string | null;
  sourceVisibility?: string | null;
}

function serializeParam(value: string | Date | number | boolean): string {
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

async function fetchJson<T>(
  path: string,
  search?: URLSearchParams,
  options: CurrentsFetchOptions = {},
): Promise<T> {
  const init: NextRequestInit = {
    method: "GET",
    headers: { accept: "application/json" },
  };

  if (options.signal) init.signal = options.signal;
  if (options.next) init.next = options.next;
  if (options.cache) {
    init.cache = options.cache;
  } else if (!options.next) {
    init.cache = "no-store";
  }

  const res = await fetch(currentsBackendUrl(path, search), init);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Currents API ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

function normalizedVisibility(value: string | null | undefined): string | null {
  const normalized = (value ?? "").trim().toLowerCase().replace(/-/g, "_");
  return normalized || null;
}

function publicUrlForVisibility(
  publicUrl: string | null | undefined,
  visibility: string | null | undefined,
): string | null {
  const trimmed = publicUrl?.trim();
  return trimmed && normalizedVisibility(visibility) === "org" ? trimmed : null;
}

function sourceKind(citation: PublicCitation): string {
  return citation.source_kind.trim().toLowerCase();
}

function citationNeedsMetadata(citation: CitationWire): boolean {
  return !(
    citation.conclusion_text?.trim() ||
    citation.conclusionText?.trim() ||
    citation.source_text?.trim()
  );
}

function opinionHasInlineCitationMarkers(opinion: PublicOpinion): boolean {
  return /\[\d+\]/.test(opinion.body_markdown);
}

function sourceMetadata(source: SourceWire): CitationMetadata {
  return {
    conclusionText:
      source.conclusion_text?.trim() ||
      source.conclusionText?.trim() ||
      source.source_text?.trim() ||
      null,
    conclusionTitle:
      source.conclusion_title?.trim() || source.conclusionTitle?.trim() || null,
    publicUrl: source.public_url ?? source.publicUrl ?? null,
    sourceVisibility: source.source_visibility ?? source.visibility ?? null,
  };
}

function normalizeCitation(
  citation: CitationWire,
  metadata: CitationMetadata | undefined,
): CitationWire {
  const visibility =
    metadata?.sourceVisibility ??
    citation.source_visibility ??
    citation.visibility ??
    null;
  const publicUrl = publicUrlForVisibility(
    metadata?.publicUrl ?? citation.public_url ?? citation.publicUrl ?? null,
    visibility,
  );
  const conclusionText =
    metadata?.conclusionText ??
    citation.conclusion_text ??
    citation.conclusionText ??
    citation.source_text ??
    null;
  const conclusionTitle =
    metadata?.conclusionTitle ??
    citation.conclusion_title ??
    citation.conclusionTitle ??
    null;

  return {
    ...citation,
    conclusion_text: conclusionText,
    conclusion_title: conclusionTitle,
    public_url: publicUrl,
    source_visibility: normalizedVisibility(visibility),
  };
}

function normalizeOpinion(
  opinion: PublicOpinion,
  metadataBySourceId: Map<string, CitationMetadata> = new Map(),
): PublicOpinion {
  return {
    ...opinion,
    citations: (opinion.citations as CitationWire[]).map((citation) =>
      normalizeCitation(citation, metadataBySourceId.get(citation.source_id)),
    ),
  };
}

function titleFromText(text: string | null | undefined): string | null {
  const normalized = text?.replace(/\s+/g, " ").trim();
  if (!normalized) return null;
  return normalized.length > 140 ? `${normalized.slice(0, 137)}...` : normalized;
}

function titleFromPayload(payloadJson: unknown): string | null {
  if (typeof payloadJson !== "string" || !payloadJson.trim()) return null;
  try {
    const payload = JSON.parse(payloadJson) as { conclusionText?: unknown; title?: unknown };
    if (typeof payload.conclusionText === "string") {
      return titleFromText(payload.conclusionText);
    }
    if (typeof payload.title === "string") return titleFromText(payload.title);
  } catch {
    return null;
  }
  return null;
}

async function citationMetadataFromSources(
  opinion: PublicOpinion,
  options?: CurrentsFetchOptions,
): Promise<Map<string, CitationMetadata>> {
  const metadataBySourceId = new Map<string, CitationMetadata>();
  if (!opinionHasInlineCitationMarkers(opinion)) return metadataBySourceId;
  if (!(opinion.citations as CitationWire[]).some(citationNeedsMetadata)) {
    return metadataBySourceId;
  }

  try {
    const sources = await fetchJson<SourceWire[]>(
      `/v1/currents/${encodeURIComponent(opinion.id)}/sources`,
      undefined,
      options,
    );
    for (const source of sources) {
      metadataBySourceId.set(source.source_id, sourceMetadata(source));
    }
  } catch {
    // Fail closed: source text may be absent, but source URLs must not leak.
  }
  return metadataBySourceId;
}

async function citationMetadataFromPublicDb(
  opinions: PublicOpinion[],
): Promise<Map<string, CitationMetadata>> {
  const opinionsWithMarkers = opinions.filter(opinionHasInlineCitationMarkers);
  const conclusionIds = [
    ...new Set(
      opinionsWithMarkers.flatMap((opinion) =>
        (opinion.citations as CitationWire[])
          .filter((citation) => sourceKind(citation) === "conclusion")
          .map((citation) => citation.source_id)
          .filter(Boolean),
      ),
    ),
  ];
  if (!conclusionIds.length) return new Map();

  try {
    const { db } = await import("@/lib/db");
    const client = db as {
      conclusion: {
        findMany: (args: unknown) => Promise<
          {
            id: string;
            text: string | null;
            topicHint?: string | null;
            sources?: {
              upload?: {
                visibility?: string | null;
                deletedAt?: Date | string | null;
              } | null;
            }[];
          }[]
        >;
      };
      publishedConclusion: {
        findMany: (args: unknown) => Promise<
          {
            sourceConclusionId: string;
            slug: string;
            version: number;
            payloadJson: string;
          }[]
        >;
      };
    };

    const [conclusions, publications] = await Promise.all([
      client.conclusion.findMany({
        where: { id: { in: conclusionIds } },
        select: {
          id: true,
          text: true,
          topicHint: true,
          sources: {
            select: {
              upload: {
                select: {
                  visibility: true,
                  deletedAt: true,
                },
              },
            },
          },
        },
      }),
      client.publishedConclusion.findMany({
        where: {
          kind: "CONCLUSION",
          sourceConclusionId: { in: conclusionIds },
        },
        orderBy: [{ publishedAt: "desc" }],
        select: {
          sourceConclusionId: true,
          slug: true,
          version: true,
          payloadJson: true,
        },
      }),
    ]);

    const latestPublication = new Map<string, (typeof publications)[number]>();
    for (const publication of publications) {
      if (!latestPublication.has(publication.sourceConclusionId)) {
        latestPublication.set(publication.sourceConclusionId, publication);
      }
    }

    const metadata = new Map<string, CitationMetadata>();
    for (const conclusion of conclusions) {
      const sourceVisibilities = (conclusion.sources ?? [])
        .map((source) => source.upload)
        .filter((upload) => upload && !upload.deletedAt)
        .map((upload) => normalizedVisibility(upload?.visibility));
      const visibility = sourceVisibilities.includes("org")
        ? "org"
        : sourceVisibilities.find(Boolean) ?? null;
      const publication = latestPublication.get(conclusion.id);
      const publicUrl =
        visibility === "org" && publication
          ? `/c/${encodeURIComponent(publication.slug)}/v/${publication.version}`
          : null;

      metadata.set(conclusion.id, {
        conclusionText: conclusion.text ?? null,
        conclusionTitle:
          titleFromPayload(publication?.payloadJson) ||
          titleFromText(conclusion.topicHint) ||
          titleFromText(conclusion.text),
        publicUrl,
        sourceVisibility: visibility,
      });
    }
    return metadata;
  } catch {
    // No DB/env access in this runtime means no public URL. That is safer than leaking.
    return new Map();
  }
}

async function enrichOpinions(
  opinions: PublicOpinion[],
  options?: CurrentsFetchOptions,
): Promise<PublicOpinion[]> {
  const sourceMetadataResults = await Promise.all(
    opinions.map((opinion) => citationMetadataFromSources(opinion, options)),
  );
  const dbMetadata = await citationMetadataFromPublicDb(opinions);

  return opinions.map((opinion, index) => {
    const merged = new Map(sourceMetadataResults[index]);
    for (const [sourceId, metadata] of dbMetadata) {
      const existing = merged.get(sourceId);
      merged.set(sourceId, {
        conclusionText: metadata.conclusionText ?? existing?.conclusionText ?? null,
        conclusionTitle: metadata.conclusionTitle ?? existing?.conclusionTitle ?? null,
        publicUrl: metadata.publicUrl ?? existing?.publicUrl ?? null,
        sourceVisibility: metadata.sourceVisibility ?? existing?.sourceVisibility ?? null,
      });
    }
    return normalizeOpinion(opinion, merged);
  });
}

export async function listCurrents(
  params: ListCurrentsParams,
  options?: CurrentsFetchOptions,
): Promise<{ items: PublicOpinion[] }> {
  const result = await fetchJson<{ items: PublicOpinion[] }>(
    "/v1/currents",
    searchParamsFor(params),
    options,
  );
  return { items: await enrichOpinions(result.items, options) };
}

export async function getCurrentsHealth(options?: CurrentsFetchOptions): Promise<CurrentsHealth> {
  return fetchJson<CurrentsHealth>("/v1/currents/health", undefined, options);
}

export async function getCurrent(id: string): Promise<PublicOpinion> {
  const opinion = await fetchJson<PublicOpinion>(`/v1/currents/${encodeURIComponent(id)}`);
  return (await enrichOpinions([opinion]))[0];
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
