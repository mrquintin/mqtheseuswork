import { db } from "@/lib/db";
import { parseMethodologyPayload } from "@/lib/methodologyProfiles";
import type { PublicationPayloadV1 } from "@/lib/publicationService";

export type PublicCitation = PublicationPayloadV1["citations"][number];

export type PublishedArticleCitation = NonNullable<PublicationPayloadV1["article"]>["citations"][number] & {
  sourceConclusionText: string | null;
  sourceConclusionTitle: string | null;
};

export type PublishedArticlePayload = Omit<NonNullable<PublicationPayloadV1["article"]>, "citations"> & {
  citations: PublishedArticleCitation[];
};

export type PublishedPublicationPayload = Omit<PublicationPayloadV1, "article"> & {
  article?: PublishedArticlePayload;
};

export type PublishedConclusion = {
  id: string;
  kind: string;
  slug: string;
  version: number;
  sourceConclusionId: string;
  publishedAt: string;
  doi: string;
  zenodoRecordId: string;
  discountedConfidence: number;
  statedConfidence: number;
  calibrationDiscountReason: string;
  payload: PublishedPublicationPayload;
};

export type PublicResponse = {
  id: string;
  publishedConclusionId: string;
  kind: string;
  body: string;
  citationUrl: string;
  status: string;
  createdAt: string;
  pseudonymous: boolean;
};

export type PublishedBundle = {
  schema: "theseus.publishedExport.v1";
  generatedAt: string;
  conclusions: PublishedConclusion[];
  openQuestions: [];
  responses: PublicResponse[];
};

type PublishedConclusionRow = {
  id: string;
  kind?: string;
  slug: string;
  version: number;
  sourceConclusionId: string;
  publishedAt: Date | string;
  doi: string;
  zenodoRecordId: string;
  discountedConfidence: number;
  statedConfidence: number;
  calibrationDiscountReason: string;
  payloadJson: string;
};

type PublicResponseRow = {
  id: string;
  publishedConclusionId: string;
  kind: string;
  body: string;
  citationUrl: string;
  status: string;
  createdAt: Date;
  pseudonymous: boolean;
};

export type PublicationPayloadJsonRow = {
  payloadJson: string;
  slug: string;
};

const PUBLISHED_CONCLUSION_SELECT = {
  id: true,
  kind: true,
  slug: true,
  version: true,
  sourceConclusionId: true,
  publishedAt: true,
  doi: true,
  zenodoRecordId: true,
  discountedConfidence: true,
  statedConfidence: true,
  calibrationDiscountReason: true,
  payloadJson: true,
};

const PUBLIC_RESPONSE_SELECT = {
  id: true,
  publishedConclusionId: true,
  kind: true,
  body: true,
  citationUrl: true,
  status: true,
  createdAt: true,
  pseudonymous: true,
};

const PUBLIC_TITLE_MAX_CHARS = 70;

