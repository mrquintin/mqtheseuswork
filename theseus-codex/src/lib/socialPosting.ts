import { createHash } from "crypto";
import path from "path";
import { v4 as uuidv4 } from "uuid";
import type { Prisma } from "@prisma/client";

import { db } from "@/lib/db";
import { runNoospherePython } from "@/lib/pythonRuntime";

export const SOCIAL_KILL_KEY = "theseus.x_kill";
export const LEGACY_SOCIAL_KILL_KEY = "theseus.social_kill";
export const SUBSTACK_KILL_KEY = "theseus.substack_kill";
export const MAX_X_CHARS = 280;
export const TCO_URL_CHARS = 23;

type FounderRef = {
  id: string;
  organizationId: string;
  role?: string;
};

export type SocialPostForGate = {
  id: string;
  organizationId: string;
  platform: string;
  source?: string;
  sourceId?: string | null;
  subject?: string | null;
  body: string;
  markdownBody?: string | null;
  status: string;
  approvedBy: string | null;
};

export type SocialGateCode =
  | "NOT_CONFIGURED"
  | "DISABLED"
  | "DAILY_BUDGET_EXCEEDED"
  | "CONTENT_REJECTED"
  | "CITATION_REQUIRED"
  | "SOURCE_REJECTED"
  | "NOT_APPROVED";

export type SocialGateFailure = {
  code: SocialGateCode;
  detail: string;
};

export type SocialGateContext = {
  oauthRefreshConfigured: boolean;
  postingEnabled: boolean;
  killSwitchEngaged: boolean;
  postsLast24h: number;
  dailyMax: number;
  forbiddenPhrases: string[];
  firmPublicationHosts: string[];
};

export type SubstackGateContext = {
  identityConfigured: boolean;
  missingIdentity: string[];
  postingEnabled: boolean;
  killSwitchEngaged: boolean;
};

type XPostResult = {
  tweet_id: string;
  posted_at: string;
};

type SubstackPostResult = {
  external_id: string;
  sent_at: string;
};

type SocialPostDraftFields = {
  body?: string;
  subject?: string;
  markdownBody?: string;
};

export type PublishableArtifactType = "session" | "upload" | "currents-opinion";
export type PublishPlatform = "x" | "substack";

type DraftCreateResult = {
  ok: boolean;
  postId?: string;
  bundleId?: string;
  error?: string;
};

type SubstackFormatterResult = {
  subject: string;
  body: string;
  markdownBody: string;
};

type XFormatterResult = {
  body: string;
  source_url?: string;
};

type PublishableArtifact = {
  title: string;
  sourceText: string;
  xText: string;
  sourceKind: string;
  source: string;
  sourceId: string;
  sourceUrl: string;
};

const URL_RE = /https:\/\/[^\s<>()]+/gi;
const MANDATORY_BLOCKLIST = ["password", "apikey", "api_key", "bearer "];
const DEFAULT_FIRM_HOSTS = ["theseuscodex.com", "www.theseuscodex.com"];
const SUBSTACK_IDENTITY_ENV = [
  "SUBSTACK_SMTP_HOST",
  "SUBSTACK_SMTP_PORT",
  "SUBSTACK_SMTP_USER",
  "SUBSTACK_SMTP_PASS",
  "SUBSTACK_PUBLISH_EMAIL",
  "SUBSTACK_FROM_EMAIL",
];

export function weightedXLength(text: string): number {
  let total = 0;
  let cursor = 0;
  for (const match of text.matchAll(URL_RE)) {
    const index = match.index ?? 0;
    total += Array.from(text.slice(cursor, index)).length;
    total += TCO_URL_CHARS;
    cursor = index + match[0].length;
  }
  total += Array.from(text.slice(cursor)).length;
  return total;
}

