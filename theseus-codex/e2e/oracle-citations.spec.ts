import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("Oracle conclusion citation opens the conclusion detail page in a new tab", async ({
  page,
}) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded founder credentials are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const noosphereId = `e2e-oracle-citation-${Date.now()}`;
  const conclusionText = `E2E Oracle citation fixture ${noosphereId}: base-rate neglect must be surfaced in every underwriting review.`;

  try {
    const org = await db.organization.findUnique({ where: { slug: founderOrg } });
    expect(org).toBeTruthy();
    const founder = await db.founder.findFirst({
      where: { organizationId: org!.id, email: founderEmail! },
    });
    expect(founder).toBeTruthy();

    const conclusion = await db.conclusion.create({
      data: {
        organizationId: org!.id,
        noosphereId,
        text: conclusionText,
        confidenceTier: "firm",
        rationale: "E2E Oracle citation deep-link fixture.",
        supportingPrincipleIds: "[]",
        evidenceChainClaimIds: "[]",
        dissentClaimIds: "[]",
        confidence: 0.91,
        topicHint: "e2e",
        attributedFounderId: founder!.id,
      },
    });
    const token = `[C:${conclusion.id.slice(0, 8)}]`;

    await page.route("**/api/ask", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        status: 200,
        body: JSON.stringify({
          question: "What does the firm believe about base-rate neglect?",
          answer: `The firm treats base-rate neglect as a first-class underwriting failure mode ${token}.`,
          model: "fixture-oracle",
          conclusionsInContext: 1,
          uploadsInContext: 0,
          uploadChunksInContext: 0,
          inputTokens: 0,
          outputTokens: 0,
          sources: [
            {
              type: "conclusion",
              id: conclusion.id,
              label: "firm",
              tier: "firm",
              topic: "e2e",
              text: conclusionText,
              url: `/conclusions/${conclusion.id}`,
            },
          ],
          citations: {
            [token]: {
              type: "conclusion",
              id: conclusion.id,
              tier: "firm",
              url: `/conclusions/${conclusion.id}`,
              preview: conclusionText,
            },
          },
          citationsResolved: 1,
          citationsUnresolved: 0,
        }),
      });
    });

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await page.goto("/ask");
    await page.getByPlaceholder(/base-rate neglect/i).fill("What does the firm believe about base-rate neglect?");
    await page.getByRole("button", { name: /ask the codex/i }).click();

    const citation = page.getByRole("link", { name: token });
    await expect(citation).toBeVisible();

    const popupPromise = page.waitForEvent("popup");
    await citation.click();
    const popup = await popupPromise;
    await popup.waitForLoadState("domcontentloaded");
    await expect(popup).toHaveURL(new RegExp(`/conclusions/${conclusion.id}(?:\\?|$)`));
    await expect(popup.getByText(conclusionText)).toBeVisible();
  } finally {
    await db.conclusion.deleteMany({ where: { noosphereId } });
    await db.$disconnect();
  }
});
