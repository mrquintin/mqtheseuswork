import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import ForecastCard from "@/app/forecasts/ForecastCard";
import type {
  PublicForecast,
  PublicForecastCitation,
  PublicMarket,
  PublicResolution,
} from "@/lib/forecastsTypes";

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

const NOW = "2026-04-29T12:00:00.000Z";

function market(overrides: Partial<PublicMarket> = {}): PublicMarket {
  return {
    id: "market-1",
    organization_id: "org-1",
    source: "POLYMARKET",
    external_id: "poly-1",
    title: "Will the policy bill pass before June?",
    description: "A binary policy market.",
    resolution_criteria: "Resolves YES if the bill passes before 2026-06-01.",
    category: "policy",
    current_yes_price: 0.58,
    current_no_price: 0.42,
    volume: 125000,
    open_time: NOW,
    close_time: "2026-05-11T12:00:00.000Z",
    resolved_at: null,
    resolved_outcome: null,
    raw_payload: {},
    status: "OPEN",
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function citation(index: number): PublicForecastCitation {
  return {
    id: `citation-${index}`,
    prediction_id: "forecast-1",
    source_type: "CONCLUSION",
    source_id: `source-${index}`,
    quoted_span: `quoted source ${index}`,
    support_label: "DIRECT",
    retrieval_score: 0.91,
    is_revoked: false,
  };
}

function resolution(
  outcome: string,
  overrides: Partial<PublicResolution> = {},
): PublicResolution {
  return {
    id: `resolution-${outcome.toLowerCase()}`,
    prediction_id: "forecast-1",
    market_outcome: outcome,
    brier_score: 0.12,
    log_loss: 0.39,
    calibration_bucket: 0.6,
    resolved_at: "2026-05-12T12:00:00.000Z",
    justification: "Fixture settlement.",
    created_at: "2026-05-12T12:01:00.000Z",
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
    headline: "Sources imply passage is more likely than market pricing",
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
    citations: [citation(1), citation(2), citation(3), citation(4)],
    resolution: null,
    ...overrides,
  };
}

describe("ForecastCard", () => {
  it("renders every status pill variant", () => {
    const published = renderToStaticMarkup(<ForecastCard forecast={forecast()} />);
    const correct = renderToStaticMarkup(
      <ForecastCard forecast={forecast({ status: "RESOLVED", resolution: resolution("YES") })} />,
    );
    const incorrect = renderToStaticMarkup(
      <ForecastCard forecast={forecast({ status: "RESOLVED", resolution: resolution("NO") })} />,
    );
    const cancelled = renderToStaticMarkup(
      <ForecastCard
        forecast={forecast({
          status: "RESOLVED",
          resolution: resolution("CANCELLED"),
        })}
      />,
    );

    expect(published).toContain("PUBLISHED");
    expect(correct).toContain("RESOLVED-CORRECT");
    expect(incorrect).toContain("RESOLVED-INCORRECT");
    expect(cancelled).toContain("RESOLVED-CANCELLED");
  });

  it("hides the edge chevron when the model edge is below five points", () => {
    const html = renderToStaticMarkup(
      <ForecastCard
        forecast={forecast({
          probability_yes: 0.62,
          market: market({ current_yes_price: 0.58 }),
        })}
      />,
    );

    expect(html).toContain("Market: 0.58");
    expect(html).not.toContain("model edge");
    expect(html).not.toContain("+0.04");
  });

  it("renders probability, source count, metadata, edge, and forecast link", () => {
    const html = renderToStaticMarkup(<ForecastCard forecast={forecast()} />);

    expect(html).toContain('href="/forecasts/forecast-1"');
    expect(html).toContain("64% YES");
    expect(html).toContain("Market: 0.58");
    expect(html).toContain("+0.06");
    expect(html).toContain("Polymarket");
    expect(html).toContain("policy");
    expect(html).toContain("▦ 4 sources");
  });
});
