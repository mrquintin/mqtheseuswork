/**
 * Visual regression — dashboard header + primary nav strip.
 *
 * The Round 20 trigger was the founder reporting that the "Library"
 * button rendered in a different font from "Upload". The root cause
 * was per-instance `className` choices (`btn--quiet` Inter vs.
 * `btn-solid btn` Cinzel uppercase) on the two `<Link>`s in the
 * header. Both now route through the `PrimaryNavLink` primitive in
 * `src/components/nav/PrimaryNav.tsx`, which guarantees they share
 * font family / size / weight.
 *
 * This snapshot pins the nav strip's pixels. Future PRs that touch
 * the primitive or the underlying `.btn*` CSS will produce a diff in
 * the report, prompting a human reviewer to confirm the change was
 * intended.
 *
 * The dashboard requires authentication; the spec mirrors the skip
 * pattern used elsewhere (see `e2e/dashboard-conclusion-actions.spec.ts`)
 * so developer machines without seeded credentials don't fail it.
 * CI workflows that set the credentials run it and gate on the
 * baseline.
 *
 * Updating the baseline (intentionally):
 *   npx playwright test playwright/dashboard-nav.snapshot.spec.ts \
 *     --update-snapshots
 */

import { expect, test } from "@playwright/test";

const founderEmail =
  process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("dashboard nav strip has stable typography", async ({ page }) => {
  test.skip(
    !founderEmail || !founderPassword,
    "Seeded founder credentials are required for the dashboard snapshot.",
  );

  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/organization/i).fill(founderOrg);
  await page.getByLabel(/email/i).fill(founderEmail!);
  await page.getByLabel(/passphrase/i).fill(founderPassword!);
  await page.getByRole("button", { name: /enter the codex/i }).click();
  await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

  // The header is the only `<header>` on the dashboard route.
  const header = page.locator("header.page-header").first();
  await expect(header).toBeVisible();

  // The primary-nav strip lives inside `page-header__actions`. It
  // must contain both buttons; missing either means the dashboard
  // render regressed before we even hit the typography check.
  const nav = header.locator(".page-header__actions");
  await expect(nav.getByRole("link", { name: "Library" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Upload" })).toBeVisible();

  await expect(header).toHaveScreenshot("dashboard-nav.png", {
    maxDiffPixelRatio: 0.01,
  });
});

test("dashboard no longer renders the Attention panel", async ({ page }) => {
  test.skip(
    !founderEmail || !founderPassword,
    "Seeded founder credentials are required for the dashboard smoke check.",
  );

  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/organization/i).fill(founderOrg);
  await page.getByLabel(/email/i).fill(founderEmail!);
  await page.getByLabel(/passphrase/i).fill(founderPassword!);
  await page.getByRole("button", { name: /enter the codex/i }).click();
  await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

  // F. Smoke: the dashboard render must not surface the old
  //   AttentionQueue and must not show the word "Attention" to the
  //   founder anywhere in the visible body. (The Currents pulse can
  //   still display the lowercase "attention" status when the
  //   service is degraded — the test targets the dashboard surface
  //   for the title-case word the founder reported as confusing.)
  await expect(
    page.locator('[data-testid="attention-queue"]'),
  ).toHaveCount(0);

  const bodyText = (await page.locator("main").innerText()) ?? "";
  expect(bodyText).not.toMatch(/\bAttention\b/);

  // No console errors during the render — a missing-component or
  // missing-import error would manifest here.
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.reload();
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
});