export function evaluateSocialPostGates(
  post: SocialPostForGate,
  ctx: SocialGateContext,
): SocialGateFailure[] {
  const failures: SocialGateFailure[] = [];
  if (!ctx.oauthRefreshConfigured) {
    failures.push({
      code: "NOT_CONFIGURED",
      detail: "X OAuth refresh token is not configured.",
    });
  }
  if (!ctx.postingEnabled) {
    failures.push({
      code: "DISABLED",
      detail: "THESEUS_X_POSTING_ENABLED is not true.",
    });
  }
  if (ctx.killSwitchEngaged) {
    failures.push({
      code: "DISABLED",
      detail: `${SOCIAL_KILL_KEY} is engaged.`,
    });
  }
  if (ctx.postsLast24h >= ctx.dailyMax) {
    failures.push({
      code: "DAILY_BUDGET_EXCEEDED",
      detail: `${ctx.postsLast24h} posts already sent in the last 24 hours.`,
    });
  }

  const content = contentGateFailure(post.body, ctx.forbiddenPhrases);
  if (content) failures.push({ code: "CONTENT_REJECTED", detail: content });
  if (!citationGatePasses(post.body, ctx.firmPublicationHosts)) {
    failures.push({
      code: "CITATION_REQUIRED",
      detail: "Post body must include an https source link.",
    });
  }
  if (post.status !== "approved" || !post.approvedBy) {
    failures.push({
      code: "NOT_APPROVED",
      detail: "Post has not been approved by an operator.",
    });
  }
  return failures;
}

export function evaluateSubstackPostGates(
  post: SocialPostForGate,
  ctx: SubstackGateContext,
  sourceFailure: string | null,
): SocialGateFailure[] {
  const failures: SocialGateFailure[] = [];
  if (!ctx.identityConfigured) {
    failures.push({
      code: "NOT_CONFIGURED",
      detail: `Missing Substack env: ${ctx.missingIdentity.join(", ") || "required identity vars"}.`,
    });
  }
  if (!ctx.postingEnabled) {
    failures.push({
      code: "DISABLED",
      detail: "THESEUS_SUBSTACK_POSTING_ENABLED is not true.",
    });
  }
  if (ctx.killSwitchEngaged) {
    failures.push({
      code: "DISABLED",
      detail: `${SUBSTACK_KILL_KEY} is engaged.`,
    });
  }

  const content = substackContentGateFailure(post);
  if (content) failures.push({ code: "CONTENT_REJECTED", detail: content });
  if (sourceFailure) {
    failures.push({ code: "SOURCE_REJECTED", detail: sourceFailure });
  }
  if (post.status !== "approved" || !post.approvedBy) {
    failures.push({
      code: "NOT_APPROVED",
      detail: "Post has not been approved by a founder.",
    });
  }
  return failures;
}

export async function evaluateSubstackPostGatesForPost(
  post: SocialPostForGate,
  ctx?: SubstackGateContext,
): Promise<SocialGateFailure[]> {
  const gateCtx = ctx ?? (await substackGateContext(post.organizationId));
  const sourceFailure = await substackSourceGateFailure(post);
  return evaluateSubstackPostGates(post, gateCtx, sourceFailure);
}

export async function socialGateContext(
  organizationId: string,
): Promise<SocialGateContext> {
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const [killState, legacyKillState, postsLast24h] = await Promise.all([
    db.operatorState.findUnique({
      where: { organizationId_key: { organizationId, key: SOCIAL_KILL_KEY } },
      select: { value: true },
    }),
    db.operatorState.findUnique({
      where: { organizationId_key: { organizationId, key: LEGACY_SOCIAL_KILL_KEY } },
      select: { value: true },
    }),
    db.socialPost.count({
      where: {
        organizationId,
        platform: "x",
        status: "posted",
        postedAt: { gte: since },
      },
    }),
  ]);

  return {
    oauthRefreshConfigured: Boolean(process.env.X_BOT_OAUTH_REFRESH_TOKEN?.trim()),
    postingEnabled:
      process.env.THESEUS_X_POSTING_ENABLED?.trim().toLowerCase() === "true",
    killSwitchEngaged: operatorKillValue(killState?.value) || operatorKillValue(legacyKillState?.value),
    postsLast24h,
    dailyMax: envInt("X_POSTS_PER_DAY_MAX", 3),
    forbiddenPhrases: envCsv("X_FORBIDDEN_PHRASES"),
    firmPublicationHosts:
      envCsv("THESEUS_FIRM_PUBLICATION_HOSTS").length > 0
        ? envCsv("THESEUS_FIRM_PUBLICATION_HOSTS")
        : DEFAULT_FIRM_HOSTS,
  };
}

