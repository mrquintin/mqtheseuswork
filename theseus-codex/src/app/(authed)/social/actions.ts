"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { getFounder } from "@/lib/auth";
import { canWrite } from "@/lib/roles";
import {
  approveAndPostSocialPost,
  bulkApproveDraftSocialPosts,
  bulkRejectDraftSocialPosts,
  createBundledSocialDraftsFromArtifact,
  createSocialDraftFromArtifact,
  engageAllOutboundKill,
  engageSubstackKill,
  engageSocialKill,
  type PublishableArtifactType,
  type PublishPlatform,
  rejectSocialPost,
  saveSocialPostDraft,
} from "@/lib/socialPosting";

async function requireFounder() {
  const founder = await getFounder();
  if (!founder) redirect("/login");
  if (!canWrite(founder.role)) redirect("/dashboard");
  return founder;
}

export async function saveDraftAction(formData: FormData) {
  const founder = await requireFounder();
  const postId = String(formData.get("postId") || "");
  const body = String(formData.get("body") || "");
  const subject = String(formData.get("subject") || "");
  const markdownBody = String(formData.get("markdownBody") || "");
  await saveSocialPostDraft(
    postId,
    {
      body,
      ...(subject ? { subject } : {}),
      ...(markdownBody ? { markdownBody } : {}),
    },
    founder,
  );
  revalidatePath("/social");
  revalidatePath(`/social/${postId}`);
}

export async function approveAndPostAction(formData: FormData) {
  const founder = await requireFounder();
  const postId = String(formData.get("postId") || "");
  const body = String(formData.get("body") || "");
  const subject = String(formData.get("subject") || "");
  const markdownBody = String(formData.get("markdownBody") || "");
  await approveAndPostSocialPost(
    postId,
    founder,
    {
      ...(body ? { body } : {}),
      ...(subject ? { subject } : {}),
      ...(markdownBody ? { markdownBody } : {}),
    },
  );
  revalidatePath("/social");
  revalidatePath(`/social/${postId}`);
}

export async function rejectPostAction(formData: FormData) {
  const founder = await requireFounder();
  const postId = String(formData.get("postId") || "");
  await rejectSocialPost(postId, founder);
  revalidatePath("/social");
  revalidatePath(`/social/${postId}`);
}

export async function killOutboundAction() {
  const founder = await requireFounder();
  await engageAllOutboundKill(founder);
  revalidatePath("/social");
}

export async function killXOutboundAction() {
  const founder = await requireFounder();
  await engageSocialKill(founder);
  revalidatePath("/social");
}

export async function killSubstackOutboundAction() {
  const founder = await requireFounder();
  await engageSubstackKill(founder);
  revalidatePath("/social");
}

export async function createSubstackDraftFromArtifactAction(formData: FormData) {
  return createDraftFromArtifactAction(formData, "substack");
}

export async function createXDraftFromArtifactAction(formData: FormData) {
  return createDraftFromArtifactAction(formData, "x");
}

export async function createBothDraftsFromArtifactAction(formData: FormData) {
  const founder = await requireFounder();
  const artifactId = artifactIdFromForm(formData);
  const artifactType = artifactTypeFromForm(formData);
  const returnPath = safeReturnPath(String(formData.get("returnPath") || ""));
  const result = await createBundledSocialDraftsFromArtifact(artifactType, artifactId, founder).catch((error) => ({
    ok: false,
    error: error instanceof Error ? error.message : "bundle_draft_failed",
    bundleId: undefined,
    postIds: [],
  }));
  if (!result.ok || !result.bundleId) {
    redirect(`${returnPath}?error=${encodeURIComponent(result.error || "bundle_draft_failed")}`);
  }
  revalidatePath("/social");
  redirect(`/social?bundle=${encodeURIComponent(result.bundleId)}`);
}

export async function bulkApproveSelectedAction(formData: FormData) {
  const founder = await requireFounder();
  const postIds = formData.getAll("postId").map(String);
  await bulkApproveDraftSocialPosts(postIds, founder);
  revalidatePath("/social");
}

export async function bulkRejectSelectedAction(formData: FormData) {
  const founder = await requireFounder();
  const postIds = formData.getAll("postId").map(String);
  await bulkRejectDraftSocialPosts(postIds, founder);
  revalidatePath("/social");
}

async function createDraftFromArtifactAction(
  formData: FormData,
  platform: PublishPlatform,
) {
  const founder = await requireFounder();
  const artifactId = artifactIdFromForm(formData);
  const artifactType = artifactTypeFromForm(formData);
  const returnPath = safeReturnPath(String(formData.get("returnPath") || ""));
  const result = await createSocialDraftFromArtifact(artifactType, artifactId, platform, founder).catch((error) => ({
    ok: false,
    error: error instanceof Error ? error.message : `${platform}_draft_failed`,
    postId: undefined,
  }));
  if (!result.ok || !result.postId) {
    redirect(`${returnPath}?error=${encodeURIComponent(result.error || `${platform}_draft_failed`)}`);
  }
  revalidatePath("/social");
  redirect(`/social/${result.postId}`);
}

function artifactIdFromForm(formData: FormData): string {
  return String(formData.get("artifactId") || formData.get("uploadId") || "");
}

function artifactTypeFromForm(formData: FormData): PublishableArtifactType {
  const explicit = String(formData.get("artifactType") || "");
  if (explicit === "session" || explicit === "upload" || explicit === "currents-opinion") {
    return explicit;
  }
  return String(formData.get("source") || "") === "session" ? "session" : "upload";
}

function safeReturnPath(path: string): string {
  if (path.startsWith("/") && !path.startsWith("//")) return path;
  return "/dashboard";
}
