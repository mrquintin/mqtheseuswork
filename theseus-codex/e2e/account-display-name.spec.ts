import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

const nudgeCopy =
  "Set your display name on /account so your peers see something meaningful.";

test("founder with no displayName sees the nudge and can set a display name", async ({
  page,
}) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded founder credentials are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const displayName = `E2E Founder ${Date.now()}`;
  let founderId = "";
  let originalDisplayName: string | null = null;
  let originalBio: string | null = null;
  let originalNudgeDismissedAt: Date | null = null;

  try {
    const org = await db.organization.findUnique({ where: { slug: founderOrg } });
    expect(org).toBeTruthy();
    const founder = await db.founder.findFirst({
      where: { organizationId: org!.id, email: founderEmail! },
      select: {
        id: true,
        displayName: true,
        bio: true,
        accountNudgeDismissedAt: true,
      },
    });
    expect(founder).toBeTruthy();

    founderId = founder!.id;
    originalDisplayName = founder!.displayName;
    originalBio = founder!.bio;
    originalNudgeDismissedAt = founder!.accountNudgeDismissedAt;

    await db.founder.update({
      where: { id: founderId },
      data: { displayName: null, accountNudgeDismissedAt: null },
    });

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await expect(page.getByText(nudgeCopy)).toBeVisible();
    await page.getByRole("link", { name: nudgeCopy }).click();
    await page.waitForURL(/\/account(?:\?|$)/, { timeout: 15_000 });

    await page.getByLabel(/display name/i).fill(displayName);
    await page.getByLabel(/^bio$/i).fill("E2E profile bio.");
    await page.getByRole("button", { name: /save profile/i }).click();
    await expect(page.getByText("Profile saved.")).toBeVisible();

    await page.goto("/dashboard");
    await expect(page.getByText(`Welcome back, ${displayName}.`)).toBeVisible();
    await expect(page.getByText(nudgeCopy)).toHaveCount(0);
  } finally {
    if (founderId) {
      await db.founder.update({
        where: { id: founderId },
        data: {
          displayName: originalDisplayName,
          bio: originalBio,
          accountNudgeDismissedAt: originalNudgeDismissedAt,
        },
      });
    }
    await db.$disconnect();
  }
});
