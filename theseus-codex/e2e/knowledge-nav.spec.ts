import { expect, test } from "@playwright/test";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("dashboard Knowledge nav opens the four knowledge tabs", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded founder credentials are required",
  );

  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/organization/i).fill(founderOrg);
  await page.getByLabel(/email/i).fill(founderEmail!);
  await page.getByLabel(/passphrase/i).fill(founderPassword!);
  await page.getByRole("button", { name: /enter the codex/i }).click();
  await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

  await page.getByRole("link", { name: "Knowledge" }).click();
  await expect(page).toHaveURL(/\/knowledge(?:\?.*)?$/);
  await expect(page.getByRole("link", { name: "Conclusions" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Explorer" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Library" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Transcripts" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible();

  await page.getByRole("link", { name: "Explorer" }).click();
  await expect(page).toHaveURL(/\/knowledge\?tab=explorer$/);
  await expect(page.getByRole("heading", { name: "Explorer" })).toBeVisible();

  await page.getByRole("link", { name: "Library" }).click();
  await expect(page).toHaveURL(/\/knowledge\?tab=library$/);
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();

  await page.getByRole("link", { name: "Transcripts" }).click();
  await expect(page).toHaveURL(/\/knowledge\?tab=transcripts$/);
  await expect(page.getByRole("heading", { name: "Transcripts" })).toBeVisible();
});
