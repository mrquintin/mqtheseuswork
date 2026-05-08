import { createHash } from "node:crypto";

import { db } from "@/lib/db";
import {
  hasMethodologyContent,
  parseMethodologyPayload,
  profilesForConclusions,
  type PublicationMethodology,
  type PublicationMethodologyProfile,
} from "@/lib/methodologyProfiles";
import { parsePublicationPayload } from "@/lib/conclusionsRead";
import { publicationSlugFromText } from "@/lib/publicSlug";
import { mintZenodoDoi } from "@/lib/zenodoMint";

export type PublicationPayloadV1 = {
  schema: "theseus.publicConclusion.v1";
  conclusionText: string;
  rationale: string;
  topicHint: string;
  evidenceSummary: string;
  exitConditions: string[];
  strongestObjection: { objection: string; firmAnswer: string };
  openQuestionsAdjacent: string[];
  voiceComparisons: { voice: string; stance: string }[];
  methodology: PublicationMethodology;
  timeline: { at: string; label: string; detail?: string }[];
  whatWouldChangeOurMind: string[];
  citations: { format: "bibtex" | "apa" | "ris"; block: string }[];
  internalLinks?: { label: string; url: string }[];
  article?: {
    kind: string;
    bodyMarkdown: string;
    sourceIds: string[];
    sourceKey?: string;
    citations: {
      label: string;
      sourceKind: string;
      sourceId: string;
      quotedSpan: string;
      publicUrl: string | null;
      linkable: boolean;
    }[];
  };
};

const PUBLISH_CHECKLIST_KEYS = [
  "metaAnalysisOk",
  "adversarialEngagedOk",
  "clarityOk",
  "noLeakageOk",
  "noHarmOk",
] as const;

export type PublishChecklist = Partial<Record<(typeof PUBLISH_CHECKLIST_KEYS)[number], boolean>>;

function publicSiteBase(): string {
  const raw = process.env.THESEUS_PUBLIC_SITE_URL?.trim();
  if (raw) return raw.replace(/\/+$/, "");
  return "https://theseus.invalid";
}

function assertChecklistForPublish(c: PublishChecklist) {
  for (const k of PUBLISH_CHECKLIST_KEYS) {
    if (!c[k]) {
      throw new Error(`Checklist incomplete: ${k}`);
    }
  }
}

function escapeBibTitle(title: string): string {
  return title.replace(/[{}]/g, "").replace(/\\/g, "");
}

function buildCitations(input: { slug: string; version: number; doi: string; title: string; year: number }) {
  const url = `${publicSiteBase()}/c/${encodeURIComponent(input.slug)}/v/${input.version}`;
  const key = `${input.slug.replace(/[^a-z0-9]+/gi, "")}_v${input.version}`.slice(0, 80);
  const bib = `@misc{theseus_${key},
  title={${escapeBibTitle(input.title)}},
  author={{Theseus}},
  year={${input.year}},
  doi={${input.doi}},
  url={${url}}
}`.trim();
  const apa = `Theseus (${input.year}). ${input.title}. ${url} https://doi.org/${input.doi}`;
  const ris = `TY  - GEN\nAU  - Theseus\nTI  - ${input.title}\nDO  - ${input.doi}\nUR  - ${url}\nPY  - ${input.year}\nER  -\n`;
  return [
    { format: "bibtex" as const, block: bib },
    { format: "apa" as const, block: apa },
    { format: "ris" as const, block: ris },
  ];
}

export async function enqueuePublicationReview(params: {
  organizationId: string;
  conclusionId: string;
}): Promise<{ id: string }> {
  const c = await db.conclusion.findFirst({
    where: { id: params.conclusionId, organizationId: params.organizationId },
  });
  if (!c) {
    throw new Error("Conclusion not found");
  }
  if (c.confidenceTier !== "firm") {
    throw new Error("Only firm-tier conclusions may enter the publication queue");
  }

  const active = await db.publicationReview.findFirst({
    where: {
      organizationId: params.organizationId,
      conclusionId: params.conclusionId,
      status: { in: ["queued", "in_review", "needs_revision"] },
    },
  });
  if (active) {
    throw new Error("This conclusion already has an active publication review");
  }

  const row = await db.publicationReview.create({
    data: {
      organizationId: params.organizationId,
      conclusionId: params.conclusionId,
      status: "queued",
      checklistJson: "{}",
    },
  });
  return { id: row.id };
}

