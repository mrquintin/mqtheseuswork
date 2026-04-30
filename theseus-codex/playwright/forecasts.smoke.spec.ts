import { expect, test } from "@playwright/test";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

async function loginAsSeededFounder(page: import("@playwright/test").Page) {
  test.skip(!founderEmail || !founderPassword, "seeded founder credentials are not set");
  await page.goto("/login?next=/forecasts/operator");
  await page.getByLabel(/organization/i).fill(founderOrg);
  await page.getByLabel(/email/i).fill(founderEmail!);
  await page.getByLabel(/passphrase/i).fill(founderPassword!);
  await page.getByRole("button", { name: /enter the codex/i }).click();
  await expect(page).toHaveURL(/\/forecasts\/operator/, { timeout: 15_000 });
}

test("public Forecasts surface renders from homepage to detail to portfolio", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/CURRENTS - live opinion/i)).toBeVisible();
  await expect(page.getByText(/FORECASTS - live predictions/i)).toBeVisible();

  await page.goto("/forecasts");
  const firstCard = page.getByRole("link", { name: /Forecast:/i }).first();
  await expect(firstCard).toBeVisible();
  await firstCard.click();

  await expect(page.locator("h1")).toBeVisible();
  await expect(page.getByLabel(/Forecast reasoning and citations/i)).toBeVisible();
  await expect(page.getByLabel(/Citation drawer/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /Citation 1:/i })).toBeVisible();

  const focusedIds: string[] = [];
  for (let index = 0; index < 3; index += 1) {
    await page.keyboard.press("]");
    focusedIds.push(
      await page.evaluate(() => document.activeElement?.id ?? ""),
    );
  }
  expect(focusedIds.every((id) => id.startsWith("forecast-drawer-citation-"))).toBe(true);
  expect(new Set(focusedIds).size).toBeGreaterThan(1);

  await page.goto("/forecasts/portfolio");
  await expect(
    page.getByRole("heading", { name: /How often does p% confident/i }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /Rolling 30-day Brier score/i }),
  ).toBeVisible();
  await expect(page.locator("[data-kill-switch]").first()).toHaveAttribute(
    "data-kill-switch",
    "clear",
  );
});

test("operator route requires login and disables confirmations when live trading is off", async ({
  page,
}) => {
  await page.goto("/forecasts/operator");
  await expect(page).toHaveURL(/\/login(?:\?|$)/);

  await loginAsSeededFounder(page);
  await expect(page.getByRole("heading", { name: /Forecasts operator/i })).toBeVisible();
  await expect(page.getByText(/Pending live authorizations/i)).toBeVisible();
  await expect(page.getByText(/Kill switch/i)).toBeVisible();
  await expect(page.getByText(/Live bet ledger/i)).toBeVisible();

  const confirmButtons = page.locator("[data-confirm-bet-id]");
  if ((await confirmButtons.count()) > 0) {
    await expect(confirmButtons.first()).toBeDisabled();
  } else {
    await expect(page.getByText(/Live trading disabled server-side/i)).toBeVisible();
  }
});

test("env-injected live mode can authorize a prediction without submitting a live bet", async ({
  page,
}) => {
  test.skip(
    process.env.FORECASTS_LIVE_TRADING_ENABLED !== "true",
    "run this smoke with FORECASTS_LIVE_TRADING_ENABLED=true in the test harness",
  );

  await loginAsSeededFounder(page);
  const authorizeButton = page.getByRole("button", {
    name: /Authorize live betting on this prediction/i,
  }).first();
  await expect(authorizeButton).toBeVisible();

  const authorizeRequest = page.waitForRequest(/\/api\/forecasts\/operator\/.+\/authorize-live$/);
  await authorizeButton.click();
  const request = await authorizeRequest;
  const match = request.url().match(/\/api\/forecasts\/operator\/([^/]+)\/authorize-live$/);
  expect(match).not.toBeNull();
  const predictionId = decodeURIComponent(match![1]);

  await expect
    .poll(async () => {
      return page.evaluate(async (id) => {
        const res = await fetch(`/api/forecasts/${encodeURIComponent(id)}`);
        if (!res.ok) return null;
        const body = await res.json();
        return body.live_authorized_at ?? null;
      }, predictionId);
    })
    .not.toBeNull();
});
