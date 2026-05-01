import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createSqlAdapter } from "../src/lib/prismaAdapter";
import { SOCIAL_KILL_KEY } from "../src/lib/socialPosting";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("admin can approve a held social draft against the mocked X client", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL ||
      !founderEmail ||
      !founderPassword ||
      process.env.THESEUS_X_CLIENT_MOCK !== "1" ||
      process.env.THESEUS_X_POSTING_ENABLED !== "true" ||
      !process.env.X_BOT_OAUTH_REFRESH_TOKEN,
    "DATABASE_URL, founder credentials, and mocked X posting env are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const sourceId = `e2e-social-${Date.now()}`;
  const body = `E2E social approval fixture ${sourceId}. https://x.com/source/status/1`;

  try {
    const org = await db.organization.findUnique({ where: { slug: founderOrg } });
    expect(org).toBeTruthy();
    await db.operatorState.deleteMany({
      where: { organizationId: org!.id, key: SOCIAL_KILL_KEY },
    });
    await db.socialPost.create({
      data: {
        organizationId: org!.id,
        source: "manual",
        sourceId,
        platform: "x",
        body,
        media: [],
        status: "draft",
      },
    });

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await page.goto("/social");
    await expect(page.getByText(body)).toBeVisible();
    await page.getByTestId("social-approve-post").first().click();
    await expect
      .poll(async () =>
        db.socialPost.findFirst({
          where: { sourceId },
          select: { status: true, externalId: true },
        }),
      )
      .toMatchObject({ status: "posted", externalId: expect.stringMatching(/^mock-/) });

    await page.goto("/social?tab=posted");
    await expect(page.getByText(body)).toBeVisible();
  } finally {
    await db.socialPost.deleteMany({ where: { sourceId } });
    await db.$disconnect();
  }
});