export async function substackGateContext(
  organizationId: string,
): Promise<SubstackGateContext> {
  const [killState] = await Promise.all([
    db.operatorState.findUnique({
      where: { organizationId_key: { organizationId, key: SUBSTACK_KILL_KEY } },
      select: { value: true },
    }),
  ]);
  const missingIdentity = SUBSTACK_IDENTITY_ENV.filter(
    (key) => !process.env[key]?.trim(),
  );
  return {
    identityConfigured: missingIdentity.length === 0,
    missingIdentity,
    postingEnabled:
      process.env.THESEUS_SUBSTACK_POSTING_ENABLED?.trim().toLowerCase() === "true",
    killSwitchEngaged: operatorKillValue(killState?.value),
  };
}

export async function saveSocialPostDraft(
  postId: string,
  bodyOrFields: string | SocialPostDraftFields,
  founder: FounderRef,
) {
  const post = await getOrgScopedPost(postId, founder.organizationId);
  if (!post) return { ok: false, error: "social_post_not_found" };
  if (post.status === "posted") return { ok: false, error: "posted_posts_are_immutable" };

  const fields =
    typeof bodyOrFields === "string" ? { body: bodyOrFields } : bodyOrFields;
  const body = fields.body ?? post.body;

  if (post.platform === "x") {
    const ctx = await socialGateContext(founder.organizationId);
    const content = contentGateFailure(body, ctx.forbiddenPhrases);
    if (content) return { ok: false, error: content };
    if (!citationGatePasses(body, ctx.firmPublicationHosts)) {
      return { ok: false, error: "Post body must include an https source link." };
    }
  }

  await db.socialPost.update({
    where: { id: post.id },
    data: {
      body,
      subject: fields.subject ?? post.subject,
      markdownBody: fields.markdownBody ?? post.markdownBody,
      status: "draft",
      approvedBy: null,
      approvedAt: null,
      failureReason: null,
    },
  });
  return { ok: true };
}

export async function rejectSocialPost(postId: string, founder: FounderRef) {
  const post = await getOrgScopedPost(postId, founder.organizationId);
  if (!post) return { ok: false, error: "social_post_not_found" };
  if (post.status === "posted") return { ok: false, error: "posted_posts_are_immutable" };
  await db.socialPost.update({
    where: { id: post.id },
    data: {
      status: "rejected",
      failureReason: `Rejected by operator ${founder.id}`,
    },
  });
  return { ok: true };
}

