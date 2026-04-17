import { db } from "@/lib/db";
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
  timeline: { at: string; label: string; detail?: string }[];
  whatWouldChangeOurMind: string[];
  citations: { format: "bibtex" | "apa" | "ris"; block: string }[];
  internalLinks?: { label: string; url: string }[];
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
      reviewer: { select: { id: true, name: true, username: true } },
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
        } catch {
          priorTimeline = [];
        }
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
    let payload: PublicationPayloadV1 | Record<string, unknown> = {};
    try {
      payload = JSON.parse(p.payloadJson) as PublicationPayloadV1;
    } catch {
      payload = {};
    }
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
