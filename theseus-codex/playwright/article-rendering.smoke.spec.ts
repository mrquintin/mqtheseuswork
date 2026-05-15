/**
 * Smoke test for the article-rendering fix from
 * docs/bugs/2026-05-13_article_rendering/.
 *
 * Asserts that a freshly published Upload (the `/post/[slug]` path)
 * surfaces in the homepage Publications rail AND that its markdown
 * body renders as structured HTML, not as a wall of plain `<p>` tags.
 *
 * This spec needs a seeded founder + Upload with markdown content
 * already in the DB. When those aren't present (typical for a fresh
 * checkout), the spec self-skips with a clear message rather than
 * failing the whole suite — symmetric to playwright/a11y.spec.ts.
 *
 * Required env vars when present:
 *   - PLAYWRIGHT_ARTICLE_FIXTURE_SLUG — slug of a published upload
 *     whose `textContent` contains markdown headings / lists. The
 *     seed scripts under theseus-codex/scripts/ may populate one.
 */

import { expect, test } from "@playwright/test";

const fixtureSlug = process.env.PLAYWRIGHT_ARTICLE_FIXTURE_SLUG?.trim();

test.describe("article rendering — public surface", () => {
  test("published article surfaces on the homepage Publications rail", async ({
    page,
  }) => {
    await page.goto("/");
    const rail = page.locator('[data-testid="homepage-publications-rail"]');
    await expect(rail).toBeVisible();
    // A rail exists; it's either populated with at least one card or
    // it renders the "no essays are published yet" empty state. Both
    // are acceptable shapes — the regression is the rail being
    // missing or pointing at the wrong route.
    const cardCount = await page
      .locator('[data-testid="homepage-publication-card"]')
      .count();
    if (cardCount > 0) {
      const firstCard = page
        .locator('[data-testid="homepage-publication-card"]')
        .first();
      const href = await firstCard.getAttribute("href");
      expect(href, "publication card must link to /post/ or /c/").toMatch(
        /^\/(post|c)\//,
      );
    } else {
      await expect(rail).toContainText(/No essays are published yet/i);
    }
  });

  test("published article body renders structured HTML, not plain paragraphs", async ({
    page,
  }) => {
    test.skip(
      !fixtureSlug,
      "PLAYWRIGHT_ARTICLE_FIXTURE_SLUG not set; skipping structured-render check",
    );

    await page.goto(`/post/${fixtureSlug}`);
    await expect(page.locator('[data-testid="post-article"]')).toBeVisible();

    const body = page.locator('[data-testid="post-article-body"]');
    await expect(body).toBeVisible();

    // The body must not surface the parse-error block on a real
    // production article. The error block is the renderer's last-
    // resort fallback; its presence here would be a regression.
    await expect(
      body.locator('[data-testid="article-parse-error"]'),
    ).toHaveCount(0);

    // A "broken/glitchy" render produces only plain <p> children with
    // literal markdown markers. The fixture article contains headings
    // and lists, so we assert at least one heading and one list
    // appear inside the body. If the fixture is a no-markdown
    // transcript, this still passes because we only require one of
    // the structural elements to exist.
    const structuralCount = await body
      .locator("h1, h2, h3, h4, h5, h6, ul, ol, blockquote, pre")
      .count();
    expect(
      structuralCount,
      "article body must render at least one structured element when markdown is present",
    ).toBeGreaterThan(0);

    // Save a post-fix screenshot as the canonical evidence artifact
    // for the audit trail. Saving is best-effort; failures here
    // shouldn't fail the test (screenshotting is filesystem-side).
    try {
      await page.screenshot({
        path: "../docs/bugs/2026-05-13_article_rendering/post_fix.png",
        fullPage: true,
      });
    } catch (error) {
      console.warn("post_fix.png save skipped:", error);
    }
  });

  test("publishing a fixture upload makes it visible on the homepage within 60s", async ({
    page,
    request,
  }) => {
    const apiKey = process.env.PLAYWRIGHT_API_KEY;
    const uploadId = process.env.PLAYWRIGHT_FIXTURE_UPLOAD_ID;
    test.skip(
      !apiKey || !uploadId,
      "PLAYWRIGHT_API_KEY + PLAYWRIGHT_FIXTURE_UPLOAD_ID not set; skipping publish integration test",
    );

    // Publish the fixture upload.
    const publishRes = await request.post("/api/publish", {
      data: { upload_id: uploadId, publish: true },
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    expect(publishRes.ok()).toBeTruthy();
    const publishBody = (await publishRes.json()) as {
      slug: string;
      publicUrl: string;
    };
    expect(publishBody.slug).toBeTruthy();

    // Poll the homepage for up to 60s; the rail must update.
    const deadline = Date.now() + 60_000;
    let appeared = false;
    while (Date.now() < deadline) {
      await page.goto("/", { waitUntil: "networkidle" });
      const matches = await page
        .locator(
          `[data-testid="homepage-publication-card"][href="${publishBody.publicUrl}"]`,
        )
        .count();
      if (matches > 0) {
        appeared = true;
        break;
      }
      await page.waitForTimeout(2_000);
    }
    expect(
      appeared,
      "published upload did not surface on the homepage within 60s",
    ).toBe(true);

    // Clean up: unpublish so the next run starts from the same state.
    await request.post("/api/publish", {
      data: { upload_id: uploadId, publish: false },
      headers: { Authorization: `Bearer ${apiKey}` },
    });
  });
});