export async function approveAndPostSocialPost(
  postId: string,
  founder: FounderRef,
  fieldsOrBody?: string | SocialPostDraftFields,
) {
  const existing = await getOrgScopedPost(postId, founder.organizationId);
  if (!existing) return { ok: false, error: "social_post_not_found" };
  if (existing.status === "posted") return { ok: false, error: "already_posted" };
  const fields =
    typeof fieldsOrBody === "string"
      ? { body: fieldsOrBody }
      : fieldsOrBody ?? {};

  const approved = await db.socialPost.update({
    where: { id: existing.id },
    data: {
      body: fields.body ?? existing.body,
      subject: fields.subject ?? existing.subject,
      markdownBody: fields.markdownBody ?? existing.markdownBody,
      status: "approved",
      approvedBy: founder.id,
      approvedAt: new Date(),
      failureReason: null,
    },
  });

  if (approved.platform === "substack") {
    const ctx = await substackGateContext(founder.organizationId);
    const sourceFailure = await substackSourceGateFailure(approved);
    const failures = evaluateSubstackPostGates(approved, ctx, sourceFailure);
    if (failures.length > 0) {
      const reason = failures.map((failure) => `${failure.code}: ${failure.detail}`).join(" ");
      await db.socialPost.update({
        where: { id: approved.id },
        data: { status: "failed", failureReason: reason },
      });
      return { ok: false, error: reason, failures };
    }

    try {
      const result = await postToSubstack({
        subject: approved.subject || approved.body,
        markdownBody: approved.markdownBody || "",
      });
      await db.socialPost.update({
        where: { id: approved.id },
        data: {
          status: "posted",
          externalId: result.external_id,
          postedAt: new Date(result.sent_at),
          failureReason: null,
        },
      });
      return { ok: true, externalId: result.external_id };
    } catch (error) {
      const reason = error instanceof Error ? error.message : "Substack post failed";
      await db.socialPost.update({
        where: { id: approved.id },
        data: { status: "failed", failureReason: reason },
      });
      return { ok: false, error: reason };
    }
  }

  const ctx = await socialGateContext(founder.organizationId);
  const failures = evaluateSocialPostGates(approved, ctx);
  if (failures.length > 0) {
    const reason = failures.map((failure) => `${failure.code}: ${failure.detail}`).join(" ");
    await db.socialPost.update({
      where: { id: approved.id },
      data: { status: "failed", failureReason: reason },
    });
    return { ok: false, error: reason, failures };
  }

  try {
    const result = await postToX(approved.body);
    await db.socialPost.update({
      where: { id: approved.id },
      data: {
        status: "posted",
        externalId: result.tweet_id,
        postedAt: new Date(result.posted_at),
        failureReason: null,
      },
    });
    return { ok: true, tweetId: result.tweet_id };
  } catch (error) {
    const reason = error instanceof Error ? error.message : "X post failed";
    await db.socialPost.update({
      where: { id: approved.id },
      data: { status: "failed", failureReason: reason },
    });
    return { ok: false, error: reason };
  }
}

export async function engageSocialKill(founder: FounderRef) {
  const value = {
    disabled: true,
    by: founder.id,
    at: new Date().toISOString(),
  };
  await db.operatorState.upsert({
    where: {
      organizationId_key: {
        organizationId: founder.organizationId,
        key: SOCIAL_KILL_KEY,
      },
    },
    create: {
      organizationId: founder.organizationId,
      key: SOCIAL_KILL_KEY,
      value,
    },
    update: { value },
  });
  return { ok: true };
}

export async function engageSubstackKill(founder: FounderRef) {
  const value = {
    disabled: true,
    by: founder.id,
    at: new Date().toISOString(),
  };
  await db.operatorState.upsert({
    where: {
      organizationId_key: {
        organizationId: founder.organizationId,
        key: SUBSTACK_KILL_KEY,
      },
    },
    create: {
      organizationId: founder.organizationId,
      key: SUBSTACK_KILL_KEY,
      value,
    },
    update: { value },
  });
  return { ok: true };
}

export async function engageAllOutboundKill(founder: FounderRef) {
  await Promise.all([engageSocialKill(founder), engageSubstackKill(founder)]);
  return { ok: true };
}

export async function createSubstackDraftFromUpload(
  uploadId: string,
  founder: FounderRef,
  source: "session" | "upload.essay" = "upload.essay",
) {
  return createSocialDraftFromArtifact(
    source === "session" ? "session" : "upload",
    uploadId,
    "substack",
    founder,
  );
}

export async function createXDraftFromUpload(
  uploadId: string,
  founder: FounderRef,
  source: "session" | "upload.essay" = "upload.essay",
) {
  return createSocialDraftFromArtifact(
    source === "session" ? "session" : "upload",
    uploadId,
    "x",
    founder,
  );
}

