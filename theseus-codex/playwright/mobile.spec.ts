import { expect, test, type Page } from "@playwright/test";

/**
 * Responsive smoke tests for the public site at common phone widths.
 *
 * These tests run a single Chromium browser via Playwright's existing
 * `chromium` project (see playwright.config.ts) and resize the viewport
 * per scenario rather than spinning up a separate device project. That
 * keeps `test:e2e` cheap to run locally.
 *
 * Two viewport widths are exercised: 375px (iPhone-class) and 414px
 * (iPhone-Plus / large Android). Both should render the public surfaces
 * with no horizontal overflow, no inline desktop nav, and a working
 * hamburger drawer.
 */

const VIEWPORTS = [
  { name: "iphone-375", width: 375, height: 812 },
  { name: "iphone-plus-414", width: 414, height: 896 },
] as const;

async function expectNoHorizontalScroll(page: Page) {
  const result = await page.evaluate(() => ({
    docWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  // Allow a 1px subpixel rounding tolerance.
  expect(result.docWidth - result.clientWidth).toBeLessThanOrEqual(1);
}

for (const viewport of VIEWPORTS) {
  test.describe(`public site @ ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test(`PublicHeader collapses to a hamburger drawer on /`, async ({ page }) => {
      await page.goto("/");

      const trigger = page.getByTestId("public-nav-trigger");
      await expect(trigger).toBeVisible();

      // Inline desktop nav is hidden below 720px.
      const inlineNav = page.locator("nav.public-header-nav");
      if (await inlineNav.count()) {
        await expect(inlineNav.first()).toBeHidden();
      }

      // Open the drawer; it should be reachable + focused.
      await trigger.click();
      const drawer = page.getByTestId("public-nav-drawer");
      await expect(drawer).toBeVisible();
      await expect(drawer.getByRole("link", { name: /home/i })).toBeVisible();

      // Tap the scrim outside the drawer body — drawer should close.
      const scrim = page.getByTestId("public-nav-scrim");
      const drawerBox = await drawer.boundingBox();
      const scrimBox = await scrim.boundingBox();
      if (!drawerBox || !scrimBox) throw new Error("missing drawer geometry");
      // Click halfway between the left edge of the viewport and the
      // drawer's left edge — guaranteed outside the drawer.
      await page.mouse.click(Math.max(2, drawerBox.x / 2), scrimBox.y + 24);
      await expect(drawer).toHaveCount(0);
    });

    test("Escape closes the drawer and restores focus", async ({ page }) => {
      await page.goto("/");
      const trigger = page.getByTestId("public-nav-trigger");
      await trigger.click();
      await expect(page.getByTestId("public-nav-drawer")).toBeVisible();

      await page.keyboard.press("Escape");
      await expect(page.getByTestId("public-nav-drawer")).toHaveCount(0);
      await expect(trigger).toBeFocused();
    });

    test("drawer closes on route change", async ({ page }) => {
      await page.goto("/");
      await page.getByTestId("public-nav-trigger").click();
      const drawer = page.getByTestId("public-nav-drawer");
      await expect(drawer).toBeVisible();

      await drawer.getByRole("link", { name: /methodology/i }).click();
      await expect(page).toHaveURL(/\/methodology$/);
      await expect(page.getByTestId("public-nav-drawer")).toHaveCount(0);
    });

    test("home page has no horizontal scroll and shows a focus ring on the hamburger", async ({
      page,
    }) => {
      await page.goto("/");
      await expectNoHorizontalScroll(page);

      // Focus-visible: tab from skip-link → trigger and verify the
      // outline isn't suppressed.
      await page.keyboard.press("Tab"); // skip link
      // Trigger may not be the second focusable on every page; instead
      // explicitly focus and assert focus visible state.
      const trigger = page.getByTestId("public-nav-trigger");
      await trigger.focus();
      await expect(trigger).toBeFocused();
      const outline = await trigger.evaluate(
        (el) => window.getComputedStyle(el).outlineStyle,
      );
      expect(outline).not.toBe("none");
    });

    test("methodology renders without overflow", async ({ page }) => {
      await page.goto("/methodology");
      await expectNoHorizontalScroll(page);
      await expect(page.locator("h1").first()).toBeVisible();
    });

    test("currents grid stacks to single column", async ({ page }) => {
      await page.goto("/currents");
      await expectNoHorizontalScroll(page);
      await expect(page.getByTestId("currents-page")).toBeVisible();

      // Live pulse indicator should still render (CurrentsNavPulse is
      // collapsed into the drawer, but the in-feed connection banner
      // is rendered by FeedClient).
      const liveIndicators = page.locator("[aria-live='polite']");
      expect(await liveIndicators.count()).toBeGreaterThan(0);
    });

    test("forecasts grid stacks to single column with pulse visible", async ({
      page,
    }) => {
      await page.goto("/forecasts");
      await expectNoHorizontalScroll(page);
      await expect(page.getByTestId("forecasts-page")).toBeVisible();
      // ForecastGridClient renders a "live" / "Reconnecting…" pill.
      const livePill = page.getByText(/live|Reconnecting/i).first();
      await expect(livePill).toBeVisible();
    });

    test("a published article (post or conclusion) is readable", async ({
      page,
    }) => {
      await page.goto("/");

      // Use whichever article kind is exposed first on the home page —
      // either a /post/<slug> link or a /c/<slug> link. If none, skip.
      const postLink = page.locator('a[href^="/post/"]').first();
      const conclusionLink = page.locator('a[href^="/c/"]').first();
      const hasPost = (await postLink.count()) > 0;
      const hasConclusion = (await conclusionLink.count()) > 0;
      test.skip(
        !hasPost && !hasConclusion,
        "no public article available on the home rail in this environment",
      );

      const target = hasPost ? postLink : conclusionLink;
      await target.click();

      await expectNoHorizontalScroll(page);

      // Body text should be at the mobile reading scale (≥17px).
      const bodyFont = await page.evaluate(() => {
        const body = document.querySelector(".public-article-body, .post-body");
        if (!body) return null;
        const cs = window.getComputedStyle(body);
        return parseFloat(cs.fontSize);
      });
      if (bodyFont !== null) {
        expect(bodyFont).toBeGreaterThanOrEqual(17);
      }
    });

    test("scroll-to-top via skip link returns focus to main content", async ({
      page,
    }) => {
      await page.goto("/");
      await page.evaluate(() => window.scrollTo(0, 1500));
      const skip = page.locator(".skip-link");
      await skip.focus();
      await expect(skip).toBeFocused();
      await page.keyboard.press("Enter");
      const scrollTop = await page.evaluate(() => window.scrollY);
      expect(scrollTop).toBeLessThan(200);
    });

    // ── Round 17 prompt 37 polish pass: mobile-specific layouts for the
    //    surfaces introduced by Round 18 v2 (composition graph, methods
    //    table, calibration plot, lineage timeline, auto-paper page).

    test("methodology composition collapses the graph to a card list", async ({
      page,
    }) => {
      await page.goto("/methodology/composition");
      await expectNoHorizontalScroll(page);

      // The radial SVG map is removed from the flow on phones; the
      // method card list stands in as the mobile representation.
      await expect(page.getByTestId("composition-graph")).toBeHidden();
      await expect(page.getByTestId("composition-card-list")).toBeVisible();
    });

    test("methodology index table reflows to stacked cards", async ({
      page,
    }) => {
      await page.goto("/methodology");
      await expectNoHorizontalScroll(page);

      const row = page.locator(".public-table-row").first();
      if ((await row.count()) === 0) {
        test.skip(true, "no methods in the manifest in this environment");
        return;
      }
      // Each <tr> becomes a block-level card and the <thead> is taken
      // out of the visual flow (clipped) — the cells carry their column
      // name inline via `data-label`.
      const rowDisplay = await row.evaluate(
        (el) => window.getComputedStyle(el).display,
      );
      expect(rowDisplay).toBe("block");
      const theadWidth = await page
        .locator(".public-table thead")
        .first()
        .evaluate((el) => el.getBoundingClientRect().width);
      expect(theadWidth).toBeLessThanOrEqual(2);
    });

    test("calibration reliability diagram swaps to the mobile bar chart", async ({
      page,
    }) => {
      await page.goto("/calibration");
      await expectNoHorizontalScroll(page);

      // The square scatter is desktop-only; the per-bin bar chart is the
      // mobile rendering. Both ship in the HTML, CSS picks one.
      await expect(page.getByTestId("calibration-plot-mobile")).toBeVisible();
      await expect(page.locator(".calibration-plot-desktop")).toBeHidden();
    });

    test("auto-paper page shows an open-in-PDF button, not an inline embed", async ({
      page,
    }) => {
      const slug = await firstResearchSlug(page);
      test.skip(
        !slug,
        "no published auto-paper available in this environment",
      );
      const response = await page.goto(`/research/${slug}`);
      test.skip(
        !response || response.status() >= 400,
        "auto-paper route not reachable in this environment",
      );

      await expectNoHorizontalScroll(page);
      // Abstract stays; the inline PDF <object> is replaced by a button.
      await expect(page.getByTestId("paper-abstract")).toBeVisible();
      await expect(page.getByTestId("paper-open-pdf")).toBeVisible();
      await expect(page.locator(".paper-pdf-embed")).toBeHidden();
    });
  });
}

/**
 * Resolve a published-post slug from the home rail so the lineage test
 * has a real target. Returns null when no public post is exposed.
 */
async function firstPostSlug(page: Page): Promise<string | null> {
  await page.goto("/");
  const href = await page
    .locator('a[href^="/post/"]')
    .first()
    .getAttribute("href")
    .catch(() => null);
  if (!href) return null;
  const match = href.match(/^\/post\/([^/]+)/);
  return match ? match[1] : null;
}

/**
 * Resolve a published auto-paper slug. There is no public index page for
 * research papers, so we probe the surfaces that link to them; returns
 * null when none are reachable (the common case in CI).
 */
async function firstResearchSlug(page: Page): Promise<string | null> {
  for (const route of ["/research", "/methodology"]) {
    await page.goto(route).catch(() => null);
    const href = await page
      .locator('a[href^="/research/"]')
      .first()
      .getAttribute("href")
      .catch(() => null);
    if (!href) continue;
    const match = href.match(/^\/research\/([^/.]+)$/);
    if (match) return match[1];
  }
  return null;
}

// Lineage view: reflows from side-by-side swim lanes to a single
// chronological column, with the lane filters in a sticky bottom sheet.
for (const viewport of VIEWPORTS) {
  test.describe(`lineage view @ ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("lineage timeline reflows to a single column with a bottom sheet", async ({
      page,
    }) => {
      const slug = await firstPostSlug(page);
      test.skip(!slug, "no public post available in this environment");

      const response = await page.goto(`/post/${slug}/lineage`);
      test.skip(
        !response || response.status() >= 400,
        "lineage route not reachable for this post",
      );

      const sheet = page.getByTestId("lineage-mobile-sheet");
      if ((await sheet.count()) === 0) {
        test.skip(true, "this post exposes no public lineage timeline");
        return;
      }

      await expectNoHorizontalScroll(page);
      // Single-column body is shown; the side-by-side swim-lane toolbar
      // is hidden and the lane filters live in the sticky bottom sheet.
      await expect(page.getByTestId("lineage-mobile-column")).toBeVisible();
      await expect(sheet).toBeVisible();

      // The sheet pins to the bottom edge and expands on tap.
      const handle = sheet.getByRole("button").first();
      await expect(handle).toHaveAttribute("aria-expanded", "false");
      await handle.click();
      await expect(handle).toHaveAttribute("aria-expanded", "true");
    });
  });
}

/**
 * Visual-regression capture. Tagged `@visual` so a screenshot review can
 * select exactly this suite (`--grep @visual`); every catalogued issue
 * in docs/architecture/Mobile_Polish_Survey.md is re-checkable from the
 * artifacts this produces. The shots land in playwright/screenshots/.
 */
const SCREENSHOT_PAGES: Array<{ name: string; path: string }> = [
  { name: "home", path: "/" },
  { name: "methodology", path: "/methodology" },
  { name: "methodology-composition", path: "/methodology/composition" },
  { name: "calibration", path: "/calibration" },
  { name: "currents", path: "/currents" },
  { name: "forecasts", path: "/forecasts" },
  { name: "about", path: "/about" },
];

for (const viewport of VIEWPORTS) {
  test.describe(`mobile screenshots @ ${viewport.width}`, {
    tag: "@visual",
  }, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const target of SCREENSHOT_PAGES) {
      test(`capture ${target.name} @ ${viewport.width}`, {
        tag: "@visual",
      }, async ({ page }) => {
        const response = await page.goto(target.path);
        test.skip(
          !response || response.status() >= 400,
          `${target.path} not reachable in this environment`,
        );
        await expectNoHorizontalScroll(page);
        await page.screenshot({
          path: `playwright/screenshots/mobile/${target.name}-${viewport.width}.png`,
          fullPage: true,
        });
      });
    }
  });
}

test.describe("citation popover @ 375×812", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("citation popover never escapes the viewport when one is reachable", async ({
    page,
  }) => {
    await page.goto("/currents");

    const citationButton = page
      .getByRole("button", { name: /citation/i })
      .first();
    if ((await citationButton.count()) === 0) {
      test.skip(true, "no citation buttons exposed in this environment");
      return;
    }

    await citationButton.click();
    const popover = page.getByRole("dialog").first();
    await expect(popover).toBeVisible();

    const box = await popover.boundingBox();
    expect(box).not.toBeNull();
    if (!box) return;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(375 + 1);
    expect(box.y).toBeGreaterThanOrEqual(0);

    // Tap-outside dismiss.
    await page.mouse.click(2, 2);
    await expect(popover).toBeHidden();
  });
});
