import { describe, expect, it, vi } from "vitest";

import { getForecast, getMarket, getPortfolioSummary } from "@/lib/forecastsApi";
import type { PortfolioSummary, PublicForecast, PublicMarket } from "@/lib/forecastsTypes";

vi.mock("@/lib/forecastsApi", () => ({
  getForecast: vi.fn(),
  getMarket: vi.fn(),
  getPortfolioSummary: vi.fn(),
}));

const NOW = "2026-04-30T12:00:00.000Z";

function market(): PublicMarket {
  return {
    id: "market-og",
    organization_id: "org-1",
    source: "POLYMARKET",
    external_id: "poly-og",
    title: "Will the policy bill pass?",
    description: null,
    resolution_criteria: null,
    category: "policy",
    current_yes_price: 0.58,
    current_no_price: 0.42,
    volume: null,
    open_time: NOW,
    close_time: "2026-05-11T12:00:00.000Z",
    resolved_at: null,
    resolved_outcome: null,
    raw_payload: {},
    status: "OPEN",
    created_at: NOW,
    updated_at: NOW,
  };
}

function forecast(): PublicForecast {
  return {
    id: "forecast-og",
    market_id: "market-og",
    organization_id: "org-1",
    probability_yes: 0.64,
    confidence_low: 0.54,
    confidence_high: 0.74,
    headline: "Sources imply passage is more likely than market pricing",
    reasoning: "The cited source base supports a higher probability.",
    status: "PUBLISHED",
    abstention_reason: null,
    topic_hint: "policy",
    model_name: "fixture",
    live_authorized_at: null,
    created_at: NOW,
    updated_at: NOW,
    revoked_sources_count: 0,
    market: null,
    citations: [],
    resolution: null,
  };
}

function summary(): PortfolioSummary {
  return {
    organization_id: "org-1",
    paper_balance_usd: 10000,
    paper_pnl_curve: [],
    calibration: [],
    mean_brier_90d: 0.173,
    total_bets: 0,
    kill_switch_engaged: false,
    kill_switch_reason: null,
    updated_at: NOW,
  };
}

describe("forecast OG image routes", () => {
  it("renders the Forecasts index OG image without throwing", async () => {
    vi.mocked(getPortfolioSummary).mockResolvedValueOnce(summary());
    const { GET } = await import("@/app/api/og/forecasts/route");

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("image/png");
  });

  it("renders a sample forecast OG card with probability, market price, and edge", async () => {
    vi.mocked(getForecast).mockResolvedValueOnce(forecast());
    vi.mocked(getMarket).mockResolvedValueOnce(market());
    const { GET } = await import("@/app/api/og/forecasts/[id]/route");

    const response = await GET(new Request("http://localhost/api/og/forecasts/forecast-og"), {
      params: Promise.resolve({ id: "forecast-og" }),
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("image/png");
  });
});