export async function createSocialDraftFromArtifact(
  artifactType: PublishableArtifactType,
  artifactId: string,
  platform: PublishPlatform,
  founder: FounderRef,
  bundleId?: string,
): Promise<DraftCreateResult> {
  const artifact = await getPublishableArtifact(artifactType, artifactId, founder);
  if (!artifact) return { ok: false, error: "artifact_not_found" };
  if (!artifact.sourceText.trim()) return { ok: false, error: "artifact_has_no_text" };

  const data =
    platform === "substack"
      ? await buildSubstackDraftData(artifact, founder, bundleId)
      : await buildXDraftData(artifact, founder, bundleId);
  const created = await db.socialPost.create({
    data,
    select: { id: true },
  });
  return { ok: true, postId: created.id, bundleId };
}

export async function createBundledSocialDraftsFromArtifact(
  artifactType: PublishableArtifactType,
  artifactId: string,
  founder: FounderRef,
) {
  const bundleId = uuidv4();
  const artifact = await getPublishableArtifact(artifactType, artifactId, founder);
  if (!artifact) return { ok: false, bundleId, error: "artifact_not_found", postIds: [] };
  if (!artifact.sourceText.trim()) return { ok: false, bundleId, error: "artifact_has_no_text", postIds: [] };

  try {
    const [xData, substackData] = await Promise.all([
      buildXDraftData(artifact, founder, bundleId),
      buildSubstackDraftData(artifact, founder, bundleId),
    ]);
    const created = await db.$transaction([
      db.socialPost.create({ data: xData, select: { id: true } }),
      db.socialPost.create({ data: substackData, select: { id: true } }),
    ]);

    return {
      ok: true,
      bundleId,
      postIds: created.map((post) => post.id),
    };
  } catch (error) {
    return {
      ok: false,
      bundleId,
      error: error instanceof Error ? error.message : "bundle_draft_failed",
      postIds: [],
    };
  }
}

export async function bulkApproveDraftSocialPosts(postIds: string[], founder: FounderRef) {
  const uniqueIds = uniquePostIds(postIds);
  const results: Array<{ postId: string; ok: boolean; error?: string }> = [];

  for (const postId of uniqueIds) {
    const post = await getOrgScopedPost(postId, founder.organizationId);
    if (!post) {
      results.push({ postId, ok: false, error: "social_post_not_found" });
      continue;
    }
    if (post.status !== "draft") {
      results.push({ postId, ok: false, error: "bulk_actions_apply_to_drafts_only" });
      continue;
    }
    const result = await approveAndPostSocialPost(post.id, founder);
    results.push({
      postId,
      ok: result.ok,
      error: result.ok ? undefined : result.error || "approval_failed",
    });
  }

  return {
    ok: results.every((result) => result.ok),
    results,
  };
}

export async function bulkRejectDraftSocialPosts(postIds: string[], founder: FounderRef) {
  const uniqueIds = uniquePostIds(postIds);
  const results: Array<{ postId: string; ok: boolean; error?: string }> = [];

  for (const postId of uniqueIds) {
    const post = await getOrgScopedPost(postId, founder.organizationId);
    if (!post) {
      results.push({ postId, ok: false, error: "social_post_not_found" });
      continue;
    }
    if (post.status !== "draft") {
      results.push({ postId, ok: false, error: "bulk_actions_apply_to_drafts_only" });
      continue;
    }
    const result = await rejectSocialPost(post.id, founder);
    results.push({
      postId,
      ok: result.ok,
      error: result.ok ? undefined : result.error || "reject_failed",
    });
  }

  return {
    ok: results.every((result) => result.ok),
    results,
  };
}

function contentGateFailure(body: string, forbiddenPhrases: string[]): string | null {
  if (weightedXLength(body) > MAX_X_CHARS) {
    return `Weighted X length exceeds ${MAX_X_CHARS}.`;
  }
  const lowered = body.toLowerCase();
  for (const token of [...MANDATORY_BLOCKLIST, ...forbiddenPhrases]) {
    const normalized = token.trim().toLowerCase();
    if (normalized && lowered.includes(normalized)) {
      return "Post body contains a forbidden token.";
    }
  }
  return null;
}

