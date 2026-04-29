import { db } from "@/lib/db";
import type { PublicationPayloadV1 } from "@/lib/publicationService";

export type PublicCitation = PublicationPayloadV1["citations"][number];

export type PublishedConclusion = {
  id: string;
  slug: string;
  version: number;
  sourceConclusionId: string;
  publishedAt: string;
  doi: string;
  zenodoRecordId: string;
  discountedConfidence: number;
  statedConfidence: number;
  calibrationDiscountReason: string;
  payload: PublicationPayloadV1;
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
  slug: string;
  version: number;
  sourceConclusionId: string;
  publishedAt: Date;
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

const PUBLISHED_CONCLUSION_SELECT = {
  id: true,
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

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function parsePayload(row: Pick<PublishedConclusionRow, "payloadJson" | "slug">): PublicationPayloadV1 {
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
    timeline,
    whatWouldChangeOurMind: whatWouldChangeOurMind.length ? whatWouldChangeOurMind : exitConditions,
    citations,
    ...(Array.isArray(parsed.internalLinks) ? { internalLinks: [] } : {}),
  };
}

function toPublishedConclusion(row: PublishedConclusionRow): PublishedConclusion {
  return {
    id: row.id,
    slug: row.slug,
    version: row.version,
    sourceConclusionId: row.sourceConclusionId,
    publishedAt: row.publishedAt.toISOString(),
    doi: row.doi,
    zenodoRecordId: row.zenodoRecordId,
    discountedConfidence: row.discountedConfidence,
    statedConfidence: row.statedConfidence,
    calibrationDiscountReason: row.calibrationDiscountReason,
    payload: parsePayload(row),
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

async function resolvePublicOrganizationId(): Promise<string | null> {
  const explicitSlug = process.env.THESEUS_PUBLIC_ORG_SLUG?.trim();
  const devFallbackSlug =
    process.env.NODE_ENV === "production"
      ? ""
      : process.env.DEFAULT_ORGANIZATION_SLUG?.trim() || process.env.NEXT_PUBLIC_DEFAULT_ORG_SLUG?.trim() || "";
  const slug = explicitSlug || devFallbackSlug;

  if (slug) {
    const org = await db.organization.findUnique({
      where: { slug },
      select: { id: true, deletedAt: true },
    });
    return org && !org.deletedAt ? org.id : null;
  }

  if (process.env.NODE_ENV !== "production") {
    const orgs = await db.organization.findMany({
      where: { deletedAt: null },
      orderBy: { createdAt: "asc" },
      take: 2,
      select: { id: true },
    });
    return orgs.length === 1 ? orgs[0].id : null;
  }

  return null;
}

export async function listPublishedConclusions(): Promise<PublishedConclusion[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const rows = await db.publishedConclusion.findMany({
    where: { organizationId },
    orderBy: [{ slug: "asc" }, { version: "asc" }],
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return (rows as PublishedConclusionRow[]).map(toPublishedConclusion);
}

export async function listPublishedConclusionsForFeed(): Promise<PublishedConclusion[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const rows = await db.publishedConclusion.findMany({
    where: { organizationId },
    orderBy: { publishedAt: "desc" },
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return (rows as PublishedConclusionRow[]).map(toPublishedConclusion);
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
  return row ? toPublishedConclusion(row) : null;
}

export async function getConclusionVersion(slug: string, version: number): Promise<PublishedConclusion | null> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return null;

  const row = await db.publishedConclusion.findFirst({
    where: { organizationId, slug, version },
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return row ? toPublishedConclusion(row as PublishedConclusionRow) : null;
}

export async function listConclusionVersions(slug: string): Promise<PublishedConclusion[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const rows = await db.publishedConclusion.findMany({
    where: { organizationId, slug },
    orderBy: { version: "asc" },
    select: PUBLISHED_CONCLUSION_SELECT,
  });
  return (rows as PublishedConclusionRow[]).map(toPublishedConclusion);
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
