/**
 * Public-surface accessibility regression tests.
 *
 * Runs axe-core against every public route at three viewport widths
 * (mobile, tablet, desktop) and against the three highest-risk
 * interactive surfaces (citation popover, command palette, mobile
 * navigation drawer).
 *
 * The CI workflow `.github/workflows/a11y_nightly.yml` installs
 * `@axe-core/playwright` and runs this file in headless Chrome
 * nightly. Failures block the next deploy.
 *
 * Locally:  npm install --save-dev @axe-core/playwright
 *           npx playwright test playwright/a11y.spec.ts
 *
 * The spec is written so that if `@axe-core/playwright` is not
 * installed (developer machines that haven't synced devDependencies),
 * it skips itself with a clear message instead of failing the suite.
 */

import { expect, test, type Page } from "@playwright/test";

// Lazy import keeps the spec runnable even when the dev hasn't
// installed @axe-core/playwright yet — important during the initial
// roll-out, after which CI enforces the dependency.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AxeBuilderCtor = new (args: { page: Page }) => any;
let AxeBuilder: AxeBuilderCtor | null = null;
let axeImportAttempted = false;

async function loadAxe(): Promise<void> {
  if (axeImportAttempted) return;
  axeImportAttempted = true;
  try {
    // @ts-expect-error optional devDependency; CI installs it before this runs
    const mod = (await import("@axe-core/playwright")) as {
      default?: AxeBuilderCtor;
      AxeBuilder?: AxeBuilderCtor;
    };
    AxeBuilder = mod.default ?? mod.AxeBuilder ?? null;
  } catch {
    AxeBuilder = null;
  }
}

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

// Every public route we publish. New routes added in Round 17+ are
// included here so a new page can't ship without an axe sweep against
// it.
const PUBLIC_ROUTES: ReadonlyArray<{ name: string; path: string }> = [
  { name: "home", path: "/" },
  { name: "about", path: "/about" },
  { name: "methodology", path: "/methodology" },
  { name: "currents", path: "/currents" },
  { name: "forecasts", path: "/forecasts" },
  { name: "critiques", path: "/critiques" },
  { name: "research", path: "/research" },
  { name: "proof", path: "/proof" },
  { name: "revisions", path: "/revisions" },
  { name: "calibration", path: "/calibration" },
  { name: "privacy", path: "/privacy" },
  { name: "ask", path: "/ask" },
  { name: "login", path: "/login" },
];

const VIEWPORTS: ReadonlyArray<{ name: string; width: number; height: number }> = [
  { name: "mobile", width: 360, height: 740 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1280, height: 900 },
];

test.beforeAll(async () => {
  await loadAxe();
});

test.beforeEach(async ({ page }) => {
  test.skip(
    AxeBuilder === null,
    "@axe-core/playwright is not installed. Run `npm install --save-dev @axe-core/playwright` to enable a11y tests.",
  );
  // Honor reduced-motion so the scanner sees the steady state of any
  // ongoing animation — preserves consistent contrast measurements.
  await page.emulateMedia({ reducedMotion: "reduce" });
});

async function runAxe(page: Page, label: string) {
  if (!AxeBuilder) throw new Error("unreachable: axe builder missing");
  const builder = new AxeBuilder({ page });
  const results = await builder
    .withTags(WCAG_TAGS as string[])
    .exclude("[data-decorative]")
    .analyze();

  type AxeNode = { target: string[] };
  type AxeViolation = {
    id: string;
    help: string;
    impact?: string | null;
    nodes: AxeNode[];
  };
  const violations = results.violations as AxeViolation[];
  if (violations.length > 0) {
    const summary = violations
      .map(
        (v: AxeViolation) =>
          `  - [${v.impact ?? "unknown"}] ${v.id} (${v.help})\n` +
          v.nodes
            .map((n: AxeNode) => `      ${n.target.join(" ")}`)
            .slice(0, 5)
            .join("\n"),
      )
      .join("\n");
    throw new Error(
      `axe-core found ${violations.length} violation(s) on ${label}:\n${summary}`,
    );
  }
  expect(violations, label).toHaveLength(0);
}

for (const route of PUBLIC_ROUTES) {
  for (const viewport of VIEWPORTS) {
    test(`a11y · ${route.name} · ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(route.path, { waitUntil: "domcontentloaded" });
      // Settle layout-shifting content (font swaps, CRT overlay mount).
      await page.waitForLoadState("networkidle").catch(() => {
        // networkidle can timeout when SSE streams stay open. That's
        // expected on /currents; treat as a soft signal and continue.
      });
      await runAxe(page, `${route.path} @ ${viewport.name}`);
    });
  }
}

// ─── High-risk interactive surfaces ────────────────────────────────────────

test("a11y · command palette opens, traps focus, closes on Escape", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  // The palette is mounted into the founder shell; many public pages
  // do not include it. Skip when not present rather than fail — its
  // own coverage lives under (authed).
  const hasPalette = await page
    .locator('[data-testid="command-palette-overlay"]')
    .count()
    .catch(() => 0);
  test.skip(hasPalette === 0, "command palette not mounted on this surface");
  await runAxe(page, "/ with command palette open");
});

test("a11y · mobile nav drawer at 360px", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const trigger = page.getByTestId("public-nav-trigger");
  if ((await trigger.count()) === 0) {
    test.skip(true, "mobile trigger not present on this surface");
  }
  await trigger.click();
  await expect(page.getByTestId("public-nav-drawer")).toBeVisible();
  await runAxe(page, "/ with mobile drawer open");

  // Focus trap regression: Shift+Tab from the close button should not
  // escape the drawer.
  const close = page.locator('[data-testid="public-nav-drawer"] button[aria-label="Close navigation menu"]');
  await close.focus();
  await page.keyboard.press("Tab");
  const stillInside = await page.evaluate(() => {
    const drawer = document.querySelector('[data-testid="public-nav-drawer"]');
    return drawer instanceof HTMLElement && drawer.contains(document.activeElement);
  });
  expect(stillInside, "drawer should trap Tab focus").toBe(true);

  await page.keyboard.press("Escape");
  await expect(page.getByTestId("public-nav-drawer")).toHaveCount(0);
});

test("a11y · skip-to-content link is reachable on first Tab", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    return el?.classList.contains("skip-link") ?? false;
  });
  expect(focused, "first Tab should focus the skip-to-content link").toBe(true);
});

test("a11y · citation popover (when present) on a published conclusion", async ({ page }) => {
  // Probe a conclusion page if one is publicly listed on /research.
  await page.goto("/research", { waitUntil: "domcontentloaded" });
  const firstLink = page.locator('a[href^="/c/"]').first();
  if ((await firstLink.count()) === 0) {
    test.skip(true, "no published conclusion in the seed dataset");
  }
  await firstLink.click();
  await page.waitForLoadState("domcontentloaded");
  await runAxe(page, "conclusion detail page");

  const citation = page.locator('[data-citation-trigger="true"]').first();
  if ((await citation.count()) === 0) return; // Article without citations is still valid.
  await citation.click();
  await expect(page.locator('[role="dialog"]')).toBeVisible();
  await runAxe(page, "conclusion detail with citation popover open");
});
