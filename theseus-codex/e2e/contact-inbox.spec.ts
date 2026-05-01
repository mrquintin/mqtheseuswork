import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";

import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("public contact form lands in the admin inbox", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded admin credentials are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const nonce = Date.now();
  const fromEmail = `contact-e2e-${nonce}@example.com`;
  const subject = `E2E contact inbox ${nonce}`;
  const body =
    "I am interested in speaking with Theseus about a summit session on prediction markets.";

  try {
    const org = await db.organization.findUnique({ where: { slug: founderOrg } });
    expect(org).toBeTruthy();
    const founder = await db.founder.findFirst({
      where: { organizationId: org!.id, email: founderEmail! },
      select: { role: true },
    });
    test.skip(founder?.role !== "admin", "seeded e2e founder must be an admin");

    await db.contactSubmission.deleteMany({ where: { fromEmail } });

    await page.goto("/about#contact");
    await page.getByLabel("Name").fill("E2E Prospective Guest");
    await page.getByLabel("Email").fill(fromEmail);
    await page.getByLabel("Subject").fill(subject);
    await page.getByLabel("Message").fill(body);
    await page.getByRole("button", { name: /send message/i }).click();
    await expect(
      page.getByText("Received. The firm will read this within ~7 days."),
    ).toBeVisible();

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await page.getByRole("link", { name: "Manage" }).click();
    await page.getByRole("link", { name: "Contact inbox" }).click();
    await expect(page).toHaveURL(/\/admin\/contact(?:\?|$)/);
    await expect(page.getByText(subject)).toBeVisible();
    await expect(page.getByRole("link", { name: fromEmail })).toBeVisible();
  } finally {
    await db.contactSubmission.deleteMany({ where: { fromEmail } }).catch(() => {});
    await db.$disconnect();
  }
});