export async function listPublicationQueue(organizationId: string) {
  return db.publicationReview.findMany({
    where: { organizationId },
    orderBy: { updatedAt: "desc" },
    take: 200,
    include: {
      target: true,
      reviewer: {
        select: { id: true, displayName: true, name: true, username: true },
      },
    },
  });
}

export type PublicationReviewAction =
  | { action: "claim" }
  | { action: "release" }
  | { action: "checklist"; checklist: PublishChecklist; reviewerNotes?: string }
  | { action: "needs_revision"; revisionAsk: string; reviewerNotes?: string }
  | { action: "decline"; declineReason: string; reviewerNotes?: string }
  | {
      action: "publish";
      checklist: PublishChecklist;
      reviewerNotes?: string;
      evidenceSummary: string;
      exitConditions: string[];
      strongestObjection: { objection: string; firmAnswer: string };
      openQuestionsAdjacent: string[];
      voiceComparisons: { voice: string; stance: string }[];
      methodologyProfiles?: PublicationMethodologyProfile[];
      methodologyNarrative?: string;
      timeline?: { at: string; label: string; detail?: string }[];
      discountedConfidence: number;
      statedConfidence?: number;
      calibrationDiscountReason: string;
      slug?: string;
      zenodoTitle?: string;
    };

function isReviewer(review: { reviewerFounderId: string | null }, founderId: string, role: string) {
  if (role === "admin") return true;
  return review.reviewerFounderId === founderId;
}

