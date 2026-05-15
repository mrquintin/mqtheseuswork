import { randomUUID } from "crypto";

import type {
  PublicCurrentEvent,
  PublicFollowupMessage,
  PublicOpinion,
  PublicReconciliation,
  PublicReconciliationCounter,
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

export interface CurrentsLastCycle {
  started_at: string | null;
  duration_ms: number;
  ingested: number;
  opined: number;
  rejected: number;
  abstained_insufficient: number;
  abstained_below_significance: number;
  abstained_off_domain: number;
  abstained_near_duplicate: number;
  abstained_budget: number;
  error_count: number;
  last_error: string | null;
}

export interface CurrentsHealth {
  x_bearer_present: boolean;
  curated_count: number;
  search_count: number;
  last_cycle_at: string | null;
  last_event_at?: string | null;
  last_opinion_at?: string | null;
  events_last_24h: number;
  opinions_last_24h: number;
  disabled_reasons: string[];
  last_cycle?: CurrentsLastCycle | null;
  db_ok?: boolean;
  db_error?: string | null;
  using_db_fallback?: boolean;
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
  timeoutMs?: number;
}

type NextRequestInit = RequestInit & { next?: NextFetchOptions };

// Default upstream timeout for the Currents proxy. Must be short enough
// that a 524 / hung backend can't block a Vercel build (which renders
// pages even when marked dynamic), and long enough to absorb a normal
// cold start. 6s is the same envelope `forecastsApi` uses.
const CURRENTS_PROXY_TIMEOUT_MS = 6_000;

function withTimeout(
  signal: AbortSignal | undefined,
  timeoutMs: number,
): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const abortFromUpstream = () => controller.abort(signal?.reason);
  if (signal?.aborted) {
    abortFromUpstream();
  } else if (signal) {
    signal.addEventListener("abort", abortFromUpstream, { once: true });
  }
  if (Number.isFinite(timeoutMs) && timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      controller.abort(new Error("currents upstream timeout"));
    }, timeoutMs);
  }
  return {
    signal: controller.signal,
    cleanup: () => {
      if (timeoutId !== null) clearTimeout(timeoutId);
      signal?.removeEventListener("abort", abortFromUpstream);
    },
  };
}

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
  const timeout = withTimeout(
    options.signal,
    options.timeoutMs ?? CURRENTS_PROXY_TIMEOUT_MS,
  );
  const init: NextRequestInit = {
    method: "GET",
    headers: { accept: "application/json" },
    signal: timeout.signal,
  };

  if (options.next) init.next = options.next;
  if (options.cache) {
    init.cache = options.cache;
  } else if (!options.next) {
    init.cache = "no-store";
  }

  try {
    const res = await fetch(currentsBackendUrl(path, search), init);
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`Currents API ${res.status}${detail ? `: ${detail}` : ""}`);
    }
    return (await res.json()) as T;
  } finally {
    timeout.cleanup();
  }
}

function normalizedVisibility(value: string | null | undefined): string | null {
  const normalized = (value ?? "").trim().toLowerCase().replace(/-/g, "_");
  return normalized || null;
}

