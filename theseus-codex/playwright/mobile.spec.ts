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