export async function applyPublicationReviewAction(params: {
  organizationId: string;
  founderId: string;
  role: string;
  reviewId: string;
  body: PublicationReviewAction;
}): Promise<Record<string, unknown>> {
  const review = await db.publicationReview.findFirst({
    where: { id: params.reviewId, organizationId: params.organizationId },
    include: { target: true },
  });
  if (!review) {
    throw new Error("Review not found");
  }

  switch (params.body.action) {
    case "claim": {
      if (review.status !== "queued" && review.status !== "needs_revision") {
        throw new Error("Cannot claim review in this state");
      }
      await db.publicationReview.update({
        where: { id: review.id },
        data: { status: "in_review", reviewerFounderId: params.founderId },
      });
      return { ok: true };
    }
    case "release": {
      if (!isReviewer(review, params.founderId, params.role)) {
        throw new Error("Only the assigned reviewer (or admin) can release a claim");
      }
      await db.publicationReview.update({
        where: { id: review.id },
        data: { status: "queued", reviewerFounderId: null },
      });
      return { ok: true };
    }
    case "checklist": {
      if (review.status !== "in_review") {
        throw new Error("Checklist updates require in_review");
      }
      if (!isReviewer(review, params.founderId, params.role)) {
        throw new Error("Only the assigned reviewer can edit the checklist");
      }
      await db.publicationReview.update({
        where: { id: review.id },
        data: {
          checklistJson: JSON.stringify(params.body.checklist ?? {}),
          reviewerNotes: params.body.reviewerNotes ?? review.reviewerNotes,
        },
      });
      return { ok: true };
    }
    case "needs_revision": {
      if (!isReviewer(review, params.founderId, params.role)) {
        throw new Error("Only the assigned reviewer can request revision");
      }
      await db.publicationReview.update({
        where: { id: review.id },
        data: {
          status: "needs_revision",
          revisionAsk: params.body.revisionAsk,
          reviewerNotes: params.body.reviewerNotes ?? review.reviewerNotes,
        },
      });
      return { ok: true };
    }
    case "decline": {
      if (!isReviewer(review, params.founderId, params.role)) {
        throw new Error("Only the assigned reviewer can decline");
      }
      await db.publicationReview.update({
        where: { id: review.id },
        data: {
          status: "declined",
          declineReason: params.body.declineReason,
          reviewerNotes: params.body.reviewerNotes ?? review.reviewerNotes,
        },
      });
      return { ok: true };
    }
    case "publish": {
      if (!isReviewer(review, params.founderId, params.role)) {
        throw new Error("Only the assigned reviewer can publish");
      }
      if (review.status !== "in_review") {
        throw new Error("Publish requires in_review status");
      }
      assertChecklistForPublish(params.body.checklist);

      const exit = params.body.exitConditions.map((s) => s.trim()).filter(Boolean);
      if (exit.length === 0) {
        throw new Error("exitConditions required");
      }
      const objection = params.body.strongestObjection.objection.trim();
      const firmAnswer = params.body.strongestObjection.firmAnswer.trim();
      if (!objection || !firmAnswer) {
        throw new Error("strongestObjection.objection and .firmAnswer are required");
      }

      const dc = params.body.discountedConfidence;
      if (typeof dc !== "number" || Number.isNaN(dc) || dc < 0 || dc > 1) {
        throw new Error("discountedConfidence must be between 0 and 1");
      }

      const conclusion = review.target;
      const stated = params.body.statedConfidence ?? conclusion.confidence;
      let methodology: PublicationMethodology = parseMethodologyPayload({
        reviewerNarrative: params.body.methodologyNarrative,
        profiles: params.body.methodologyProfiles,
      });
      if (methodology.profiles.length === 0) {
        const profileMap = await profilesForConclusions(params.organizationId, [conclusion.id]);
        methodology = {
          ...methodology,
          profiles: profileMap.get(conclusion.id) ?? [],
        };
      }

      const prev = await db.publishedConclusion.findFirst({
        where: { organizationId: params.organizationId, sourceConclusionId: conclusion.id },
        orderBy: { version: "desc" },
      });
      const nextVersion = (prev?.version ?? 0) + 1;

      const baseSlug = (params.body.slug?.trim() || prev?.slug || publicationSlugFromText(conclusion.text)).slice(
        0,
        120,
      );

      let slug = baseSlug;
      if (!prev) {
        const clash = await db.publishedConclusion.findFirst({
          where: { slug, version: 1 },
        });
        if (clash && clash.sourceConclusionId !== conclusion.id) {
          slug = `${baseSlug}-${conclusion.id.slice(0, 6)}`.slice(0, 120);
        }
      } else {
        slug = prev.slug;
      }

      const publishedAt = new Date();

      let priorTimeline: { at: string; label: string; detail?: string }[] = [];
      if (prev) {
        try {
          const priorPayload = JSON.parse(prev.payloadJson) as PublicationPayloadV1;
          priorTimeline = priorPayload.timeline ?? [];
          if (!hasMethodologyContent(methodology)) {
            methodology = parseMethodologyPayload(priorPayload.methodology);
          }
        } catch {
          priorTimeline = [];
        }
      }
      if (!hasMethodologyContent(methodology)) {
        throw new Error("methodology profile or reviewer methodology narrative is required");
      }
      const timeline =
        params.body.timeline?.length ?
          params.body.timeline
        : [
            ...priorTimeline,
            {
              at: publishedAt.toISOString(),
              label: nextVersion === 1 ? "Initial publication" : `Revision v${nextVersion}`,
            },
          ];

      const whatWouldChangeOurMind = exit;

      const payload: PublicationPayloadV1 = {
        schema: "theseus.publicConclusion.v1",
        conclusionText: conclusion.text,
        rationale: conclusion.rationale,
        topicHint: conclusion.topicHint,
        evidenceSummary: params.body.evidenceSummary.trim(),
        exitConditions: exit,
        strongestObjection: { objection, firmAnswer },
        openQuestionsAdjacent: params.body.openQuestionsAdjacent.map((s) => s.trim()).filter(Boolean),
        voiceComparisons: params.body.voiceComparisons,
        methodology,
        timeline,
        whatWouldChangeOurMind,
        citations: [],
      };

      const draftTitle = (params.body.zenodoTitle ?? conclusion.text).slice(0, 240);
      const minted = await mintZenodoDoi({
        title: draftTitle,
        description: `${params.body.evidenceSummary.trim()}\n\n---\n\n${conclusion.text}`.slice(0, 48_000),
      });

      payload.citations = buildCitations({
        slug,
        version: nextVersion,
        doi: minted.doi,
        title: draftTitle,
        year: publishedAt.getUTCFullYear(),
      });

      const calibrationDiscountReason = params.body.calibrationDiscountReason.trim();
      const publishedChecklistJson = JSON.stringify(params.body.checklist);
      const publishedReviewerNotes = params.body.reviewerNotes ?? review.reviewerNotes;

      await db.$transaction(async (tx) => {
        await tx.publishedConclusion.create({
          data: {
            organizationId: params.organizationId,
            sourceConclusionId: conclusion.id,
            slug,
            version: nextVersion,
            discountedConfidence: dc,
            statedConfidence: stated,
            calibrationDiscountReason,
            payloadJson: JSON.stringify(payload),
            doi: minted.doi,
            zenodoRecordId: minted.recordId,
            publishedAt,
          },
        });
        await tx.publicationReview.update({
          where: { id: review.id },
          data: {
            status: "published",
            checklistJson: publishedChecklistJson,
            reviewerNotes: publishedReviewerNotes,
          },
        });
      });

      return { ok: true, slug, version: nextVersion, doi: minted.doi };
    }
    default:
      throw new Error("Unknown publication review action");
  }
}