function isoDate(value: Date | string | null | undefined): string {
  if (!value) return new Date(0).toISOString();
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function enumString(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

const X_SOURCE_VALUES = new Set(["X", "X_TWITTER", "TWITTER"]);

const INLINE_CONCLUSION_TOKEN_RE = /\s*\[C:[^\]\s]+\]/g;
const GENERIC_X_EVENT_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bThe current event\b/g, "The X post"],
  [/\bthe current event\b/g, "the X post"],
  [/\bCurrent event\b/g, "X post"],
  [/\bcurrent event\b/g, "X post"],
  [/\bThe event's\b/g, "The post's"],
  [/\bthe event's\b/g, "the post's"],
  [/\bThis event's\b/g, "This post's"],
  [/\bthis event's\b/g, "this post's"],
  [/\bThat event's\b/g, "That post's"],
  [/\bthat event's\b/g, "that post's"],
  [/\bIn the event\b/g, "In the post"],
  [/\bin the event\b/g, "in the post"],
  [/\bThe event\b/g, "The post"],
  [/\bthe event\b/g, "the post"],
  [/\bThis event\b/g, "This post"],
  [/\bthis event\b/g, "this post"],
  [/\bThat event\b/g, "That post"],
  [/\bthat event\b/g, "that post"],
  [/\bThe observed event\b/g, "The observed post"],
  [/\bthe observed event\b/g, "the observed post"],
  [/\bThe source post\b/g, "The X post"],
  [/\bthe source post\b/g, "the X post"],
  [/\bsource post\b/g, "X post"],
];
const PUBLIC_SOURCE_LANGUAGE_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bthrough the firm's sources\b/gi, "through the firm's judgment"],
  [/\bbased on the firm's sources\b/gi, "as the firm's opinion"],
  [/\bthe firm's sources\b/gi, "the firm's judgment"],
  [/\bfirm sources\b/gi, "firm reasoning"],
  [/\bretrieved firm conclusions\b/gi, "the firm's recorded conclusions"],
  [/\bretrieved conclusions\b/gi, "the firm's recorded conclusions"],
  [/\bretrieved sources\b/gi, "the firm's recorded reasoning"],
  [/\bsource material\b/gi, "the firm's internal reasoning"],
  [/\bthe sources\b/gi, "the firm's reasoning"],
  [/\bthose sources\b/gi, "that reasoning"],
  [/\bits sources\b/gi, "its judgment"],
  [/\bsingle source\b/gi, "limited firm confidence"],
  [/\bthe data\b/gi, "the firm's judgment"],
];

function sourceSpecificCopy(event: PublicCurrentEvent | null, text: string): string {
  let revised = text;
  if (event && X_SOURCE_VALUES.has(event.source.toUpperCase())) {
    for (const [pattern, replacement] of GENERIC_X_EVENT_REPLACEMENTS) {
      revised = revised.replace(pattern, replacement);
    }
  }
  for (const [pattern, replacement] of PUBLIC_SOURCE_LANGUAGE_REPLACEMENTS) {
    revised = revised.replace(pattern, replacement);
  }
  return revised
    .replace(INLINE_CONCLUSION_TOKEN_RE, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();
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
  return /\[(?:\d+|C:[^\]\s]+)\]/.test(opinion.body_markdown);
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
    reconciliation: opinion.reconciliation ?? null,
  };
}

const RECONCILIATION_ROLE = "counter_claim";
const NO_COUNTER_UNCERTAINTY_TAG = "no_canonical_counter_claim_found";
const NO_COUNTER_FOUND_NOTE = "no canonical counter-claim found in firm history";

interface ReconciliationMetadata {
  role?: unknown;
  reconciliation_markdown?: unknown;
  unresolved_tension?: unknown;
  what_we_would_need_to_know?: unknown;
  strongest_form_of_counter_claim?: unknown;
  no_counter_found?: unknown;
  counter_claim_kind?: unknown;
  counter_claim_id?: unknown;
  counter_claim_similarity?: unknown;
  counter_claim_cascade_weight?: unknown;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asBool(value: unknown): boolean {
  return typeof value === "boolean" ? value : false;
}

function asNumberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function reconciliationFromMetadata(
  metadata: ReconciliationMetadata,
  counterMeta: CitationMetadata | undefined,
  fallbackText: string,
): PublicReconciliation {
  const counterId = asString(metadata.counter_claim_id);
  const counterKind = asString(metadata.counter_claim_kind) || "conclusion";
  const text =
    counterMeta?.conclusionText ??
    fallbackText ??
    null;
  const counter: PublicReconciliationCounter | null = counterId
    ? {
        source_kind: counterKind,
        source_id: counterId,
        quoted_span: fallbackText,
        similarity: asNumberOrNull(metadata.counter_claim_similarity) ?? 0,
        cascade_weight: asNumberOrNull(metadata.counter_claim_cascade_weight),
        conclusion_text: text,
        conclusion_title: counterMeta?.conclusionTitle ?? null,
        public_url: counterMeta?.publicUrl ?? null,
        is_revoked: false,
      }
    : null;
  return {
    no_counter_found: asBool(metadata.no_counter_found),
    reconciliation_markdown: asString(metadata.reconciliation_markdown),
    unresolved_tension: asBool(metadata.unresolved_tension),
    what_we_would_need_to_know: asString(metadata.what_we_would_need_to_know),
    strongest_form_of_counter_claim: asString(
      metadata.strongest_form_of_counter_claim,
    ),
    counter_claim: counter,
  };
}

function honestNoCounterReconciliation(): PublicReconciliation {
  return {
    no_counter_found: true,
    reconciliation_markdown:
      `The firm has searched its own prior conclusions and claims for a ` +
      `canonical counter-claim to this opinion and found none above the ` +
      `similarity floor: ${NO_COUNTER_FOUND_NOTE}. The firm reports the ` +
      `absence rather than papering over it with a fabricated objection.`,
    unresolved_tension: false,
    what_we_would_need_to_know: "",
    strongest_form_of_counter_claim: "",
    counter_claim: null,
  };
}

async function counterConclusionMetadata(
  conclusionIds: string[],
): Promise<Map<string, CitationMetadata>> {
  const out = new Map<string, CitationMetadata>();
  if (!conclusionIds.length) return out;
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
              upload: { select: { visibility: true, deletedAt: true } },
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
    for (const conclusion of conclusions) {
      const visibilities = (conclusion.sources ?? [])
        .map((source) => source.upload)
        .filter((upload) => upload && !upload.deletedAt)
        .map((upload) => normalizedVisibility(upload?.visibility));
      const visibility = visibilities.includes("org")
        ? "org"
        : visibilities.find(Boolean) ?? null;
      const publication = latestPublication.get(conclusion.id);
      const publicUrl =
        visibility === "org" && publication
          ? `/c/${encodeURIComponent(publication.slug)}/v/${publication.version}`
          : null;
      out.set(conclusion.id, {
        conclusionText: conclusion.text ?? null,
        conclusionTitle:
          titleFromPayload(publication?.payloadJson) ||
          titleFromText(conclusion.topicHint) ||
          titleFromText(conclusion.text),
        publicUrl,
        sourceVisibility: visibility,
      });
    }
  } catch {
    // No DB / no env: leave the map empty so the page still renders.
  }
  return out;
}


async function reconciliationsForOpinions(
  opinions: PublicOpinion[],
): Promise<Map<string, PublicReconciliation>> {
  const result = new Map<string, PublicReconciliation>();
  if (!opinions.length) return result;

  for (const opinion of opinions) {
    if (
      Array.isArray(opinion.uncertainty_notes) &&
      opinion.uncertainty_notes.includes(NO_COUNTER_UNCERTAINTY_TAG)
    ) {
      result.set(opinion.id, honestNoCounterReconciliation());
    }
  }

  try {
    const { db } = await import("@/lib/db");
    const client = db as {
      opinionCitation: {
        findMany: (args: unknown) => Promise<
          {
            opinionId: string;
            sourceKind: string;
            conclusionId: string | null;
            claimId: string | null;
            quotedSpan: string;
            justificationMetadata: ReconciliationMetadata | null;
          }[]
        >;
      };
    };
    const rows = await client.opinionCitation.findMany({
      where: { opinionId: { in: opinions.map((opinion) => opinion.id) } },
      select: {
        opinionId: true,
        sourceKind: true,
        conclusionId: true,
        claimId: true,
        quotedSpan: true,
        justificationMetadata: true,
      },
    });

    const counterConclusionIds = new Set<string>();
    for (const row of rows) {
      const metadata = row.justificationMetadata ?? {};
      if (metadata.role !== RECONCILIATION_ROLE) continue;
      if (row.sourceKind?.toLowerCase() === "conclusion" && row.conclusionId) {
        counterConclusionIds.add(row.conclusionId);
      }
    }

    const conclusionMetadata = await counterConclusionMetadata(
      Array.from(counterConclusionIds),
    );

    for (const row of rows) {
      const metadata = row.justificationMetadata ?? {};
      if (metadata.role !== RECONCILIATION_ROLE) continue;
      const sourceId =
        row.conclusionId ?? row.claimId ?? asString(metadata.counter_claim_id);
      if (!sourceId) continue;
      const counterMeta = conclusionMetadata.get(sourceId);
      result.set(
        row.opinionId,
        reconciliationFromMetadata(metadata, counterMeta, row.quotedSpan ?? ""),
      );
    }
  } catch {
    // Without DB access we fall back to whatever the no-counter tag implies.
  }

  return result;
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
  enrichOptions: { skipUpstreamSources?: boolean } = {},
): Promise<PublicOpinion[]> {
  const sourceMetadataResults = enrichOptions.skipUpstreamSources
    ? opinions.map(() => new Map<string, CitationMetadata>())
    : await Promise.all(
        opinions.map((opinion) => citationMetadataFromSources(opinion, options)),
      );
  const [dbMetadata, reconciliations] = await Promise.all([
    citationMetadataFromPublicDb(opinions),
    reconciliationsForOpinions(opinions),
  ]);

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
    const normalized = normalizeOpinion(opinion, merged);
    return {
      ...normalized,
      reconciliation: reconciliations.get(opinion.id) ?? normalized.reconciliation,
    };
  });
}

function listParamsFromSearch(search: URLSearchParams): ListCurrentsParams {
  return {
    since: search.get("since"),
    until: search.get("until"),
    topic: search.get("topic"),
    stance: search.get("stance"),
    limit: search.has("limit") ? Number(search.get("limit")) : undefined,
    seeded: search.has("seeded") ? search.get("seeded") === "true" : undefined,
  };
}

function dateFilter(value: string | Date | null | undefined): Date | undefined {
  if (!value) return undefined;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

function currentEventToPublic(event: {
  id: string;
  source: unknown;
  externalId: string;
  authorHandle: string | null;
  text: string;
  url: string | null;
  capturedAt: Date | string;
  observedAt: Date | string;
  topicHint: string | null;
} | null): PublicCurrentEvent | null {
  if (!event) return null;
  return {
    id: event.id,
    source: enumString(event.source),
    external_id: event.externalId,
    author_handle: event.authorHandle,
    text: event.text,
    url: event.url,
    captured_at: isoDate(event.capturedAt),
    observed_at: isoDate(event.observedAt),
    topic_hint: event.topicHint,
  };
}

function citationSourceId(citation: {
  sourceKind: string;
  conclusionId: string | null;
  claimId: string | null;
}): string {
  const kind = citation.sourceKind.toLowerCase();
  if (kind === "conclusion") return citation.conclusionId ?? "";
  if (kind === "claim") return citation.claimId ?? "";
  return citation.conclusionId ?? citation.claimId ?? "";
}

function citationToPublic(citation: {
  id: string;
  sourceKind: string;
  conclusionId: string | null;
  claimId: string | null;
  quotedSpan: string;
  retrievalScore: number;
  isRevoked: boolean;
}): PublicCitation {
  return {
    id: citation.id,
    source_kind: citation.sourceKind.toLowerCase(),
    source_id: citationSourceId(citation),
    quoted_span: citation.quotedSpan,
    retrieval_score: Number(citation.retrievalScore),
    is_revoked: Boolean(citation.isRevoked),
  };
}

function opinionToPublic(opinion: {
  id: string;
  organizationId: string;
  eventId: string;
  stance: unknown;
  confidence: number;
  headline: string;
  bodyMarkdown: string;
  uncertaintyNotes: string[];
  topicHint: string | null;
  modelName: string;
  generatedAt: Date | string;
  revokedAt: Date | string | null;
  abstentionReason: unknown | null;
  citations: Array<{
    id: string;
    sourceKind: string;
    conclusionId: string | null;
    claimId: string | null;
    quotedSpan: string;
    retrievalScore: number;
    isRevoked: boolean;
  }>;
  event: Parameters<typeof currentEventToPublic>[0];
}): PublicOpinion {
  const event = currentEventToPublic(opinion.event);
  const citations = opinion.citations.map(citationToPublic);
  return {
    id: opinion.id,
    organization_id: opinion.organizationId,
    event_id: opinion.eventId,
    stance: enumString(opinion.stance),
    confidence: Number(opinion.confidence),
    headline: sourceSpecificCopy(event, opinion.headline),
    body_markdown: sourceSpecificCopy(event, opinion.bodyMarkdown),
    uncertainty_notes: (opinion.uncertaintyNotes ?? []).map((note) =>
      sourceSpecificCopy(event, note),
    ),
    topic_hint: opinion.topicHint,
    model_name: opinion.modelName,
    generated_at: isoDate(opinion.generatedAt),
    revoked_at: opinion.revokedAt ? isoDate(opinion.revokedAt) : null,
    abstention_reason: opinion.abstentionReason ? enumString(opinion.abstentionReason) : null,
    revoked_sources_count: citations.filter((citation) => citation.is_revoked).length,
    event,
    citations,
  };
}

async function resolveCurrentsOrganizationId(): Promise<string | null> {
  const { resolvePublicOrganizationId } = await import("@/lib/conclusionsRead");
  return resolvePublicOrganizationId();
}

async function listCurrentsFromPublicDb(
  params: ListCurrentsParams,
  options?: CurrentsFetchOptions,
): Promise<{ items: PublicOpinion[] }> {
  const organizationId = await resolveCurrentsOrganizationId();
  if (!organizationId) return { items: [] };

  const { db } = await import("@/lib/db");
  const client = db as unknown as {
    eventOpinion: {
      findMany: (args: unknown) => Promise<Parameters<typeof opinionToPublic>[0][]>;
    };
  };
  const generatedAt: { gte?: Date; lte?: Date } = {};
  const since = dateFilter(params.since);
  const until = dateFilter(params.until);
  if (since) generatedAt.gte = since;
  if (until) generatedAt.lte = until;

  const where: Record<string, unknown> = { organizationId };
  if (Object.keys(generatedAt).length) where.generatedAt = generatedAt;
  if (params.topic) where.topicHint = params.topic;
  if (params.stance) where.stance = String(params.stance).toUpperCase();

  const rows = await client.eventOpinion.findMany({
    where,
    orderBy: { generatedAt: "desc" },
    take: Math.max(1, Math.min(50, Number(params.limit) || 20)),
    include: {
      event: true,
      citations: true,
    },
  });
  const opinions = rows.map(opinionToPublic);
  return {
    items: await enrichOpinions(opinions, options, { skipUpstreamSources: true }),
  };
}

async function getCurrentFromPublicDb(id: string): Promise<PublicOpinion> {
  const organizationId = await resolveCurrentsOrganizationId();
  if (!organizationId) throw new Error("currents_public_org_unavailable");

  const { db } = await import("@/lib/db");
  const client = db as unknown as {
    eventOpinion: {
      findFirst: (args: unknown) => Promise<Parameters<typeof opinionToPublic>[0] | null>;
    };
  };
  const row = await client.eventOpinion.findFirst({
    where: { id, organizationId },
    include: {
      event: true,
      citations: true,
    },
  });
  if (!row) throw new Error("opinion_not_found");
  return (await enrichOpinions([opinionToPublic(row)], undefined, { skipUpstreamSources: true }))[0];
}

async function getCurrentSourcesFromPublicDb(id: string): Promise<PublicSource[]> {
  const organizationId = await resolveCurrentsOrganizationId();
  if (!organizationId) return [];

  const { db } = await import("@/lib/db");
  const client = db as unknown as {
    eventOpinion: {
      findFirst: (args: unknown) => Promise<{ id: string } | null>;
    };
    opinionCitation: {
      findMany: (args: unknown) => Promise<
        Array<{
          id: string;
          opinionId: string;
          sourceKind: string;
          conclusionId: string | null;
          claimId: string | null;
          quotedSpan: string;
          retrievalScore: number;
          isRevoked: boolean;
          revokedReason: string | null;
        }>
      >;
    };
    conclusion: {
      findMany: (args: unknown) => Promise<Array<{ id: string; text: string }>>;
    };
  };
  const opinion = await client.eventOpinion.findFirst({
    where: { id, organizationId },
    select: { id: true },
  });
  if (!opinion) return [];

  const citations = await client.opinionCitation.findMany({
    where: { opinionId: id },
    orderBy: { id: "asc" },
  });
  const conclusionIds = [
    ...new Set(
      citations
        .filter((citation) => citation.sourceKind.toLowerCase() === "conclusion")
        .map((citation) => citation.conclusionId)
        .filter(Boolean) as string[],
    ),
  ];
  const conclusions = conclusionIds.length
    ? await client.conclusion.findMany({
        where: { id: { in: conclusionIds } },
        select: { id: true, text: true },
      })
    : [];
  const textByConclusionId = new Map(conclusions.map((row) => [row.id, row.text]));

  return citations.map((citation) => {
    const sourceKind = citation.sourceKind.toLowerCase();
    const sourceId = citationSourceId(citation);
    return {
      id: citation.id,
      opinion_id: citation.opinionId,
      source_kind: sourceKind,
      source_id: sourceId,
      source_text:
        sourceKind === "conclusion" && sourceId
          ? textByConclusionId.get(sourceId) ?? ""
          : "",
      quoted_span: citation.quotedSpan,
      retrieval_score: Number(citation.retrievalScore),
      is_revoked: Boolean(citation.isRevoked),
      revoked_reason: citation.revokedReason,
      canonical_path:
        sourceKind === "conclusion" && sourceId
          ? `/c/${sourceId}`
          : sourceKind === "claim" && sourceId
            ? `/conclusions/${sourceId}#claim-${sourceId}`
            : null,
    };
  });
}

async function getCurrentsHealthFromPublicDb(): Promise<CurrentsHealth> {
  const organizationId = await resolveCurrentsOrganizationId();
  if (!organizationId) {
    return {
      x_bearer_present: false,
      curated_count: 0,
      search_count: 0,
      last_cycle_at: null,
      last_event_at: null,
      last_opinion_at: null,
      events_last_24h: 0,
      opinions_last_24h: 0,
      disabled_reasons: ["currents_public_org_unavailable"],
      last_cycle: null,
      db_ok: false,
      db_error: "public organization could not be resolved",
      using_db_fallback: true,
    };
  }
  const { db } = await import("@/lib/db");
  const client = db as unknown as {
    currentEvent: {
      count: (args: unknown) => Promise<number>;
      findFirst: (args: unknown) => Promise<{ createdAt: Date | string } | null>;
    };
    eventOpinion: {
      count: (args: unknown) => Promise<number>;
      findFirst: (args: unknown) => Promise<{ generatedAt: Date | string } | null>;
    };
  };
  const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const [eventsLast24h, opinionsLast24h, lastEvent, lastOpinion] = await Promise.all([
    client.currentEvent.count({
      where: { organizationId, createdAt: { gte: cutoff } },
    }),
    client.eventOpinion.count({
      where: { organizationId, generatedAt: { gte: cutoff } },
    }),
    client.currentEvent.findFirst({
      where: { organizationId },
      orderBy: { createdAt: "desc" },
      select: { createdAt: true },
    }),
    client.eventOpinion.findFirst({
      where: { organizationId },
      orderBy: { generatedAt: "desc" },
      select: { generatedAt: true },
    }),
  ]);
  return {
    x_bearer_present: false,
    curated_count: 0,
    search_count: 0,
    last_cycle_at: null,
    last_event_at: lastEvent ? isoDate(lastEvent.createdAt) : null,
    last_opinion_at: lastOpinion ? isoDate(lastOpinion.generatedAt) : null,
    events_last_24h: eventsLast24h,
    opinions_last_24h: opinionsLast24h,
    disabled_reasons: ["currents_api_unavailable_db_fallback"],
    last_cycle: null,
    db_ok: true,
    db_error: null,
    using_db_fallback: true,
  };
}

export async function listCurrents(
  params: ListCurrentsParams,
  options?: CurrentsFetchOptions,
): Promise<{ items: PublicOpinion[] }> {
  try {
    const result = await fetchJson<{ items: PublicOpinion[] }>(
      "/v1/currents",
      searchParamsFor(params),
      options,
    );
    return { items: await enrichOpinions(result.items, options) };
  } catch (error) {
    try {
      return await listCurrentsFromPublicDb(params, options);
    } catch {
      throw error;
    }
  }
}

export async function getCurrentsHealth(options?: CurrentsFetchOptions): Promise<CurrentsHealth> {
  try {
    return await fetchJson<CurrentsHealth>("/v1/currents/health", undefined, options);
  } catch (error) {
    try {
      return await getCurrentsHealthFromPublicDb();
    } catch {
      throw error;
    }
  }
}

export async function getCurrent(id: string): Promise<PublicOpinion> {
  try {
    const opinion = await fetchJson<PublicOpinion>(`/v1/currents/${encodeURIComponent(id)}`);
    return (await enrichOpinions([opinion]))[0];
  } catch (error) {
    try {
      return await getCurrentFromPublicDb(id);
    } catch {
      throw error;
    }
  }
}

export async function getCurrentSources(id: string): Promise<PublicSource[]> {
  try {
    return await fetchJson<PublicSource[]>(`/v1/currents/${encodeURIComponent(id)}/sources`);
  } catch (error) {
    try {
      return await getCurrentSourcesFromPublicDb(id);
    } catch {
      throw error;
    }
  }
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

async function currentsFallbackResponse(
  req: Request,
  path: string,
): Promise<Response | null> {
  if (req.method !== "GET") return null;
  const sourceUrl = new URL(req.url);
  try {
    if (path === "/v1/currents") {
      const result = await listCurrentsFromPublicDb(
        listParamsFromSearch(sourceUrl.searchParams),
      );
      return Response.json(result);
    }
    if (path === "/v1/currents/health") {
      return Response.json(await getCurrentsHealthFromPublicDb());
    }

    const sourceMatch = path.match(/^\/v1\/currents\/([^/]+)\/sources$/);
    if (sourceMatch) {
      return Response.json(
        await getCurrentSourcesFromPublicDb(decodeURIComponent(sourceMatch[1])),
      );
    }
    const detailMatch = path.match(/^\/v1\/currents\/([^/]+)$/);
    if (detailMatch) {
      return Response.json(
        await getCurrentFromPublicDb(decodeURIComponent(detailMatch[1])),
      );
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "db fallback failed";
    const status = message === "opinion_not_found" ? 404 : 503;
    return Response.json(
      {
        error: status === 404 ? "opinion_not_found" : "currents_db_fallback_unavailable",
        detail: message,
      },
      { status },
    );
  }
  return null;
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
    if (!upstream.ok && upstream.status >= 500) {
      const fallback = await currentsFallbackResponse(req, path);
      if (fallback) return fallback;
    }
    return options.sse ? proxySseResponse(upstream) : proxyResponse(upstream);
  } catch (error) {
    const fallback = await currentsFallbackResponse(req, path);
    if (fallback) return fallback;
    return upstreamUnavailable(error);
  }
}
