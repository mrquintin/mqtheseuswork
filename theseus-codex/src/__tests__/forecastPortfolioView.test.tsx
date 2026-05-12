import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import ForecastPortfolioView from "@/app/(authed)/forecasts/portfolio/ForecastPortfolioView";
import type { ForecastPortfolioSurface } from "@/lib/forecastPortfolioData";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("ForecastPortfolioView", () => {
  it("renders the principles-to-bet trace and gate state", () => {
    const surface: ForecastPortfolioSurface = {
      kpis: {
        hitRate: 1,
        openPositions: 1,
        realizedPaperPnl: 12.5,
        runningBrier: 0.18,
        unrealizedPaperPnl: 3.2,
      },
      mode: {
        failedGates: [],
        liveTradingEnabled: false,
        mode: "PAPER",
      },
      openPositions: [
        {
          avgPrice: 0.42,
          betId: "bet_fixture",
          currentImpliedProb: 0.51,
          decisionTrace: {
            action: "PAPER_TRADE",
            analogicalTransfer: null,
            confidence: 0.71,
            edge: 0.17,
            firmProbabilityYes: 0.62,
            frames: [],
            synthesis: null,
            marketYesPrice: 0.45,
            metrics: [
              {
                detail: "firm_p=0.6200 market_p=0.4500",
                lowConfidence: false,
                method: "edge_calc@v1",
                name: "market_mispricing_edge",
                rangeHigh: 1,
                rangeLow: -1,
                value: 0.17,
              },
            ],
            rationale: "Compounding feedback supports the YES side here.",
            reasons: ["|edge|=0.170 clears paper, below live threshold 0.08"],
            rules: [
              {
                detail: "open",
                fired: true,
                kind: "veto",
                name: "market_open",
                passed: true,
              },
              {
                detail: "|edge|=0.170 clears paper",
                fired: true,
                kind: "bucket",
                name: "edge_bucket",
                passed: true,
              },
            ],
            side: "YES",
            stakeRecommendationUsd: 25,
            traceVersion: "decision_metrics@v1",
          },
          drivingPrinciples: [
            {
              conclusionId: "conclusion_fixture_123456",
              snippet: "durable education depends on compounding feedback",
              weight: 0.91,
            },
          ],
          gateResults: [
            {
              gateName: "paper_edge_threshold",
              passed: true,
              reason: "paper fill recorded",
            },
          ],
          lastUpdated: new Date("2026-05-01T12:00:00Z"),
          marketTitle: "Fixture market: Harvard rank in four years",
          marketUrl: "https://polymarket.com/event/fixture",
          mode: "PAPER",
          predictionId: "prediction_fixture",
          side: "YES",
          sizeUsd: 25,
        },
      ],
      pipeline: [
        {
          category: "education",
          decisionTrace: null,
          drivingPrinciples: [
            {
              conclusionId: "conclusion_fixture_123456",
              snippet: "durable education depends on compounding feedback",
              weight: 0.91,
            },
          ],
          gateResults: [
            {
              gateName: "concentration_cap",
              passed: false,
              reason: "would exceed category exposure",
            },
          ],
          gateState: "would fail concentration_cap: would exceed category exposure",
          lastUpdated: new Date("2026-05-01T12:00:00Z"),
          marketId: "market_fixture",
          marketNoPrice: 0.55,
          marketTitle: "Fixture market: Harvard rank in four years",
          marketUrl: "https://polymarket.com/event/fixture",
          marketYesPrice: 0.45,
          predictionId: "prediction_fixture",
          source: "POLYMARKET",
        },
      ],
      recentlyResolved: [],
      watching: {
        kalshiCategories: ["education"],
        polymarketCategories: ["education"],
        scannedThisWeek: 4,
        watchedMarkets: [],
      },
    };

    const html = renderToStaticMarkup(<ForecastPortfolioView surface={surface} />);

    expect(html).toContain("PAPER");
    expect(html).toContain("Fixture market: Harvard rank in four years");
    expect(html).toContain("[C:conclusi]");
    expect(html).toContain("/conclusions/conclusion_fixture_123456");
    expect(html).toContain("would fail concentration_cap");
    expect(html).toContain("PAPER_TRADE");
    expect(html).toContain("market_mispricing_edge");
    expect(html).toContain("Setup and readiness");
  });
});