export async function buildPublicExportBundle(organizationId: string) {
  const pubs = await db.publishedConclusion.findMany({
    where: { organizationId },
    orderBy: [{ slug: "asc" }, { version: "asc" }],
  });

  const openQuestions = await db.openQuestion.findMany({
    where: { organizationId },
    orderBy: { createdAt: "desc" },
    take: 500,
  });

  const responses = await db.publicResponse.findMany({
    where: { organizationId, status: { in: ["approved", "engaged"] } },
    orderBy: { createdAt: "desc" },
    take: 500,
  });

  const conclusions = pubs.map((p) => {
    const payload = parsePublicationPayload({ payloadJson: p.payloadJson, slug: p.slug });
    return {
      id: p.id,
      slug: p.slug,
      version: p.version,
      sourceConclusionId: p.sourceConclusionId,
      publishedAt: p.publishedAt.toISOString(),
      doi: p.doi,
      zenodoRecordId: p.zenodoRecordId,
      discountedConfidence: p.discountedConfidence,
      statedConfidence: p.statedConfidence,
      calibrationDiscountReason: p.calibrationDiscountReason,
      payload,
    };
  });

  return {
    schema: "theseus.publishedExport.v1" as const,
    generatedAt: new Date().toISOString(),
    conclusions,
    openQuestions: openQuestions.map((q) => ({
      id: q.id,
      summary: q.summary,
      unresolvedReason: q.unresolvedReason,
      layerDisagreementSummary: q.layerDisagreementSummary,
      createdAt: q.createdAt.toISOString(),
    })),
    responses: responses.map((r) => ({
      id: r.id,
      publishedConclusionId: r.publishedConclusionId,
      kind: r.kind,
      body: r.body,
      citationUrl: r.citationUrl,
      status: r.status,
      createdAt: r.createdAt.toISOString(),
      pseudonymous: r.pseudonymous,
    })),
  };
}

// ── Publication signing ────────────────────────────────────────────────
//
// The web app NEVER holds private signing keys. The noosphere CLI mints
// signatures (`noosphere ledger sign-publication <slug>`) and writes them
// into PublicationSignature. The web app:
//   1. serves signatures verbatim via /api/public/signature/[slug],
//   2. recomputes the canonical hash from the live row using the
//      canonicalizer below,
//   3. compares to PublicationSignature.canonicalHash to decide whether
//      to render a verified / unsigned / mismatch banner.
//
// The canonicalizer here MUST stay byte-for-byte equivalent to
// noosphere/noosphere/ledger/canonicalize.py — the verifier and signer
// hash the same bytes or nothing works.

