import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";

import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword = process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("forecast portfolio shows a fixture paper position and deep-links its principle chip", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded founder credentials are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const suffix = `${Date.now()}`;
  const externalId = `forecast-e2e-${suffix}`;
  let conclusionId = "";

  try {
    const org = await db.organization.findUnique({ where: { slug: founderOrg } });
    expect(org).toBeTruthy();
    const founder = await db.founder.findFirst({
      where: { organizationId: org!.id, email: founderEmail! },
    });
    expect(founder).toBeTruthy();

    const conclusion = await db.conclusion.create({
      data: {
        attributedFounderId: founder!.id,
        confidence: 0.9,
        confidenceTier: "firm",
        dissentClaimIds: "[]",
        evidenceChainClaimIds: "[]",
        noosphereId: externalId,
        normalizedText: externalId,
        organizationId: org!.id,
        rationale: "Forecast portfolio E2E fixture.",
        supportingPrincipleIds: "[]",
        text: `Forecast portfolio fixture principle ${externalId}: durable education outcomes compound through feedback loops.`,
        topicHint: "forecast-e2e",
      },
    });
    conclusionId = conclusion.id;

    const market = await db.forecastMarket.create({
      data: {
        category: "education",
        currentNoPrice: "0.550000",
        currentYesPrice: "0.450000",
        externalId,
        organizationId: org!.id,
        rawPayload: { url: `https://polymarket.com/event/${externalId}` },
        source: "POLYMARKET",
        status: "OPEN",
        title: `Forecast portfolio fixture market ${externalId}`,
      },
    });
    const prediction = await db.forecastPrediction.create({
      data: {
        confidenceHigh: "0.690000",
        confidenceLow: "0.540000",
        headline: "Fixture forecast favors yes",
        marketId: market.id,
        modelName: "fixture-model",
        organizationId: org!.id,
        probabilityYes: "0.620000",
        reasoning: `Fixture reasoning cites ${conclusion.id}.`,
        status: "PUBLISHED",
        topicHint: "education",
      },
    });
    await db.forecastTrace.create({
      data: {
        gateResults: [
          { gateName: "paper_edge_threshold", passed: true, reason: "paper fill recorded" },
        ],
        marketId: market.id,
        marketTitle: market.title,
        modelOutput: {
          confidence: 0.85,
          edge: 0.17,
          rationale: prediction.headline,
          side: "YES",
        },
        organizationId: org!.id,
        predictionId: prediction.id,
        principlesUsed: [
          {
            conclusionId: conclusion.id,
            snippet: "durable education outcomes compound",
            weight: 0.94,
          },
        ],
      },
    });
    await db.forecastBet.create({
      data: {
        entryPrice: "0.450000",
        exchange: "POLYMARKET",
        mode: "PAPER",
        organizationId: org!.id,
        predictionId: prediction.id,
        side: "YES",
        stakeUsd: "25.00",
        status: "FILLED",
      },
    });

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await page.goto("/forecasts/portfolio");
    await expect(page.getByTestId("forecast-mode-banner")).toContainText("PAPER");
    await expect(page.getByText(market.title)).toBeVisible();

    await page.getByRole("link", { name: `[C:${conclusion.id.slice(0, 8)}]` }).click();
    await expect(page).toHaveURL(new RegExp(`/conclusions/${conclusion.id}(?:\\?|$)`));
  } finally {
    if (conclusionId) {
      await db.forecastBet.deleteMany({
        where: { prediction: { market: { externalId } } },
      });
      await db.forecastTrace.deleteMany({
        where: { prediction: { market: { externalId } } },
      });
      await db.forecastPrediction.deleteMany({
        where: { market: { externalId } },
      });
      await db.forecastMarket.deleteMany({ where: { externalId } });
      await db.conclusion.deleteMany({ where: { id: conclusionId } });
    }
    await db.$disconnect();
  }
});
