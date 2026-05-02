import { Prisma } from "@prisma/client";

import { db } from "@/lib/db";

export type PublicationMethodologyProfile = {
  patternType: string;
  title: string;
  summary: string;
  reasoningMoves: string[];
  transferTargets: string[];
  assumptions: string[];
  failureModes: string[];
  evidenceAnchors: { sentenceIndex?: number; sourceTitle?: string }[];
  confidence: number;
};

export type PublicationMethodology = {
  schema: "theseus.methodology.v1";
  reviewerNarrative: string;
  profiles: PublicationMethodologyProfile[];
};

type MethodologyProfileRow = {
  id: string;
  conclusionId: string | null;
  sourceConclusionId: string | null;
  patternType: string;
  title: string;
  summary: string;
  reasoningMoves: unknown;
  transferTargets: unknown;
  assumptions: unknown;
  failureModes: unknown;
  evidenceAnchors: unknown;
  confidence: number | string;
};

const MAX_PROFILE_COUNT = 8;
const MAX_LIST_ITEMS = 12;

function cleanString(value: unknown, maxLength: number): string {
  if (typeof value !== "string") return "";
  return value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufeff]/g, "").trim().slice(0, maxLength);
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => cleanString(item, 600))
    .filter(Boolean)
    .slice(0, MAX_LIST_ITEMS);
}

function confidenceValue(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value || 0.5);
  if (!Number.isFinite(n)) return 0.5;
  return Math.min(1, Math.max(0, n));
}

function anchorArray(value: unknown): PublicationMethodologyProfile["evidenceAnchors"] {
  if (!Array.isArray(value)) return [];
  // Evidence anchors are allowed to preserve public-safe provenance metadata,
  // but never the underlying transcript quote text.
  return value.flatMap((item): PublicationMethodologyProfile["evidenceAnchors"] => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const raw = item as Record<string, unknown>;
    const sentenceIndex =
      typeof raw.sentenceIndex === "number" && Number.isFinite(raw.sentenceIndex) && raw.sentenceIndex >= 0
        ? Math.trunc(raw.sentenceIndex)
        : undefined;
    const sourceTitle = cleanString(raw.sourceTitle, 180);
    if (sentenceIndex === undefined && !sourceTitle) return [];
    return [{ ...(sentenceIndex !== undefined ? { sentenceIndex } : {}), ...(sourceTitle ? { sourceTitle } : {}) }];
  }).slice(0, MAX_LIST_ITEMS);
}

export function normalizeMethodologyProfiles(value: unknown): PublicationMethodologyProfile[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): PublicationMethodologyProfile[] => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const raw = item as Record<string, unknown>;
    const title = cleanString(raw.title, 180);
    const summary = cleanString(raw.summary, 4_000);
    if (!title || !summary) return [];
    return [
      {
        patternType: cleanString(raw.patternType, 80) || "manual_methodology",
        title,
        summary,
        reasoningMoves: stringArray(raw.reasoningMoves),
        transferTargets: stringArray(raw.transferTargets),
        assumptions: stringArray(raw.assumptions),
        failureModes: stringArray(raw.failureModes),
        evidenceAnchors: anchorArray(raw.evidenceAnchors),
        confidence: confidenceValue(raw.confidence),
      },
    ];
  }).slice(0, MAX_PROFILE_COUNT);
}

export function parseMethodologyPayload(value: unknown): PublicationMethodology {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { schema: "theseus.methodology.v1", reviewerNarrative: "", profiles: [] };
  }
  const raw = value as Record<string, unknown>;
  return {
    schema: "theseus.methodology.v1",
    reviewerNarrative: cleanString(raw.reviewerNarrative, 4_000),
    profiles: normalizeMethodologyProfiles(raw.profiles),
  };
}

export function hasMethodologyContent(methodology: PublicationMethodology): boolean {
  return methodology.profiles.length > 0 || methodology.reviewerNarrative.trim().length > 0;
}

function rowToProfile(row: MethodologyProfileRow): PublicationMethodologyProfile {
  return {
    patternType: cleanString(row.patternType, 80) || "manual_methodology",
    title: cleanString(row.title, 180),
    summary: cleanString(row.summary, 4_000),
    reasoningMoves: stringArray(row.reasoningMoves),
    transferTargets: stringArray(row.transferTargets),
    assumptions: stringArray(row.assumptions),
    failureModes: stringArray(row.failureModes),
    evidenceAnchors: anchorArray(row.evidenceAnchors),
    confidence: confidenceValue(row.confidence),
  };
}

function hasDisplayableProfile(profile: PublicationMethodologyProfile): boolean {
  return Boolean(profile.title && profile.summary);
}

export async function profilesForConclusions(
  organizationId: string,
  conclusionIds: string[],
): Promise<Map<string, PublicationMethodologyProfile[]>> {
  const ids = [...new Set(conclusionIds.filter(Boolean))];
  const out = new Map<string, PublicationMethodologyProfile[]>();
  if (ids.length === 0) return out;

  try {
    const rows = await db.$queryRaw<MethodologyProfileRow[]>`
      SELECT
        mp.id,
        mp."conclusionId",
        cs."conclusionId" AS "sourceConclusionId",
        mp."patternType",
        mp.title,
        mp.summary,
        mp."reasoningMoves",
        mp."transferTargets",
        mp.assumptions,
        mp."failureModes",
        mp."evidenceAnchors",
        mp.confidence
      FROM "MethodologyProfile" mp
      LEFT JOIN "ConclusionSource" cs ON cs."uploadId" = mp."uploadId"
      WHERE mp."organizationId" = ${organizationId}
        AND (
          mp."conclusionId" IN (${Prisma.join(ids)})
          OR cs."conclusionId" IN (${Prisma.join(ids)})
        )
      ORDER BY mp.confidence DESC, mp."createdAt" DESC
      LIMIT 200
    `;
    for (const row of rows) {
      const targets = [row.conclusionId, row.sourceConclusionId].filter((id): id is string => Boolean(id));
      const profile = rowToProfile(row);
      if (!hasDisplayableProfile(profile)) continue;
      for (const id of targets) {
        if (!ids.includes(id)) continue;
        const list = out.get(id) ?? [];
        if (!list.some((profile) => profile.patternType === row.patternType)) {
          list.push(profile);
        }
        out.set(id, list.slice(0, 6));
      }
    }
  } catch (error) {
    console.error("[methodology] profile query failed (schema lag?):", error);
  }

  return out;
}

export async function profilesForUpload(
  organizationId: string,
  uploadId: string,
): Promise<PublicationMethodologyProfile[]> {
  try {
    const rows = await db.$queryRaw<MethodologyProfileRow[]>`
      SELECT
        id,
        "conclusionId",
        NULL AS "sourceConclusionId",
        "patternType",
        title,
        summary,
        "reasoningMoves",
        "transferTargets",
        assumptions,
        "failureModes",
        "evidenceAnchors",
        confidence
      FROM "MethodologyProfile"
      WHERE "organizationId" = ${organizationId}
        AND "uploadId" = ${uploadId}
      ORDER BY confidence DESC, "createdAt" DESC
      LIMIT 8
    `;
    return rows.map(rowToProfile).filter(hasDisplayableProfile);
  } catch (error) {
    console.error("[methodology] upload profile query failed (schema lag?):", error);
    return [];
  }
}
