import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("dashboard conclusion action menu is keyboard-accessible", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded founder credentials are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const noosphereId = `e2e-dashboard-actions-${Date.now()}`;
  const title = `Keyboard dismissal affordance ${noosphereId}`;

  try {
    const org = await db.organization.findUnique({ where: { slug: founderOrg } });
    expect(org).toBeTruthy();
    const founder = await db.founder.findFirst({
      where: { organizationId: org!.id, email: founderEmail! },
    });
    expect(founder).toBeTruthy();

    const conclusion = await db.conclusion.create({
      data: {
        organizationId: org!.id,
        noosphereId,
        text: title,
        confidenceTier: "open",
        rationale: "E2E keyboard accessibility fixture.",
        supportingPrincipleIds: "[]",
        evidenceChainClaimIds: "[]",
        dissentClaimIds: "[]",
        confidence: 0.42,
        topicHint: "e2e",
        attributedFounderId: founder!.id,
      },
    });
    await db.dashboardDismissal.deleteMany({
      where: { founderId: founder!.id, conclusionId: conclusion.id },
    });

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    const card = page
      .locator('[data-testid="dashboard-conclusion-card"]')
      .filter({ hasText: title })
      .first();
    await expect(card).toBeVisible();

    const menuButton = card.getByRole("button", { name: /conclusion actions/i });
    await menuButton.focus();
    await expect(menuButton).toBeFocused();
    await page.keyboard.press("Enter");

    const menu = card.getByRole("menu", { name: "Conclusion actions" });
    await expect(menu).toBeVisible();

    const dismissItem = card.getByRole("menuitem", {
      name: /Hide this conclusion from MY dashboard/i,
    });
    const requestItem = card.getByRole("menuitem", {
      name: /Request deletion/i,
    });

    await expect(dismissItem).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(requestItem).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(dismissItem).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page.getByText("Hidden from your dashboard.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Undo dismissal" })).toBeVisible();
    await expect
      .poll(async () =>
        db.dashboardDismissal.count({
          where: { founderId: founder!.id, conclusionId: conclusion.id },
        }),
      )
      .toBe(1);
  } finally {
    await db.conclusion.deleteMany({ where: { noosphereId } });
    await db.$disconnect();
  }
});
