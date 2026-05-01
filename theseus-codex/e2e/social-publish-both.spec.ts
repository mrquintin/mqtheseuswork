import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";
const SOCIAL_KILL_KEY = "theseus.x_kill";
const LEGACY_SOCIAL_KILL_KEY = "theseus.social_kill";
const SUBSTACK_KILL_KEY = "theseus.substack_kill";

test("session can publish to bundled X and Substack drafts, then bulk approve both", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL ||
      !founderEmail ||
      !founderPassword ||
      process.env.THESEUS_X_CLIENT_MOCK !== "1" ||
      process.env.THESEUS_X_POSTING_ENABLED !== "true" ||
      !process.env.X_BOT_OAUTH_REFRESH_TOKEN ||
      process.env.THESEUS_SUBSTACK_CLIENT_MOCK !== "1" ||
      process.env.THESEUS_SUBSTACK_POSTING_ENABLED !== "true" ||
      !process.env.SUBSTACK_SMTP_HOST ||
      !process.env.SUBSTACK_SMTP_PORT ||
      !process.env.SUBSTACK_SMTP_USER ||
      !process.env.SUBSTACK_SMTP_PASS ||
      !process.env.SUBSTACK_PUBLISH_EMAIL ||
      !process.env.SUBSTACK_FROM_EMAIL,
    "DATABASE_URL, founder credentials, and mocked X/Substack posting env are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const sourceId = `e2e-both-${Date.now()}`;
  let uploadId = "";

  try {
    const org = await db.organization.findUnique({
      where: { slug: founderOrg },
      include: { founders: { where: { email: founderEmail! }, take: 1 } },
    });
    expect(org).toBeTruthy();
    const founder = org!.founders[0];
    expect(founder).toBeTruthy();
    await db.operatorState.deleteMany({
      where: {
        organizationId: org!.id,
        key: { in: [SOCIAL_KILL_KEY, LEGACY_SOCIAL_KILL_KEY, SUBSTACK_KILL_KEY] },
      },
    });
    const upload = await db.upload.create({
      data: {
        organizationId: org!.id,
        founderId: founder!.id,
        title: `E2E Bundled Session ${sourceId}`,
        description: "E2E bundled transcript fixture.",
        sourceType: "transcript",
        originalName: `${sourceId}.txt`,
        mimeType: "text/plain",
        filePath: `/tmp/${sourceId}.txt`,
        fileSize: 1024,
        textContent:
          "[00:00:12] Michael: The operator should approve the artifact once.\n" +
          "[00:01:30] Ada: The channels should remain separate behind the panel.\n" +
          "[00:02:45] Michael: A bundle keeps the paired drafts visible.\n" +
          "The remaining transcript body is deliberately long enough to clear the Substack gate. ".repeat(8),
        status: "ingested",
        visibility: "org",
      },
    });
    uploadId = upload.id;

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await page.goto(`/sessions/${upload.id}`);
    await page.getByTestId("publish-to-dropdown").click();
    await page.getByTestId("publish-to-both").click();
    await page.waitForURL(/\/social\?bundle=/, { timeout: 20_000 });

    await expect
      .poll(async () =>
        db.socialPost.findMany({
          where: { sourceId: upload.id },
          orderBy: { platform: "asc" },
          select: { bundleId: true, platform: true, status: true },
        }),
      )
      .toHaveLength(2);

    const created = await db.socialPost.findMany({
      where: { sourceId: upload.id },
      orderBy: { platform: "asc" },
      select: { bundleId: true, platform: true, status: true },
    });
    expect(created[0].bundleId).toBeTruthy();
    expect(new Set(created.map((post) => post.bundleId)).size).toBe(1);
    expect(created.map((post) => `${post.platform}:${post.status}`)).toEqual(["substack:draft", "x:draft"]);

    await expect(page.getByTestId("social-bundle-group")).toBeVisible();
    const checkboxes = page.locator('input[name="postId"]');
    await expect(checkboxes).toHaveCount(2);
    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();
    await page.getByTestId("bulk-approve-selected").click();

    await expect
      .poll(async () =>
        db.socialPost.findMany({
          where: { sourceId: upload.id },
          orderBy: { platform: "asc" },
          select: { externalId: true, platform: true, status: true },
        }),
      )
      .toEqual([
        { externalId: expect.stringMatching(/^mock-substack-/), platform: "substack", status: "posted" },
        { externalId: expect.stringMatching(/^mock-/), platform: "x", status: "posted" },
      ]);

    await page.goto(`/social?status=posted&bundle=${created[0].bundleId}`);
    await expect(page.getByTestId("social-bundle-group")).toContainText("posted");
  } finally {
    if (uploadId) await db.socialPost.deleteMany({ where: { sourceId: uploadId } });
    await db.upload.deleteMany({ where: { originalName: `${sourceId}.txt` } });
    await db.$disconnect();
  }
});
