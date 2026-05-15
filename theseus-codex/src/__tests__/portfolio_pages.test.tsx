import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

import OverviewTab from "@/components/portfolio/OverviewTab";
import EquitiesTab from "@/components/portfolio/EquitiesTab";
import DecisionTraceDrawer from "@/components/portfolio/DecisionTraceDrawer";
import type {
  DecisionTrace,
  EquitySurface,
  UnifiedOverview,
} from "@/components/portfolio/types";
import { appRedirects } from "../../next.config";

function makeOverview(overrides: Partial<UnifiedOverview> = {}): UnifiedOverview {
  return {
    organizationId: "org_test",
    netPaperPnlUsd: 125.5,
    netPaperPnlCurve: [
      { ts: "2026-04-01T00:00:00Z", paperBalanceUsd: 10000, paperPnlUsd: 50 },
      { ts: "2026-04-15T00:00:00Z", paperBalanceUsd: 10000, paperPnlUsd: 125.5 },
    ],
    forecasts: {
      openPositions: 2,
      realizedPaperPnlUsd: 80,
      unrealizedPaperPnlUsd: 0,
    },
    equities: {
      openPositions: 1,
      realizedPaperPnlUsd: 45.5,
      unrealizedPaperPnlUsd: 0,
    },
    killSwitchEngaged: false,
    killSwitchReason: null,
    liveStatus: { forecasts: "DISABLED", equities: "ENABLED-AWAITING-AUTH" },
    activePrinciples: [
      {
        conclusionId: "concl_abcdef12345",
        snippet: "Persistent edge beats spot accuracy",
        weight: 0.74,
        positionCount: 2,
      },
    ],
    ...overrides,
  };
}

function makeEquitySurface(
  overrides: Partial<EquitySurface> = {},
): EquitySurface {
  return {
    organizationId: "org_test",
    paperBalanceUsd: 10000,
    totals: {
      openPositions: 1,
      realizedPaperPnlUsd: 45.5,
      unrealizedPaperPnlUsd: 0,
    },
    liveStatus: { forecasts: "DISABLED", equities: "DISABLED" },
    killSwitchEngaged: false,
    killSwitchReason: null,
    openPositions: [
      {
        positionId: "pos_eq_1",
        signalId: "sig_eq_1",
        instrumentSymbol: "MSFT",
        instrumentName: "Microsoft Corp",
        side: "LONG",
        qty: 5,
        entryPrice: 350.12,
        entryAt: "2026-04-02T00:00:00Z",
        unrealizedPnlUsd: 12.5,
        horizonDays: 30,
        direction: "BULLISH",
        lastUpdated: "2026-04-02T00:00:00Z",
      },
    ],
    recentSignals: [
      {
        signalId: "sig_eq_1",
        instrumentSymbol: "MSFT",
        direction: "BULLISH",
        headline: "Re-rating on AI margin expansion",
        confidenceLow: 0.6,
        confidenceHigh: 0.8,
        targetPriceLow: 370,
        targetPriceHigh: 410,
        horizonDays: 30,
        status: "PUBLISHED",
        createdAt: "2026-04-01T00:00:00Z",
      },
    ],
    paperPnlCurve: [{ ts: "2026-04-15T00:00:00Z", paperPnlUsd: 45.5 }],
    targetPriceMape: [
      { horizonLabel: "≤ 7 days", n: 0, meanAbsolutePctError: null },
      { horizonLabel: "8–30 days", n: 2, meanAbsolutePctError: 0.06 },
      { horizonLabel: "31–90 days", n: 0, meanAbsolutePctError: null },
      { horizonLabel: "> 90 days", n: 0, meanAbsolutePctError: null },
    ],
    ...overrides,
  };
}

describe("OverviewTab", () => {
  it("renders aggregate counts and active principles when both tracks have data", () => {
    const html = renderToStaticMarkup(
      <OverviewTab
        binaryOutcomes={[
          { probabilityYes: 0.7, outcome: 1 },
          { probabilityYes: 0.7, outcome: 1 },
          { probabilityYes: 0.2, outcome: 0 },
        ]}
        directionalSamples={[
          { predicted: "BULLISH", actual: "UP" },
          { predicted: "BEARISH", actual: "UP" },
        ]}
        overview={makeOverview()}
      />,
    );
    expect(html).toContain("data-testid=\"overview-net-curve\"");
    expect(html).toContain("data-testid=\"overview-calibration-plot\"");
    expect(html).toContain("data-testid=\"overview-directional-plot\"");
    expect(html).toContain("data-testid=\"overview-position-counts\"");
    expect(html).toContain("Persistent edge beats spot accuracy");
    expect(html).toContain("href=\"/principles/concl_abcdef12345\"");
  });

  it("renders empty hint copy when a track has no rows", () => {
    const html = renderToStaticMarkup(
      <OverviewTab
        binaryOutcomes={[]}
        directionalSamples={[]}
        overview={makeOverview({
          forecasts: {
            openPositions: 0,
            realizedPaperPnlUsd: 0,
            unrealizedPaperPnlUsd: 0,
          },
          activePrinciples: [],
        })}
      />,
    );
    expect(html).toContain("No resolved binary forecasts yet");
    expect(html).toContain("No resolved equity signals yet");
    expect(html).toContain("No open positions yet");
  });
});

