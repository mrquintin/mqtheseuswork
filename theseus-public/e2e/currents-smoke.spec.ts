import { test, expect } from "@playwright/test";

/**
 * Opt-in smoke test for the public currents surface.
 *
 * This is NOT wired into `npm test` — run it via `npm run test:e2e` after
 * `npm i` pulls `@playwright/test`. It assumes a local dev server is
 * either already running on :3001 (webServer.reuseExistingServer=true)
 * or will be started by Playwright via `npm run dev`.
 *
 * We make no assertions that require a live scheduler or a populated
 * database — this is a smoke test, not proof. A fresh install with an
 * empty DB should still pass.
 */

test("currents page renders", async ({ page }) => {
  await page.goto("/currents");
  // The currents layout renders a main heading — just confirm the HTML
  // parses and the page isn't a 500.
  await expect(page).toHaveURL(/\/currents/);
  await expect(page.locator("main")).toBeVisible({ timeout: 10_000 });
});

test("home page reachable", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL("http://localhost:3001/");
  await expect(page.locator("body")).toBeVisible();
});