function substackContentGateFailure(post: SocialPostForGate): string | null {
  const markdownBody = post.markdownBody || "";
  const subject = post.subject || "";
  const body = post.body || "";
  if (markdownBody.length < 400) return "markdownBody must be at least 400 characters.";
  if (subject.length < 5 || subject.length > 100) {
    return "subject must be 5-100 characters.";
  }
  if (body.length > 240) return "body subtitle must be 240 characters or fewer.";
  return null;
}

async function substackSourceGateFailure(post: SocialPostForGate): Promise<string | null> {
  const source = (post.source || "").trim().toLowerCase();
  if (source === "manual") {
    return post.approvedBy ? null : "manual posts require an approving founder.";
  }
  if (source === "currents.opinion" || source === "currents-opinion") {
    if (!post.sourceId) return "sourceId is required for source-backed Substack posts.";
    const opinion = await db.eventOpinion.findFirst({
      where: {
        id: post.sourceId,
        organizationId: post.organizationId,
        revokedAt: null,
      },
      select: { id: true },
    });
    return opinion ? null : "source opinion was not found.";
  }
  if (["session", "upload", "upload.essay", "upload.transcript"].includes(source)) {
    if (!post.sourceId) return "sourceId is required for source-backed Substack posts.";
    const upload = await db.upload.findFirst({
      where: {
        id: post.sourceId,
        organizationId: post.organizationId,
        deletedAt: null,
      },
      select: {
        founder: { select: { id: true, role: true } },
      },
    });
    if (!upload?.founder?.id) return "source upload was not found.";
    if (upload.founder.role === "admin" || upload.founder.role === "founder") {
      return null;
    }
    return "source upload is not owned by a write-capable founder.";
  }
  return "unsupported source for Substack publishing.";
}

function citationGatePasses(body: string, firmHosts: string[]): boolean {
  for (const match of body.matchAll(URL_RE)) {
    try {
      const host = new URL(match[0]).hostname.toLowerCase();
      if (["x.com", "twitter.com", "www.x.com", "www.twitter.com"].includes(host)) {
        return true;
      }
      if (firmHosts.includes(host)) return true;
    } catch {
      continue;
    }
  }
  return false;
}

function operatorKillValue(value: unknown): boolean {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Boolean((value as { disabled?: unknown }).disabled);
  }
  if (typeof value === "string") return ["1", "true", "disabled", "on"].includes(value.toLowerCase());
  return Boolean(value);
}

async function getOrgScopedPost(postId: string, organizationId: string) {
  return db.socialPost.findFirst({
    where: { id: postId, organizationId },
  });
}

async function getUploadForSocialDraft(uploadId: string, founder: FounderRef) {
  return db.upload.findFirst({
    where: {
      id: uploadId,
      organizationId: founder.organizationId,
      deletedAt: null,
      OR: [{ visibility: { not: "private" } }, { founderId: founder.id }],
    },
    select: {
      id: true,
      title: true,
      textContent: true,
      sourceType: true,
      mimeType: true,
      slug: true,
      founder: { select: { id: true, role: true } },
    },
  });
}