export const PUBLICATION_SIGNATURE_SCHEMA = "theseus.publicationSignature.v1";

export type PublicationCanonicalCitation = {
  format: string;
  block: string;
};

export type PublicationCanonicalMqs = {
  aimMethodFit: number;
  composite: number;
  compressibility: number;
  domainSensitivity: number;
  progressivity: number;
  promptVersion: string;
  severity: number;
};

export type PublicationCanonicalInput = {
  citations: PublicationCanonicalCitation[];
  conclusionText: string;
  discountedConfidence: number;
  methodologyProfileIds: string[];
  mqs: PublicationCanonicalMqs | null;
  publishedAt: string;
  schema: typeof PUBLICATION_SIGNATURE_SCHEMA;
  slug: string;
  statedConfidence: number;
  version: number;
};

export type PublicationSignaturePayload = {
  schema: string;
  slug: string;
  version: number;
  canonicalInput: PublicationCanonicalInput;
  canonicalHash: string;
  signatureHex: string;
  keyFingerprint: string;
  signedAt: string;
};

export type PublicationSignatureStatus =
  | { state: "verified"; signature: PublicationSignaturePayload; expectedHash: string }
  | { state: "unsigned"; expectedHash: string }
  | {
      state: "mismatch";
      signature: PublicationSignaturePayload;
      expectedHash: string;
      signedHash: string;
    };

export function normalizeMarkdownForSignature(text: string | null | undefined): string {
  if (text == null) return "";
  let s = String(text).normalize("NFC");
  s = s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  s = s
    .split("\n")
    .map((line) => line.replace(/[ \t\f\v]+$/u, ""))
    .join("\n");
  s = s.replace(/\n{3,}/g, "\n\n");
  return s.trim();
}

function normalizeIsoTimestamp(ts: string | Date | null | undefined): string {
  if (ts == null) return "";
  const d = ts instanceof Date ? ts : new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts);
  // Match Python's: drop microseconds, render as Z UTC.
  const iso = new Date(Math.floor(d.getTime() / 1000) * 1000).toISOString();
  return iso.replace(/\.\d+Z$/, "Z");
}

function round6(n: unknown): number {
  const v = typeof n === "number" ? n : Number(n ?? 0);
  if (!Number.isFinite(v)) return 0;
  return Math.round(v * 1_000_000) / 1_000_000;
}

function normalizeCitations(
  raw: { format?: string; block?: string }[] | null | undefined,
): PublicationCanonicalCitation[] {
  if (!raw || raw.length === 0) return [];
  const out = raw.map((c) => ({
    format: String(c?.format ?? "").trim().toLowerCase(),
    block: normalizeMarkdownForSignature(c?.block ?? ""),
  }));
  out.sort((a, b) => {
    if (a.format !== b.format) return a.format < b.format ? -1 : 1;
    if (a.block !== b.block) return a.block < b.block ? -1 : 1;
    return 0;
  });
  return out;
}

function normalizeProfileIds(ids: (string | null | undefined)[] | null | undefined): string[] {
  if (!ids) return [];
  const cleaned = ids
    .map((s) => (s == null ? "" : String(s).trim()))
    .filter((s) => s.length > 0);
  return Array.from(new Set(cleaned)).sort();
}

function canonicalJsonStringify(obj: unknown): string {
  if (obj === null || typeof obj !== "object") return JSON.stringify(obj);
  if (Array.isArray(obj)) {
    return `[${obj.map((v) => canonicalJsonStringify(v)).join(",")}]`;
  }
  const keys = Object.keys(obj as Record<string, unknown>).sort();
  const body = keys
    .map((k) => `${JSON.stringify(k)}:${canonicalJsonStringify((obj as Record<string, unknown>)[k])}`)
    .join(",");
  return `{${body}}`;
}

