import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  PublicBet,
  PublicForecast,
  PublicForecastSource,
  PublicMarket,
} from "@/lib/forecastsTypes";

const mocks = vi.hoisted(() => ({
  getForecast: vi.fn(),
  getForecastBets: vi.fn(),
  getForecastResolution: vi.fn(),
  getForecastSources: vi.fn(),
  getFounder: vi.fn(),
  getMarket: vi.fn(),
  getPortfolioCalibration: vi.fn(),
}));

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

vi.mock("next/navigation", () => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)} data-testid="public-header">
      Public header
    </header>
  ),
}));

vi.mock("@/components/PublishToToolbar", () => ({
  default: () => <div>PublishToToolbar sentinel</div>,
}));

vi.mock("@/lib/auth", () => ({
  getFounder: mocks.getFounder,
}));

vi.mock("@/lib/forecastsApi", () => ({
  getForecast: mocks.getForecast,
  getForecastBets: mocks.getForecastBets,
  getForecastResolution: mocks.getForecastResolution,
  getForecastSources: mocks.getForecastSources,
  getMarket: mocks.getMarket,
  getPortfolioCalibration: mocks.getPortfolioCalibration,
}));

vi.mock("@/app/forecasts/[id]/AuditTrail", () => ({
  default: () => <aside>AuditTrail sentinel</aside>,
}));

vi.mock("@/app/forecasts/[id]/ChatPanel", () => ({
  default: ({ predictionId }: { predictionId: string }) => (
    <section aria-label="Forecast follow-up">Forecast chat {predictionId}</section>
  ),
}));

vi.mock("@/app/forecasts/[id]/CopyPermalink", () => ({
  CopyPermalink: ({ forecastId }: { forecastId: string }) => (
    <button type="button">Copy {forecastId}</button>
  ),
}));

vi.mock("@/app/forecasts/[id]/SourceDrawer", () => ({
  ForecastEvidencePanel: () => (
    <section aria-label="Forecast reasoning and citations">
      Forecast evidence panel
    </section>
  ),
}));

import ForecastsLayout from "@/app/forecasts/layout";
import ForecastDetailPage from "@/app/forecasts/[id]/page";

const NOW = "2026-04-30T12:00:00.000Z";

function market(overrides: Partial<PublicMarket> = {}): PublicMarket {
  return {
    id: "market-1",
    organization_id: "org-1",
    source: "POLYMARKET",
    external_id: "poly-1",
    title: "Will the fixture resolve YES?",
    description: "Fixture market.",
    resolution_criteria: "Resolves YES if the fixture passes.",
    category: "policy",
    current_yes_price: 0.58,
    current_no_price: 0.42,
    volume: 120000,
    open_time: NOW,
    close_time: "2026-05-30T12:00:00.000Z",
    resolved_at: null,
    resolved_outcome: null,
    raw_payload: {},
    status: "OPEN",
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function forecast(overrides: Partial<PublicForecast> = {}): PublicForecast {
  return {
    id: "forecast-1",
    market_id: "market-1",
    organization_id: "org-1",
    probability_yes: 0.64,
    confidence_low: 0.55,
    confidence_high: 0.73,
    headline: "Fixture forecast headline",
    reasoning: "The cited source base supports a higher probability.",
    status: "PUBLISHED",
    abstention_reason: null,
    topic_hint: "policy",
    model_name: "fixture-model",
    live_authorized_at: null,
    created_at: NOW,
    updated_at: NOW,
    revoked_sources_count: 0,
    market: market(),
    citations: [
      {
        id: "citation-1",
        prediction_id: "forecast-1",
        source_type: "CONCLUSION",
        source_id: "source-1",
        quoted_span: "higher probability",
        support_label: "DIRECT",
        retrieval_score: 0.91,
        is_revoked: false,
      },
    ],
    resolution: null,
    ...overrides,
  };
}

function source(overrides: Partial<PublicForecastSource> = {}): PublicForecastSource {
  return {
    id: "source-row-1",
    prediction_id: "forecast-1",
    source_type: "CONCLUSION",
    source_id: "source-1",
    source_text: "Fixture source text supports the public detail path.",
    quoted_span: "supports the public detail path",
    support_label: "DIRECT",
    retrieval_score: 0.91,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: "/c/source-1",
    ...overrides,
  };
}

function bet(overrides: Partial<PublicBet> = {}): PublicBet {
  return {
    id: "bet-1",
    prediction_id: "forecast-1",
    mode: "PAPER",
    exchange: "POLYMARKET",
    side: "YES",
    stake_usd: 100,
    entry_price: 0.61,
    exit_price: null,
    status: "OPEN",
    settlement_pnl_usd: null,
    created_at: NOW,
    settled_at: null,
    ...overrides,
  };
}

async function renderChrome() {
  const detail = await ForecastDetailPage({
    params: Promise.resolve({ id: "forecast-1" }),
  });
  const element = await ForecastsLayout({ children: detail });
  return renderToStaticMarkup(element);
}

describe("Forecasts detail chrome", () => {
  beforeEach(() => {
    mocks.getForecast.mockReset();
    mocks.getForecastBets.mockReset();
    mocks.getForecastResolution.mockReset();
    mocks.getForecastSources.mockReset();
    mocks.getFounder.mockReset();
    mocks.getMarket.mockReset();
    mocks.getPortfolioCalibration.mockReset();

    mocks.getFounder.mockResolvedValue(null);
    mocks.getForecast.mockResolvedValue(forecast());
    mocks.getMarket.mockResolvedValue(market());
    mocks.getForecastSources.mockResolvedValue([source()]);
    mocks.getForecastResolution.mockRejectedValue(
      new Error("Forecasts API 404: not resolved"),
    );
    mocks.getForecastBets.mockResolvedValue([bet()]);
    mocks.getPortfolioCalibration.mockResolvedValue({ items: [] });
  });

  it("renders the public header and Forecasts back link", async () => {
    const html = await renderChrome();

    expect(html).toContain('data-testid="public-header"');
    expect(html).toContain('href="/forecasts"');
    expect(html).toContain("← Forecasts");
    expect(html).toContain('aria-label="Back to Forecasts"');
  });

  it("does not mount public AuditTrail or PublishToToolbar chrome", async () => {
    const html = await renderChrome();

    expect(html).not.toContain("AuditTrail sentinel");
    expect(html).not.toContain("Retrieval audit");
    expect(html).not.toContain("PublishToToolbar sentinel");
    expect(html).not.toContain("Publish to");
  });
});