async function getPublishableArtifact(
  artifactType: PublishableArtifactType,
  artifactId: string,
  founder: FounderRef,
): Promise<PublishableArtifact | null> {
  if (artifactType === "session" || artifactType === "upload") {
    const upload = await getUploadForSocialDraft(artifactId, founder);
    if (!upload) return null;
    const isSession = artifactType === "session";
    const sourceUrl = upload.slug
      ? `${publicBaseUrl()}/post/${upload.slug}`
      : `${publicBaseUrl()}/${isSession ? "sessions" : "upload"}/${upload.id}`;
    const lead = isSession ? "Session note" : "Essay note";
    return {
      title: upload.title,
      sourceText: upload.textContent || "",
      xText: `${lead}: ${upload.title}`,
      sourceKind: isSession ? "session" : "essay",
      source: isSession ? "session" : "upload.essay",
      sourceId: upload.id,
      sourceUrl,
    };
  }

  const opinion = await db.eventOpinion.findFirst({
    where: {
      id: artifactId,
      organizationId: founder.organizationId,
      revokedAt: null,
    },
    select: {
      id: true,
      headline: true,
      bodyMarkdown: true,
      uncertaintyNotes: true,
      topicHint: true,
      event: {
        select: {
          text: true,
          url: true,
          topicHint: true,
        },
      },
    },
  });
  if (!opinion) return null;

  const notes = opinion.uncertaintyNotes.length
    ? `\n\nUncertainty notes:\n${opinion.uncertaintyNotes.map((note) => `- ${note}`).join("\n")}`
    : "";
  const eventText = opinion.event?.text
    ? `\n\nObserved event:\n${opinion.event.text}`
    : "";

  return {
    title: opinion.headline,
    sourceText: `${opinion.bodyMarkdown}${notes}${eventText}`.trim(),
    xText: opinion.headline,
    sourceKind: "currents-opinion",
    source: "currents.opinion",
    sourceId: opinion.id,
    sourceUrl: `${publicBaseUrl()}/currents/${opinion.id}`,
  };
}

async function buildSubstackDraftData(
  artifact: PublishableArtifact,
  founder: FounderRef,
  bundleId?: string,
): Promise<Prisma.SocialPostUncheckedCreateInput> {
  const formatted = await formatUploadForSubstack({
    title: artifact.title,
    sourceText: artifact.sourceText,
    sourceKind: artifact.sourceKind,
  });
  return {
    organizationId: founder.organizationId,
    source: artifact.source,
    sourceId: artifact.sourceId,
    platform: "substack",
    bundleId,
    subject: formatted.subject,
    body: formatted.body,
    markdownBody: formatted.markdownBody,
    media: [],
    status: "draft",
  };
}

async function buildXDraftData(
  artifact: PublishableArtifact,
  founder: FounderRef,
  bundleId?: string,
): Promise<Prisma.SocialPostUncheckedCreateInput> {
  const formatted = await formatArtifactForX({
    text: artifact.xText,
    sourceUrl: artifact.sourceUrl,
  });
  if (!formatted?.body) throw new Error("x_formatter_failed");
  return {
    organizationId: founder.organizationId,
    source: artifact.source,
    sourceId: artifact.sourceId,
    platform: "x",
    bundleId,
    body: formatted.body,
    media: [],
    status: "draft",
  };
}

async function formatArtifactForX({
  text,
  sourceUrl,
}: {
  text: string;
  sourceUrl: string;
}): Promise<XFormatterResult | null> {
  const noosphereRoot = noosphereRootPath();
  const result = await runNoospherePython(
    ["-m", "noosphere.social.x_formatter", "--format-json-stdin"],
    {
      cwd: noosphereRoot,
      envExtra: { PYTHONPATH: noosphereRoot },
      stdin: JSON.stringify({
        opinion: { body_markdown: text },
        source_url: sourceUrl,
      }),
    },
  );
  if (result.skipped) throw new Error(result.out.trim());
  if (result.code !== 0) throw new Error(result.out.trim() || "X formatter failed");
  const parsed = JSON.parse(result.out) as XFormatterResult | null;
  if (!parsed?.body) return null;
  return parsed;
}

async function postToX(body: string): Promise<XPostResult> {
  if (process.env.THESEUS_X_CLIENT_MOCK === "1") {
    return {
      tweet_id: `mock-${createHash("sha256").update(body).digest("hex").slice(0, 12)}`,
      posted_at: new Date().toISOString(),
    };
  }

  const noosphereRoot =
    process.env.NOOSPHERE_ROOT ||
    path.resolve(process.cwd(), "..", "noosphere");
  const result = await runNoospherePython(
    ["-m", "noosphere.social.x_live_client", "--post-json-stdin"],
    {
      cwd: noosphereRoot,
      envExtra: { PYTHONPATH: noosphereRoot },
      stdin: JSON.stringify({ body }),
    },
  );
  if (result.skipped) throw new Error(result.out.trim());
  if (result.code !== 0) throw new Error(result.out.trim() || "X client failed");
  const parsed = JSON.parse(result.out) as XPostResult;
  if (!parsed.tweet_id || !parsed.posted_at) {
    throw new Error("X client returned an invalid response");
  }
  return parsed;
}

