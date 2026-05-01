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
          marketTitle: "Fixture market: Harvard rank in four years",
          marketUrl: "https://polymarket.com/event/fixture",
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
  });
});