export type CanonicalInputSource = {
  slug: string;
  version: number;
  publishedAt: Date | string;
  discountedConfidence: number;
  statedConfidence: number;
  payload: PublicationPayloadV1 | { conclusionText?: string; methodology?: PublicationMethodology; citations?: { format?: string; block?: string }[] };
  mqs?: {
    aimMethodFit?: number | null;
    composite?: number | null;
    compressibility?: number | null;
    domainSensitivity?: number | null;
    progressivity?: number | null;
    promptVersion?: string | null;
    severity?: number | null;
  } | null;
};

export function buildCanonicalInput(src: CanonicalInputSource): PublicationCanonicalInput {
  const profiles = (src.payload as PublicationPayloadV1)?.methodology?.profiles;
  const profileIds = normalizeProfileIds(
    Array.isArray(profiles) ? profiles.map((p) => (p as { id?: string }).id) : [],
  );
  const citations = normalizeCitations(
    Array.isArray((src.payload as { citations?: { format?: string; block?: string }[] }).citations)
      ? ((src.payload as { citations: { format?: string; block?: string }[] }).citations)
      : [],
  );
  const mqs = src.mqs
    ? {
        aimMethodFit: round6(src.mqs.aimMethodFit),
        composite: round6(src.mqs.composite),
        compressibility: round6(src.mqs.compressibility),
        domainSensitivity: round6(src.mqs.domainSensitivity),
        progressivity: round6(src.mqs.progressivity),
        promptVersion: String(src.mqs.promptVersion ?? ""),
        severity: round6(src.mqs.severity),
      }
    : null;

  return {
    citations,
    conclusionText: normalizeMarkdownForSignature(
      (src.payload as { conclusionText?: string }).conclusionText ?? "",
    ),
    discountedConfidence: round6(src.discountedConfidence),
    methodologyProfileIds: profileIds,
    mqs,
    publishedAt: normalizeIsoTimestamp(src.publishedAt),
    schema: PUBLICATION_SIGNATURE_SCHEMA,
    slug: String(src.slug),
    statedConfidence: round6(src.statedConfidence),
    version: Math.trunc(Number(src.version) || 0),
  };
}

export function canonicalHash(input: PublicationCanonicalInput): string {
  return createHash("sha256").update(canonicalJsonStringify(input), "utf8").digest("hex");
}

export async function evaluatePublicationSignatureStatus(
  publishedConclusionId: string,
  src: CanonicalInputSource,
): Promise<PublicationSignatureStatus> {
  const liveInput = buildCanonicalInput(src);
  const expectedHash = canonicalHash(liveInput);

  const sig = await db.publicationSignature.findUnique({
    where: { publishedConclusionId },
  });
  if (!sig) {
    return { state: "unsigned", expectedHash };
  }

  let payload: PublicationSignaturePayload | null = null;
  try {
    const parsed = JSON.parse(sig.payloadJson) as PublicationSignaturePayload;
    payload = parsed;
  } catch {
    payload = null;
  }
  const fallback: PublicationSignaturePayload = payload ?? {
    schema: PUBLICATION_SIGNATURE_SCHEMA,
    slug: sig.slug,
    version: sig.version,
    canonicalInput: liveInput,
    canonicalHash: sig.canonicalHash,
    signatureHex: sig.signatureHex,
    keyFingerprint: sig.keyFingerprint,
    signedAt: sig.signedAt,
  };

  if (sig.canonicalHash === expectedHash) {
    return { state: "verified", signature: fallback, expectedHash };
  }
  return {
    state: "mismatch",
    signature: fallback,
    expectedHash,
    signedHash: sig.canonicalHash,
  };
}

export async function activePublicationKeyFingerprint(): Promise<string | null> {
  const latest = await db.publicationSignature.findFirst({
    orderBy: { createdAt: "desc" },
    select: { keyFingerprint: true },
  });
  return latest?.keyFingerprint ?? null;
}