describe("EquitiesTab", () => {
  it("renders open positions, signals, and the MAPE chart with data", () => {
    const html = renderToStaticMarkup(
      <EquitiesTab surface={makeEquitySurface()} />,
    );
    expect(html).toContain("MSFT");
    expect(html).toContain("Re-rating on AI margin expansion");
    expect(html).toContain("8–30 days");
    expect(html).toContain("data-testid=\"equities-mape\"");
  });

  it("renders hint copy when the equity track has no rows yet", () => {
    const html = renderToStaticMarkup(
      <EquitiesTab
        surface={makeEquitySurface({
          openPositions: [],
          recentSignals: [],
          paperPnlCurve: [],
          targetPriceMape: [
            { horizonLabel: "≤ 7 days", n: 0, meanAbsolutePctError: null },
          ],
        })}
      />,
    );
    expect(html).toContain("No open equity positions");
    expect(html).toContain("No equity signals yet");
    expect(html).toContain("No closed equity positions yet");
    expect(html).toContain("No resolved signals with target prices yet");
  });
});

describe("DecisionTraceDrawer", () => {
  function forecastTrace(): DecisionTrace {
    return {
      kind: "forecast",
      positionId: "bet_forecast_1",
      marketOrInstrumentTitle: "Will SCOTUS rule by July?",
      principles: [
        {
          conclusionId: "concl_principle_1",
          snippet: "Term-end clustering on contested cases",
          weight: 0.82,
        },
      ],
      citations: [
        {
          sourceType: "CONCLUSION",
          sourceId: "concl_principle_1",
          quotedSpan: "term-end clustering on contested cases",
          supportLabel: "DIRECT",
        },
      ],
      signal: {
        id: "pred_1",
        headline: "Lean YES",
        directionOrSide: "YES",
        rationale: "Term-end pressure plus oral-argument signal.",
        confidenceLow: 0.6,
        confidenceHigh: 0.78,
      },
      position: {
        id: "bet_forecast_1",
        mode: "PAPER",
        side: "YES",
        size: 100,
        entryPrice: 0.62,
        status: "SETTLED",
        createdAt: "2026-04-01T00:00:00Z",
      },
      fill: {
        exitPrice: 1.0,
        exitAt: "2026-04-20T00:00:00Z",
        realizedPnlUsd: 61.29,
      },
      resolution: {
        outcome: "YES",
        resolvedAt: "2026-04-20T00:00:00Z",
        brierScore: 0.0144,
        justification: "Decision filed.",
      },
      gates: [],
    };
  }

  function equityTrace(): DecisionTrace {
    return {
      kind: "equity",
      positionId: "pos_eq_1",
      marketOrInstrumentTitle: "MSFT",
      principles: [],
      citations: [
        {
          sourceType: "TRANSCRIPT",
          sourceId: "msft_q3_call",
          quotedSpan: "AI margin expansion lifted gross margin",
          supportLabel: "DIRECT",
        },
      ],
      signal: {
        id: "sig_eq_1",
        headline: "Re-rating on AI margins",
        directionOrSide: "BULLISH",
        rationale: "Margin lift sustains.",
        confidenceLow: 0.6,
        confidenceHigh: 0.8,
      },
      position: {
        id: "pos_eq_1",
        mode: "PAPER",
        side: "LONG",
        size: 5,
        entryPrice: 350.12,
        status: "OPEN",
        createdAt: "2026-04-02T00:00:00Z",
      },
      fill: null,
      resolution: null,
      gates: [],
    };
  }

  it("round-trips a synthetic forecast trace", () => {
    const html = renderToStaticMarkup(
      <DecisionTraceDrawer onClose={() => undefined} trace={forecastTrace()} />,
    );
    expect(html).toContain("Will SCOTUS rule by July?");
    expect(html).toContain("Term-end clustering on contested cases");
    expect(html).toContain("data-testid=\"decision-trace-resolution\"");
    expect(html).toContain("outcome=YES");
  });

  it("round-trips a synthetic equity trace", () => {
    const html = renderToStaticMarkup(
      <DecisionTraceDrawer onClose={() => undefined} trace={equityTrace()} />,
    );
    expect(html).toContain("MSFT");
    expect(html).toContain("AI margin expansion lifted gross margin");
    expect(html).toContain("kind=equity");
  });
});

describe("Live pill copy", () => {
  it("renders all three pill states correctly from PortfolioShell header", async () => {
    const { default: PortfolioShell } = await import(
      "@/components/portfolio/PortfolioShell"
    );
    const overview = makeOverview({
      liveStatus: { forecasts: "ENABLED", equities: "ENABLED-AWAITING-AUTH" },
    });
    const html = renderToStaticMarkup(
      <PortfolioShell
        binaryOutcomes={[]}
        directionalSamples={[]}
        equitySurface={makeEquitySurface()}
        overview={overview}
        predictionMarketsContent={<div data-testid="pm-tab">pm</div>}
      />,
    );
    expect(html).toMatch(/Forecasts · ENABLED/);
    expect(html).toMatch(/Equities · ENABLED-AWAITING-AUTH/);
  });

  it("shows DISABLED when the env flag is off", async () => {
    const { default: PortfolioShell } = await import(
      "@/components/portfolio/PortfolioShell"
    );
    const overview = makeOverview({
      liveStatus: { forecasts: "DISABLED", equities: "DISABLED" },
    });
    const html = renderToStaticMarkup(
      <PortfolioShell
        binaryOutcomes={[]}
        directionalSamples={[]}
        equitySurface={makeEquitySurface()}
        overview={overview}
        predictionMarketsContent={<div data-testid="pm-tab">pm</div>}
      />,
    );
    expect(html).toMatch(/Forecasts · DISABLED/);
    expect(html).toMatch(/Equities · DISABLED/);
  });
});

describe("Legacy redirect", () => {
  it("301s (permanent) /forecasts/portfolio to /portfolio", () => {
    const entry = appRedirects.find(
      (row) => row.source === "/forecasts/portfolio",
    );
    expect(entry).toBeDefined();
    expect(entry?.destination).toBe("/portfolio");
    expect(entry?.permanent).toBe(true);
  });
});
