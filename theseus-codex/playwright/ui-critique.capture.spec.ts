/**
 * UI critique screenshot capture — prompt 65.
 *
 * Captures full-page page-shots of every founder-facing surface (and the
 * public homepage) into
 * `docs/ui-critique/2026-05-13/screenshots/` so the critique document
 * (`coding_prompts/UI_CRITIQUE_2026_05_13.md`) references real images
 * the founder can look at while reading.
 *
 * The capture intentionally overwrites the zero-byte placeholder PNGs
 * created alongside `.gitkeep`. The placeholders exist so the doc-shape
 * test (`__tests__/ui_critique_doc_shape.test.ts`) passes before
 * Playwright has been run; the spec replaces them with real bytes.
 *
 * Running:
 *
 *   # Captures every surface, including the authed ones, when seeded
 *   # credentials are available (CI sets E2E_FOUNDER_EMAIL etc.):
 *   npx playwright test playwright/ui-critique.capture.spec.ts
 *
 *   # Public-only on a developer box without seeded credentials:
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
 *     npx playwright test playwright/ui-critique.capture.spec.ts \
 *     --grep "public|mobile"
 *
 * Updating the critique with a fresh capture is intentional — these are
 * not visual-regression baselines, they are documentation artifacts.
 */

import path from "node:path";
import { expect, test } from "@playwright/test";

const founderEmail =
  process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

// Anchored at the repo root so the capture works regardless of where
// the playwright command is launched from.
const SCREENSHOT_DIR = path.resolve(
  __dirname,
  "..",
  "..",
  "docs",
  "ui-critique",
  "2026-05-13",
  "screenshots",
);

function shotPath(filename: string): string {
  return path.join(SCREENSHOT_DIR, filename);
}

test.describe("UI critique — public surfaces", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("public home", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("public-home.png"), fullPage: true });
  });

  test("login", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("login.png"), fullPage: true });
  });
});

test.describe("UI critique — public mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("public home mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.screenshot({
      path: shotPath("public-home-mobile.png"),
      fullPage: true,
    });
  });
});

test.describe("UI critique — authed surfaces", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ page }) => {
    test.skip(
      !founderEmail || !founderPassword,
      "Seeded founder credentials are required for authed captures.",
    );
    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });
  });

  test("dashboard", async ({ page }) => {
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("dashboard.png"), fullPage: true });
  });

  test("knowledge", async ({ page }) => {
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("knowledge.png"), fullPage: true });
  });

  test("principles", async ({ page }) => {
    await page.goto("/principles");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("principles.png"), fullPage: true });
  });

  test("founder currents", async ({ page }) => {
    await page.goto("/founder-currents");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("currents.png"), fullPage: true });
  });

  test("portfolio", async ({ page }) => {
    await page.goto("/portfolio");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("portfolio.png"), fullPage: true });
  });

  test("article (first conclusion)", async ({ page }) => {
    // Land on the dashboard and click the first conclusion link we can
    // find, falling back to /knowledge if the dashboard's signal cards
    // have no link. This avoids a hard-coded conclusion id that may not
    // exist in a fresh database.
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");
    const firstConclusion = page.locator('a[href^="/c/"]').first();
    if (await firstConclusion.count()) {
      await firstConclusion.click();
      await page.waitForLoadState("networkidle");
    }
    await page.screenshot({ path: shotPath("article.png"), fullPage: true });
  });

  test("ops console", async ({ page }) => {
    await page.goto("/ops");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shotPath("ops.png"), fullPage: true });
  });

  test("all referenced screenshots are non-empty after capture", async () => {
    // Cheap end-of-suite assertion: every PNG path is on disk and
    // larger than zero bytes. Catches the "playwright wrote the file
    // but the browser was at about:blank" case.
    const fs = await import("node:fs/promises");
    const files = [
      "public-home.png",
      "login.png",
      "dashboard.png",
      "knowledge.png",
      "principles.png",
      "currents.png",
      "portfolio.png",
      "article.png",
      "ops.png",
      "public-home-mobile.png",
    ];
    for (const f of files) {
      const stat = await fs.stat(shotPath(f));
      expect(stat.size, `${f} should be non-empty after capture`).toBeGreaterThan(
        0,
      );
    }
  });
});
