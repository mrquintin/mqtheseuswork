import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createSqlAdapter } from "../src/lib/prismaAdapter";
import { SUBSTACK_KILL_KEY } from "../src/lib/socialPosting";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("session transcript can publish to Substack through review approval", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL ||
      !founderEmail ||
      !founderPassword ||
      process.env.THESEUS_SUBSTACK_CLIENT_MOCK !== "1" ||
      process.env.THESEUS_SUBSTACK_POSTING_ENABLED !== "true" ||
      !process.env.SUBSTACK_SMTP_HOST ||
      !process.env.SUBSTACK_SMTP_PORT ||
      !process.env.SUBSTACK_SMTP_USER ||
      !process.env.SUBSTACK_SMTP_PASS ||
      !process.env.SUBSTACK_PUBLISH_EMAIL ||
      !process.env.SUBSTACK_FROM_EMAIL,
    "DATABASE_URL, founder credentials, and mocked Substack posting env are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const sourceId = `e2e-substack-${Date.now()}`;
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
      where: { organizationId: org!.id, key: SUBSTACK_KILL_KEY },
    });
    const upload = await db.upload.create({
      data: {
        organizationId: org!.id,
        founderId: founder!.id,
        title: `E2E Substack Session ${sourceId}`,
        description: "E2E Substack transcript fixture.",
        sourceType: "transcript",
        originalName: `${sourceId}.txt`,
        mimeType: "text/plain",
        filePath: `/tmp/${sourceId}.txt`,
        fileSize: 1024,
        textContent:
          "[00:00:12] Michael: Conviction has to survive inspection.\n" +
          "[00:01:30] Ada: Memory changes incentives.\n" +
          "[00:02:45] Michael: Publish the part that can bear pressure.\n" +
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
    await page.getByTestId("publish-to-substack").click();
    await page.waitForURL(/\/social\/[^/]+$/, { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: /E2E Substack Session/i })).toBeVisible();

    await page.getByTestId("substack-approve-publish").click();
    await expect
      .poll(async () =>
        db.socialPost.findFirst({
          where: { sourceId: upload.id, platform: "substack" },
          select: { status: true, externalId: true },
        }),
      )
      .toMatchObject({ status: "posted", externalId: expect.stringMatching(/^mock-substack-/) });
    await expect(page.getByTestId("substack-posted-state")).toContainText("externalId");
  } finally {
    if (uploadId) await db.socialPost.deleteMany({ where: { sourceId: uploadId } });
    await db.upload.deleteMany({ where: { originalName: `${sourceId}.txt` } });
    await db.$disconnect();
  }
});
