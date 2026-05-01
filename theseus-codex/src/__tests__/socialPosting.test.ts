import { beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  operatorState: {
    findUnique: vi.fn(),
    upsert: vi.fn(),
  },
  socialPost: {
    count: vi.fn(),
    create: vi.fn(),
    findFirst: vi.fn(),
    update: vi.fn(),
  },
  upload: {
    findFirst: vi.fn(),
  },
}));

const pythonMock = vi.hoisted(() => ({
  runNoospherePython: vi.fn(),
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));
vi.mock("@/lib/pythonRuntime", () => pythonMock);

import {
  approveAndPostSocialPost,
  bulkApproveDraftSocialPosts,
  createSubstackDraftFromUpload,
  evaluateSocialPostGates,
  evaluateSubstackPostGates,
  substackGateContext,
  weightedXLength,
} from "@/lib/socialPosting";

const BODY = "Theseus complicates the premise. https://x.com/source/status/1";

describe("social posting gates and actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.X_BOT_OAUTH_REFRESH_TOKEN = "fixture-refresh";
    process.env.THESEUS_X_POSTING_ENABLED = "true";
    process.env.X_POSTS_PER_DAY_MAX = "3";
    delete process.env.THESEUS_X_CLIENT_MOCK;
    delete process.env.THESEUS_SUBSTACK_CLIENT_MOCK;
    process.env.SUBSTACK_SMTP_HOST = "smtp.example.test";
    process.env.SUBSTACK_SMTP_PORT = "587";
    process.env.SUBSTACK_SMTP_USER = "smtp-user";
    process.env.SUBSTACK_SMTP_PASS = "smtp-pass";
    process.env.SUBSTACK_PUBLISH_EMAIL = "post@substack.example";
    process.env.SUBSTACK_FROM_EMAIL = "founder@example.com";
    process.env.THESEUS_SUBSTACK_POSTING_ENABLED = "true";
    dbMock.operatorState.findUnique.mockResolvedValue(null);
    dbMock.socialPost.count.mockResolvedValue(0);
    dbMock.socialPost.findFirst.mockResolvedValue({
      id: "post-1",
      organizationId: "org-1",
      source: "currents.opinion",
      sourceId: "opinion-1",
      platform: "x",
      body: BODY,
      subject: null,
      markdownBody: null,
      status: "draft",
      approvedBy: null,
    });
    dbMock.socialPost.create.mockResolvedValue({ id: "post-substack" });
    dbMock.socialPost.update.mockImplementation(async ({ data }: { data: Record<string, unknown> }) => ({
      id: "post-1",
      organizationId: "org-1",
      source: "currents.opinion",
      sourceId: "opinion-1",
      platform: String(data.platform || "x"),
      body: String(data.body || BODY),
      subject: (data.subject as string | null) ?? null,
      markdownBody: (data.markdownBody as string | null) ?? null,
      status: String(data.status || "draft"),
      approvedBy: (data.approvedBy as string | null) ?? "founder-1",
    }));
    dbMock.upload.findFirst.mockResolvedValue({
      id: "upload-1",
      title: "Recorded reasoning",
      textContent: "Session transcript " + "body ".repeat(120),
      sourceType: "transcript",
      mimeType: "text/plain",
      slug: null,
      founder: { id: "founder-1", role: "founder" },
    });
    pythonMock.runNoospherePython.mockResolvedValue({
      code: 0,
      out: JSON.stringify({ tweet_id: "tweet-1", posted_at: "2026-05-01T12:00:00.000Z" }),
      skipped: false,
      reason: "ok",
    });
  });

  it("accounts for URL t.co length budget", () => {
    const longUrl = `https://x.com/source/status/${"9".repeat(80)}`;
    expect(weightedXLength(`ok ${longUrl}`)).toBe(26);
  });

  it("human gate fails before approval and passes after approval", () => {
    const ctx = {
      oauthRefreshConfigured: true,
      postingEnabled: true,
      killSwitchEngaged: false,
      postsLast24h: 0,
      dailyMax: 3,
      forbiddenPhrases: [],
      firmPublicationHosts: ["theseuscodex.com"],
    };

    expect(
      evaluateSocialPostGates(
        { id: "post-1", organizationId: "org-1", platform: "x", body: BODY, status: "draft", approvedBy: null },
        ctx,
      ).map((failure) => failure.code),
    ).toContain("NOT_APPROVED");
    expect(
      evaluateSocialPostGates(
        { id: "post-1", organizationId: "org-1", platform: "x", body: BODY, status: "approved", approvedBy: "founder-1" },
        ctx,
      ),
    ).toEqual([]);
  });

  it("approves, reruns gates, and calls the redacted Python live client with the expected body", async () => {
    const result = await approveAndPostSocialPost("post-1", {
      id: "founder-1",
      organizationId: "org-1",
    });

    expect(result).toEqual({ ok: true, tweetId: "tweet-1" });
    expect(dbMock.socialPost.update).toHaveBeenNthCalledWith(1, {
      where: { id: "post-1" },
      data: expect.objectContaining({
        body: BODY,
        status: "approved",
        approvedBy: "founder-1",
      }),
    });
    expect(pythonMock.runNoospherePython).toHaveBeenCalledWith(
      ["-m", "noosphere.social.x_live_client", "--post-json-stdin"],
      expect.objectContaining({
        stdin: JSON.stringify({ body: BODY }),
      }),
    );
    expect(dbMock.socialPost.update).toHaveBeenLastCalledWith({
      where: { id: "post-1" },
      data: expect.objectContaining({
        externalId: "tweet-1",
        status: "posted",
      }),
    });
  });

  it("records failed instead of posting when env mode gate is disabled", async () => {
    process.env.THESEUS_X_POSTING_ENABLED = "false";

    const result = await approveAndPostSocialPost("post-1", {
      id: "founder-1",
      organizationId: "org-1",
    });

    expect(result.ok).toBe(false);
    expect(String(result.error)).toContain("DISABLED");
    expect(pythonMock.runNoospherePython).not.toHaveBeenCalled();
    expect(dbMock.socialPost.update).toHaveBeenLastCalledWith({
      where: { id: "post-1" },
      data: expect.objectContaining({
        failureReason: expect.stringContaining("DISABLED"),
        status: "failed",
      }),
    });
  });

  it("evaluates Substack identity, content, source, and human gates", async () => {
    const ctx = {
      identityConfigured: true,
      missingIdentity: [],
      postingEnabled: true,
      killSwitchEngaged: false,
    };
    const failures = evaluateSubstackPostGates(
      {
        id: "post-2",
        organizationId: "org-1",
        platform: "substack",
        source: "session",
        sourceId: "upload-1",
        subject: "Recorded Reasoning",
        body: "A short subtitle.",
        markdownBody: "Long Substack body. ".repeat(40),
        status: "draft",
        approvedBy: null,
      },
      ctx,
      null,
    );

    expect(failures.map((failure) => failure.code)).toEqual(["NOT_APPROVED"]);
    expect(
      evaluateSubstackPostGates(
        {
          id: "post-2",
          organizationId: "org-1",
          platform: "substack",
          source: "session",
          sourceId: "upload-1",
          subject: "Bad",
          body: "A short subtitle.",
          markdownBody: "short",
          status: "approved",
          approvedBy: "founder-1",
        },
        ctx,
        "source upload was not found.",
      ).map((failure) => failure.code),
    ).toEqual(["CONTENT_REJECTED", "SOURCE_REJECTED"]);
  });

  it("builds Substack gate context from required env vars and kill state", async () => {
    dbMock.operatorState.findUnique.mockResolvedValueOnce({ value: { disabled: true } });

    const ctx = await substackGateContext("org-1");

    expect(ctx).toMatchObject({
      identityConfigured: true,
      postingEnabled: true,
      killSwitchEngaged: true,
    });
  });

  it("approves Substack, reruns gates, and calls the Python email client", async () => {
    const markdownBody = "Long Substack body. ".repeat(40);
    dbMock.socialPost.findFirst.mockResolvedValueOnce({
      id: "post-2",
      organizationId: "org-1",
      source: "session",
      sourceId: "upload-1",
      platform: "substack",
      subject: "Recorded Reasoning",
      body: "A short subtitle.",
      markdownBody,
      status: "draft",
      approvedBy: null,
    });
    dbMock.socialPost.update.mockImplementationOnce(async ({ data }: { data: Record<string, unknown> }) => ({
      id: "post-2",
      organizationId: "org-1",
      source: "session",
      sourceId: "upload-1",
      platform: "substack",
      subject: data.subject ?? "Recorded Reasoning",
      body: data.body ?? "A short subtitle.",
      markdownBody: data.markdownBody ?? markdownBody,
      status: data.status,
      approvedBy: data.approvedBy,
    }));
    pythonMock.runNoospherePython.mockResolvedValueOnce({
      code: 0,
      out: JSON.stringify({ external_id: "substack-email-to-post", sent_at: "2026-05-01T12:00:00.000Z" }),
      skipped: false,
      reason: "ok",
    });

    const result = await approveAndPostSocialPost("post-2", {
      id: "founder-1",
      organizationId: "org-1",
    });

    expect(result).toEqual({ ok: true, externalId: "substack-email-to-post" });
    expect(pythonMock.runNoospherePython).toHaveBeenCalledWith(
      ["-m", "noosphere.social.substack_live_client", "--post-json-stdin"],
      expect.objectContaining({
        stdin: JSON.stringify({
          subject: "Recorded Reasoning",
          markdownBody,
        }),
      }),
    );
  });

  it("creates a Substack draft from an upload only through the formatter, not SMTP", async () => {
    pythonMock.runNoospherePython.mockResolvedValueOnce({
      code: 0,
      out: JSON.stringify({
        subject: "Recorded Reasoning",
        body: "A short subtitle.",
        markdownBody: "Long Substack body. ".repeat(40),
      }),
      skipped: false,
      reason: "ok",
    });

    const result = await createSubstackDraftFromUpload("upload-1", {
      id: "founder-1",
      organizationId: "org-1",
    }, "session");

    expect(result).toEqual({ ok: true, postId: "post-substack" });
    expect(dbMock.socialPost.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        platform: "substack",
        source: "session",
        sourceId: "upload-1",
        status: "draft",
        subject: "Recorded Reasoning",
      }),
      select: { id: true },
    });
    expect(pythonMock.runNoospherePython).toHaveBeenCalledTimes(1);
  });

  it("bulk approval only shortcuts UX: each draft still reruns gates per row", async () => {
    process.env.THESEUS_X_CLIENT_MOCK = "1";
    const safeBody = "Bulk-safe fixture. https://x.com/source/status/10";
    const blockedBody = "Bulk blocked password fixture. https://x.com/source/status/11";
    const posts = new Map([
      [
        "safe-post",
        {
          id: "safe-post",
          organizationId: "org-1",
          source: "manual",
          sourceId: "safe-source",
          platform: "x",
          body: safeBody,
          subject: null,
          markdownBody: null,
          status: "draft",
          approvedBy: null,
        },
      ],
      [
        "blocked-post",
        {
          id: "blocked-post",
          organizationId: "org-1",
          source: "manual",
          sourceId: "blocked-source",
          platform: "x",
          body: blockedBody,
          subject: null,
          markdownBody: null,
          status: "draft",
          approvedBy: null,
        },
      ],
      [
        "rejected-post",
        {
          id: "rejected-post",
          organizationId: "org-1",
          source: "manual",
          sourceId: "rejected-source",
          platform: "x",
          body: safeBody,
          subject: null,
          markdownBody: null,
          status: "rejected",
          approvedBy: null,
        },
      ],
    ]);
    dbMock.socialPost.findFirst.mockImplementation(async ({ where }: { where: { id: string } }) => posts.get(where.id) || null);
    dbMock.socialPost.update.mockImplementation(async ({ where, data }: { where: { id: string }; data: Record<string, unknown> }) => {
      const current = posts.get(where.id);
      const next = { ...current, ...data };
      posts.set(where.id, next);
      return next;
    });

    const result = await bulkApproveDraftSocialPosts(["safe-post", "blocked-post", "rejected-post"], {
      id: "founder-1",
      organizationId: "org-1",
    });

    expect(result.ok).toBe(false);
    expect(result.results).toEqual([
      { postId: "safe-post", ok: true, error: undefined },
      {
        postId: "blocked-post",
        ok: false,
        error: expect.stringContaining("CONTENT_REJECTED"),
      },
      {
        postId: "rejected-post",
        ok: false,
        error: "bulk_actions_apply_to_drafts_only",
      },
    ]);
    expect(posts.get("safe-post")).toMatchObject({
      externalId: expect.stringMatching(/^mock-/),
      status: "posted",
    });
    expect(posts.get("blocked-post")).toMatchObject({
      failureReason: expect.stringContaining("CONTENT_REJECTED"),
      status: "failed",
    });
    expect(posts.get("rejected-post")).toMatchObject({ status: "rejected" });
  });
});