function warnIfLongTitle(title: string) {
  const n = title.length;
  if (n > PUBLIC_TITLE_MAX_CHARS) {
    console.warn("[title-policy] long title (%d chars): %s", n, title);
  }
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function publicSourceUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const url = value.trim();
  if (!url) return null;
  if (/^\/(?:c|post|currents|forecasts)(?:\/|$)/.test(url)) return url;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

function parseArticlePayload(value: unknown): PublishedArticlePayload | undefined {
  const article = objectValue(value);
  const bodyMarkdown =
    typeof article.bodyMarkdown === "string" ? article.bodyMarkdown
    : typeof article.body_markdown === "string" ? article.body_markdown
    : "";
  const rawCitations = Array.isArray(article.citations) ? article.citations : [];
  const citations = rawCitations.flatMap((item, index): PublishedArticleCitation[] => {
    const citation = objectValue(item);
    const sourceKind =
      typeof citation.sourceKind === "string" ? citation.sourceKind
      : typeof citation.source_kind === "string" ? citation.source_kind
      : "";
    const sourceId =
      typeof citation.sourceId === "string" ? citation.sourceId
      : typeof citation.source_id === "string" ? citation.source_id
      : "";
    const quotedSpan =
      typeof citation.quotedSpan === "string" ? citation.quotedSpan
      : typeof citation.quoted_span === "string" ? citation.quoted_span
      : "";
    if (!sourceKind || !sourceId || !quotedSpan) return [];
    const publicUrl = publicSourceUrl(citation.publicUrl ?? citation.public_url);
    return [
      {
        label:
          typeof citation.label === "string" && citation.label.trim()
            ? citation.label.trim()
            : `S${index + 1}`,
        sourceKind,
        sourceId,
        quotedSpan,
        publicUrl,
        linkable: Boolean(publicUrl),
        sourceConclusionText: optionalText(citation.sourceConclusionText ?? citation.source_conclusion_text),
        sourceConclusionTitle: optionalText(citation.sourceConclusionTitle ?? citation.source_conclusion_title),
      },
    ];
  });

  if (!bodyMarkdown && citations.length === 0) return undefined;
  return {
    kind: typeof article.kind === "string" ? article.kind : "",
    bodyMarkdown,
    sourceIds: stringArray(article.sourceIds ?? article.source_ids),
    ...(typeof article.sourceKey === "string" ? { sourceKey: article.sourceKey } : {}),
    citations,
  };
}

export function parsePublicationPayload(row: PublicationPayloadJsonRow): PublishedPublicationPayload {
  let parsed: Record<string, unknown> = {};
  try {
    const value = JSON.parse(row.payloadJson);
    if (value && typeof value === "object" && !Array.isArray(value)) {
      parsed = value as Record<string, unknown>;
    }
  } catch {
    parsed = {};
  }

  const strongestObjection =
    parsed.strongestObjection && typeof parsed.strongestObjection === "object" && !Array.isArray(parsed.strongestObjection)
      ? (parsed.strongestObjection as Record<string, unknown>)
      : {};

  const citations: PublicCitation[] = Array.isArray(parsed.citations)
    ? parsed.citations.flatMap((item): PublicCitation[] => {
        if (!item || typeof item !== "object" || Array.isArray(item)) return [];
        const citation = item as Record<string, unknown>;
        if (
          (citation.format === "bibtex" || citation.format === "apa" || citation.format === "ris") &&
          typeof citation.block === "string"
        ) {
          return [{ format: citation.format, block: citation.block }];
        }
        return [];
      })
    : [];

  const timeline =
    Array.isArray(parsed.timeline)
      ? parsed.timeline.flatMap((item): PublicationPayloadV1["timeline"] => {
          if (!item || typeof item !== "object" || Array.isArray(item)) return [];
          const event = item as Record<string, unknown>;
          if (typeof event.at !== "string" || typeof event.label !== "string") return [];
          return [
            {
              at: event.at,
              label: event.label,
              ...(typeof event.detail === "string" ? { detail: event.detail } : {}),
            },
          ];
        })
      : [];

  const voiceComparisons =
    Array.isArray(parsed.voiceComparisons)
      ? parsed.voiceComparisons.flatMap((item): PublicationPayloadV1["voiceComparisons"] => {
          if (!item || typeof item !== "object" || Array.isArray(item)) return [];
          const voice = item as Record<string, unknown>;
          if (typeof voice.voice !== "string" || typeof voice.stance !== "string") return [];
          return [{ voice: voice.voice, stance: voice.stance }];
        })
      : [];

  const exitConditions = stringArray(parsed.exitConditions);
  const whatWouldChangeOurMind = stringArray(parsed.whatWouldChangeOurMind);
  const article = parseArticlePayload(parsed.article);

  return {
    schema: "theseus.publicConclusion.v1",
    conclusionText: typeof parsed.conclusionText === "string" ? parsed.conclusionText : row.slug,
    rationale: typeof parsed.rationale === "string" ? parsed.rationale : "",
    topicHint: typeof parsed.topicHint === "string" ? parsed.topicHint : "",
    evidenceSummary: typeof parsed.evidenceSummary === "string" ? parsed.evidenceSummary : "",
    exitConditions,
    strongestObjection: {
      objection: typeof strongestObjection.objection === "string" ? strongestObjection.objection : "",
      firmAnswer: typeof strongestObjection.firmAnswer === "string" ? strongestObjection.firmAnswer : "",
    },
    openQuestionsAdjacent: stringArray(parsed.openQuestionsAdjacent),
    voiceComparisons,
    methodology: parseMethodologyPayload(parsed.methodology),
    timeline,
    whatWouldChangeOurMind: whatWouldChangeOurMind.length ? whatWouldChangeOurMind : exitConditions,
    citations,
    ...(Array.isArray(parsed.internalLinks) ? { internalLinks: [] } : {}),
    ...(article ? { article } : {}),
  };
}

function toPublishedConclusion(row: PublishedConclusionRow): PublishedConclusion {
  const payload = parsePublicationPayload(row);
  warnIfLongTitle(payload.conclusionText);

  return {
    id: row.id,
    kind: row.kind || "CONCLUSION",
    slug: row.slug,
    version: row.version,
    sourceConclusionId: row.sourceConclusionId,
    publishedAt: row.publishedAt instanceof Date ? row.publishedAt.toISOString() : new Date(row.publishedAt).toISOString(),
    doi: row.doi,
    zenodoRecordId: row.zenodoRecordId,
    discountedConfidence: row.discountedConfidence,
    statedConfidence: row.statedConfidence,
    calibrationDiscountReason: row.calibrationDiscountReason,
    payload,
  };
}

function toPublicResponse(row: PublicResponseRow): PublicResponse {
  return {
    id: row.id,
    publishedConclusionId: row.publishedConclusionId,
    kind: row.kind,
    body: row.body,
    citationUrl: row.citationUrl,
    status: row.status,
    createdAt: row.createdAt.toISOString(),
    pseudonymous: row.pseudonymous,
  };
}

type DbFindMany<T> = {
  findMany: (args: Record<string, unknown>) => Promise<T[]>;
};

type SourceLookupDb = {
  conclusion?: DbFindMany<{
    id: string;
    text: string;
    sources?: {
      upload?: {
        visibility: string;
        publishedAt: Date | string | null;
        slug: string | null;
      } | null;
    }[];
  }>;
  eventOpinion?: DbFindMany<{
    id: string;
    headline: string;
    revokedAt: Date | string | null;
  }>;
  forecastPrediction?: DbFindMany<{
    id: string;
    headline: string;
  }>;
};

type CitationSourceMetadata = {
  sourceConclusionText: string | null;
  sourceConclusionTitle: string | null;
  publicLinkConfirmed: boolean;
};

const CONCLUSION_SOURCE_KINDS = new Set(["conclusion", "claim", "principle", "firm_conclusion", "source_conclusion"]);

function normalizedSourceKind(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function citationSourceKey(sourceKind: string, sourceId: string): string {
  return `${normalizedSourceKind(sourceKind)}:${sourceId}`;
}

function idsForKind(sourceIdsByKind: Map<string, Set<string>>, ...sourceKinds: string[]): string[] {
  const ids = new Set<string>();
  for (const sourceKind of sourceKinds) {
    const sourceIds = sourceIdsByKind.get(normalizedSourceKind(sourceKind));
    if (!sourceIds) continue;
    for (const id of sourceIds) ids.add(id);
  }
  return [...ids];
}

function collectArticleCitationSourceIds(rows: PublishedConclusion[]): Map<string, Set<string>> {
  const sourceIdsByKind = new Map<string, Set<string>>();
  for (const row of rows) {
    for (const citation of row.payload.article?.citations ?? []) {
      const sourceKind = normalizedSourceKind(citation.sourceKind);
      if (!sourceKind || !citation.sourceId) continue;
      const existing = sourceIdsByKind.get(sourceKind) ?? new Set<string>();
      existing.add(citation.sourceId);
      sourceIdsByKind.set(sourceKind, existing);
    }
  }
  return sourceIdsByKind;
}

function hasPublicOrgUpload(
  sources:
    | {
        upload?: {
          visibility: string;
          publishedAt: Date | string | null;
          slug: string | null;
        } | null;
      }[]
    | undefined,
): boolean {
  return Boolean(
    sources?.some(({ upload }) => upload?.visibility === "org" && Boolean(upload.publishedAt) && Boolean(upload.slug)),
  );
}

async function addConclusionCitationMetadata(
  organizationId: string,
  sourceIdsByKind: Map<string, Set<string>>,
  sourceMetadata: Map<string, CitationSourceMetadata>,
) {
  const ids = new Set<string>();
  for (const sourceKind of CONCLUSION_SOURCE_KINDS) {
    for (const id of idsForKind(sourceIdsByKind, sourceKind)) ids.add(id);
  }
  if (!ids.size) return;

  const conclusionDb = (db as unknown as SourceLookupDb).conclusion;
  if (!conclusionDb) return;

  const rows = await conclusionDb.findMany({
    where: { organizationId, id: { in: [...ids] } },
    select: {
      id: true,
      text: true,
      sources: {
        select: {
          upload: {
            select: {
              visibility: true,
              publishedAt: true,
              slug: true,
            },
          },
        },
      },
    },
  });

  for (const row of rows) {
    const metadata = {
      sourceConclusionText: row.text,
      sourceConclusionTitle: null,
      publicLinkConfirmed: hasPublicOrgUpload(row.sources),
    };
    for (const sourceKind of CONCLUSION_SOURCE_KINDS) {
      sourceMetadata.set(citationSourceKey(sourceKind, row.id), metadata);
    }
  }
}

async function addEventOpinionCitationMetadata(
  organizationId: string,
  sourceIdsByKind: Map<string, Set<string>>,
  sourceMetadata: Map<string, CitationSourceMetadata>,
) {
  const ids = idsForKind(sourceIdsByKind, "event_opinion", "correction");
  if (!ids.length) return;

  const eventOpinionDb = (db as unknown as SourceLookupDb).eventOpinion;
  if (!eventOpinionDb) return;

  const rows = await eventOpinionDb.findMany({
    where: { organizationId, id: { in: ids } },
    select: { id: true, headline: true, revokedAt: true },
  });

  for (const row of rows) {
    const publicLinkConfirmed = !row.revokedAt;
    sourceMetadata.set(citationSourceKey("event_opinion", row.id), {
      sourceConclusionText: row.headline,
      sourceConclusionTitle: row.headline,
      publicLinkConfirmed,
    });
    sourceMetadata.set(citationSourceKey("correction", row.id), {
      sourceConclusionText: `Correction to: ${row.headline}`,
      sourceConclusionTitle: row.headline,
      publicLinkConfirmed,
    });
  }
}

async function addForecastCitationMetadata(
  organizationId: string,
  sourceIdsByKind: Map<string, Set<string>>,
  sourceMetadata: Map<string, CitationSourceMetadata>,
) {
  const ids = idsForKind(sourceIdsByKind, "forecast_postmortem");
  if (!ids.length) return;

  const forecastDb = (db as unknown as SourceLookupDb).forecastPrediction;
  if (!forecastDb) return;

  const rows = await forecastDb.findMany({
    where: { organizationId, id: { in: ids } },
    select: { id: true, headline: true },
  });

  for (const row of rows) {
    sourceMetadata.set(citationSourceKey("forecast_postmortem", row.id), {
      sourceConclusionText: row.headline,
      sourceConclusionTitle: row.headline,
      publicLinkConfirmed: true,
    });
  }
}

async function enrichArticleCitationSources(
  rows: PublishedConclusion[],
  organizationId: string,
): Promise<PublishedConclusion[]> {
  const sourceIdsByKind = collectArticleCitationSourceIds(rows);
  if (!sourceIdsByKind.size) return rows;

  const sourceMetadata = new Map<string, CitationSourceMetadata>();
  await Promise.all([
    addConclusionCitationMetadata(organizationId, sourceIdsByKind, sourceMetadata),
    addEventOpinionCitationMetadata(organizationId, sourceIdsByKind, sourceMetadata),
    addForecastCitationMetadata(organizationId, sourceIdsByKind, sourceMetadata),
  ]);

  return rows.map((row) => {
    const article = row.payload.article;
    if (!article?.citations.length) return row;

    return {
      ...row,
      payload: {
        ...row.payload,
        article: {
          ...article,
          citations: article.citations.map((citation) => {
            const metadata = sourceMetadata.get(citationSourceKey(citation.sourceKind, citation.sourceId));
            const sourceConclusionText = metadata?.sourceConclusionText ?? citation.sourceConclusionText;
            const sourceConclusionTitle = metadata?.sourceConclusionTitle ?? citation.sourceConclusionTitle;
            const publicUrl = metadata?.publicLinkConfirmed && citation.publicUrl ? citation.publicUrl : null;
            return {
              ...citation,
              sourceConclusionText,
              sourceConclusionTitle,
              publicUrl,
              linkable: Boolean(publicUrl),
            };
          }),
        },
      },
    };
  });
}

export async function resolvePublicOrganizationId(): Promise<string | null> {
  const explicitId = (
    process.env.THESEUS_PUBLIC_ORG_ID?.trim() ||
    process.env.CURRENTS_INGEST_ORG_ID?.trim() ||
    ""
  );
  if (explicitId) {
    const org = await db.organization.findUnique({
      where: { id: explicitId },
      select: { id: true, deletedAt: true },
    });
    return org && !org.deletedAt ? org.id : null;
  }

  const slug =
    process.env.THESEUS_PUBLIC_ORG_SLUG?.trim() ||
    process.env.DEFAULT_ORGANIZATION_SLUG?.trim() ||
    process.env.NEXT_PUBLIC_DEFAULT_ORG_SLUG?.trim() ||
    "";

  if (slug) {
    const org = await db.organization.findUnique({
      where: { slug },
      select: { id: true, deletedAt: true },
    });
    return org && !org.deletedAt ? org.id : null;
  }

  const orgs = await db.organization.findMany({
    where: { deletedAt: null },
    orderBy: { createdAt: "asc" },
    take: 2,
    select: { id: true },
  });
  return orgs.length === 1 ? orgs[0].id : null;
}

export async function listPublishedConclusions(): Promise<PublishedConclusion[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const rows = await db.publishedConclusion.findMany({
    where: { organizationId },
    orderBy: [{ slug: "asc" }, { version: "asc" }],
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return enrichArticleCitationSources((rows as PublishedConclusionRow[]).map(toPublishedConclusion), organizationId);
}

export async function listPublishedConclusionsForFeed(): Promise<PublishedConclusion[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const rows = await db.publishedConclusion.findMany({
    where: { organizationId },
    orderBy: { publishedAt: "desc" },
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return enrichArticleCitationSources((rows as PublishedConclusionRow[]).map(toPublishedConclusion), organizationId);
}

export async function listPublishedArticles(limit = 8): Promise<PublishedConclusion[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  try {
    const rows = await db.$queryRaw<PublishedConclusionRow[]>`
      SELECT
        id,
        kind,
        slug,
        version,
        "sourceConclusionId",
        "publishedAt",
        doi,
        "zenodoRecordId",
        "discountedConfidence",
        "statedConfidence",
        "calibrationDiscountReason",
        "payloadJson"
      FROM "PublishedConclusion"
      WHERE "organizationId" = ${organizationId}
        AND kind = 'ARTICLE'
      ORDER BY "publishedAt" DESC
      LIMIT ${limit}
    `;
    return enrichArticleCitationSources(rows.map(toPublishedConclusion), organizationId);
  } catch (error) {
    console.error("[public] article query failed (schema lag?):", error);
    return [];
  }
}

/**
 * Unified shape for the homepage Publications rail. Bridges the two
 * publication paths: PublishedConclusion (kind=ARTICLE → /c/[slug])
 * and Upload (publishedAt!=null, visibility='org' → /post/[slug]).
 * Whatever flips the underlying "is published" bit, the homepage
 * surfaces it here within one render cycle.
 */
export type HomepagePublishedArticle = {
  id: string;
  href: string;
  title: string;
  excerpt: string;
  publishedAt: string;
  source: "upload" | "conclusion";
};

type PublishedUploadRow = {
  id: string;
  slug: string | null;
  title: string;
  blogExcerpt: string | null;
  description: string | null;
  textContent: string | null;
  publishedAt: Date | string | null;
};

function deriveHomepageExcerpt(text: string, limit = 200): string {
  const cleaned = text.replace(/[#>*_`-]/g, " ").replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= limit) return cleaned;
  const cut = cleaned.slice(0, limit);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > limit * 0.65 ? cut.slice(0, lastSpace) : cut) + "…";
}

async function listHomepageUploadPosts(
  organizationId: string,
  limit: number,
): Promise<HomepagePublishedArticle[]> {
  try {
    const rows = (await db.upload.findMany({
      where: {
        organizationId,
        publishedAt: { not: null },
        deletedAt: null,
        visibility: "org",
        slug: { not: null },
      },
      orderBy: [{ publishedAt: "desc" }, { id: "asc" }],
      take: limit,
      select: {
        id: true,
        slug: true,
        title: true,
        blogExcerpt: true,
        description: true,
        textContent: true,
        publishedAt: true,
      },
    })) as unknown as PublishedUploadRow[];

    return rows.flatMap((row): HomepagePublishedArticle[] => {
      if (!row.slug || !row.publishedAt) return [];
      const publishedAt =
        row.publishedAt instanceof Date
          ? row.publishedAt.toISOString()
          : new Date(row.publishedAt).toISOString();
      const excerptSource =
        row.blogExcerpt || row.description || row.textContent || "";
      return [
        {
          id: row.id,
          href: `/post/${encodeURIComponent(row.slug)}`,
          title: row.title,
          excerpt: deriveHomepageExcerpt(excerptSource),
          publishedAt,
          source: "upload",
        },
      ];
    });
  } catch (error) {
    console.error("[public] upload publication query failed:", error);
    return [];
  }
}

function homepageArticleFromConclusion(
  row: PublishedConclusion,
): HomepagePublishedArticle {
  const excerptSource =
    row.payload.article?.bodyMarkdown ||
    row.payload.evidenceSummary ||
    row.payload.rationale ||
    "";
  return {
    id: row.id,
    href: `/c/${encodeURIComponent(row.slug)}`,
    title: row.payload.conclusionText,
    excerpt: deriveHomepageExcerpt(excerptSource),
    publishedAt: row.publishedAt,
    source: "conclusion",
  };
}

/**
 * Single source of truth for the homepage Publications rail. Merges
 * both publish paths, orders by publishedAt desc with a stable id-asc
 * secondary so two near-simultaneous publishes don't flip on refresh,
 * then trims to `limit`.
 */
export async function listHomepagePublishedArticles(
  limit = 8,
): Promise<HomepagePublishedArticle[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const [conclusionArticles, uploadPosts] = await Promise.all([
    listPublishedArticles(limit),
    listHomepageUploadPosts(organizationId, limit),
  ]);

  const merged: HomepagePublishedArticle[] = [
    ...conclusionArticles.map(homepageArticleFromConclusion),
    ...uploadPosts,
  ];

  merged.sort((a, b) => {
    if (a.publishedAt === b.publishedAt) return a.id < b.id ? -1 : 1;
    return a.publishedAt < b.publishedAt ? 1 : -1;
  });

  return merged.slice(0, limit);
}

export async function getConclusionBySlug(slug: string): Promise<PublishedConclusion | null> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return null;

  const rows = await db.publishedConclusion.findMany({
    where: { organizationId, slug },
    orderBy: { version: "desc" },
    take: 1,
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  const row = rows[0] as PublishedConclusionRow | undefined;
  return row ? (await enrichArticleCitationSources([toPublishedConclusion(row)], organizationId))[0] : null;
}

export async function getConclusionVersion(slug: string, version: number): Promise<PublishedConclusion | null> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return null;

  const row = await db.publishedConclusion.findFirst({
    where: { organizationId, slug, version },
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return row ? (await enrichArticleCitationSources([toPublishedConclusion(row as PublishedConclusionRow)], organizationId))[0] : null;
}

export async function listConclusionVersions(slug: string): Promise<PublishedConclusion[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const rows = await db.publishedConclusion.findMany({
    where: { organizationId, slug },
    orderBy: { version: "asc" },
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return enrichArticleCitationSources((rows as PublishedConclusionRow[]).map(toPublishedConclusion), organizationId);
}

export async function responsesForPublishedId(publishedConclusionId: string): Promise<PublicResponse[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const rows = await db.publicResponse.findMany({
    where: {
      organizationId,
      publishedConclusionId,
      status: { in: ["approved", "engaged"] },
    },
    orderBy: { createdAt: "desc" },
    select: PUBLIC_RESPONSE_SELECT,
  });
  return (rows as PublicResponseRow[]).map(toPublicResponse);
}

export async function buildPublishedBundle(): Promise<PublishedBundle> {
  const conclusions = await listPublishedConclusions();
  const responses = conclusions.length
    ? await Promise.all(conclusions.map((row) => responsesForPublishedId(row.id))).then((groups) => groups.flat())
    : [];

  return {
    schema: "theseus.publishedExport.v1",
    generatedAt: new Date().toISOString(),
    conclusions,
    openQuestions: [],
    responses,
  };
}