async function formatUploadForSubstack({
  title,
  sourceText,
  sourceKind,
}: {
  title: string;
  sourceText: string;
  sourceKind: string;
}): Promise<SubstackFormatterResult> {
  const noosphereRoot = noosphereRootPath();
  const result = await runNoospherePython(
    ["-m", "noosphere.social.substack_formatter", "--format-json-stdin"],
    {
      cwd: noosphereRoot,
      envExtra: { PYTHONPATH: noosphereRoot },
      stdin: JSON.stringify({
        title,
        source_text: sourceText,
        source_kind: sourceKind,
      }),
    },
  );
  if (result.skipped) throw new Error(result.out.trim());
  if (result.code !== 0) throw new Error(result.out.trim() || "Substack formatter failed");
  const parsed = JSON.parse(result.out) as SubstackFormatterResult;
  if (!parsed.subject || !parsed.body || !parsed.markdownBody) {
    throw new Error("Substack formatter returned an invalid payload");
  }
  return parsed;
}

async function postToSubstack({
  subject,
  markdownBody,
}: {
  subject: string;
  markdownBody: string;
}): Promise<SubstackPostResult> {
  if (process.env.THESEUS_SUBSTACK_CLIENT_MOCK === "1") {
    return {
      external_id: `mock-substack-${createHash("sha256").update(subject + markdownBody).digest("hex").slice(0, 12)}`,
      sent_at: new Date().toISOString(),
    };
  }

  const noosphereRoot = noosphereRootPath();
  const args = ["-m", "noosphere.social.substack_live_client", "--post-json-stdin"];
  const dryRun = process.env.THESEUS_SUBSTACK_DRY_RUN === "1";
  if (dryRun) args.push("--dry-run");
  const result = await runNoospherePython(args, {
    cwd: noosphereRoot,
    envExtra: { PYTHONPATH: noosphereRoot },
    stdin: JSON.stringify({ subject, markdownBody }),
  });
  if (result.skipped) throw new Error(result.out.trim());
  if (result.code !== 0) throw new Error(result.out.trim() || "Substack client failed");
  if (dryRun) {
    return {
      external_id: "substack-email-dry-run",
      sent_at: new Date().toISOString(),
    };
  }
  const parsed = JSON.parse(result.out) as Partial<SubstackPostResult>;
  if (!parsed.external_id || !parsed.sent_at) {
    throw new Error("Substack client returned an invalid response");
  }
  return {
    external_id: parsed.external_id,
    sent_at: parsed.sent_at,
  };
}

function noosphereRootPath(): string {
  return process.env.NOOSPHERE_ROOT || path.resolve(process.cwd(), "..", "noosphere");
}

function publicBaseUrl(): string {
  return (process.env.THESEUS_PUBLIC_BASE_URL || "https://theseuscodex.com").replace(/\/+$/, "");
}

function clampXDraft(body: string): string {
  if (weightedXLength(body) <= MAX_X_CHARS) return body;
  const match = body.match(URL_RE);
  const url = match?.[0] || "";
  const budget = MAX_X_CHARS - (url ? TCO_URL_CHARS + 1 : 0);
  const prefix = body.replace(URL_RE, "").trim();
  return `${prefix.slice(0, Math.max(0, budget - 1)).trimEnd()} ${url}`.trim();
}

function uniquePostIds(postIds: string[]): string[] {
  return Array.from(
    new Set(
      postIds
        .map((postId) => postId.trim())
        .filter(Boolean),
    ),
  );
}

function envCsv(key: string): string[] {
  return (process.env[key] || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function envInt(key: string, fallback: number): number {
  const value = Number(process.env[key]);
  return Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : fallback;
}
