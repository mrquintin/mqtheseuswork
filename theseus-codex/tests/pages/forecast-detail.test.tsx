import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import AuditTrail from "@/app/forecasts/[id]/AuditTrail";
import BetsPanel from "@/app/forecasts/[id]/BetsPanel";
import ResolutionPanel from "@/app/forecasts/[id]/ResolutionPanel";
import type {
  CalibrationBucket,
  PublicBet,
  PublicForecastCitation,
  PublicForecastSource,
  PublicMarket,
  PublicResolution,
} from "@/lib/forecastsTypes";

const NOW = "2026-04-29T12:00:00.000Z";

function market(overrides: Partial<PublicMarket> = {}): PublicMarket {
  return {
    id: "market-1",
    organization_id: "org-1",
    source: "POLYMARKET",
    external_id: "poly-1",
    title: "Will the bill pass?",
    description: "Fixture market.",
    resolution_criteria: "Resolves YES if the bill passes.",
    category: "policy",
    current_yes_price: 0.58,
    current_no_price: 0.42,
    volume: 120000,
    open_time: NOW,
    close_time: "2026-05-12T12:00:00.000Z",
    resolved_at: null,
    resolved_outcome: null,
    raw_payload: {},
    status: "OPEN",
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function resolution(
  outcome: string,
  overrides: Partial<PublicResolution> = {},
): PublicResolution {
  return {
    id: `resolution-${outcome}`,
    prediction_id: "prediction-1",
    market_outcome: outcome,
    brier_score: 0.04,
    log_loss: 0.21,
    calibration_bucket: 0.8,
    resolved_at: "2026-04-02T12:00:00.000Z",
    justification: "Market resolved per UMA oracle.",
    created_at: "2026-04-02T12:01:00.000Z",
    ...overrides,
  };
}

function calibration(): CalibrationBucket[] {
  return [
    {
      bucket: 0.8,
      prediction_count: 30,
      resolved_count: 23,
      mean_probability_yes: 0.81,
      empirical_yes_rate: 0.78,
      mean_brier: 0.13,
    },
  ];
}

function bet(overrides: Partial<PublicBet> = {}): PublicBet {
  return {
    id: "bet-1",
    prediction_id: "prediction-1",
    mode: "PAPER",
    exchange: "POLYMARKET",
    side: "YES",
    stake_usd: 100,
    entry_price: 0.61,
    exit_price: 0.9,
    status: "SETTLED",
    settlement_pnl_usd: 47.54,
    created_at: NOW,
    settled_at: "2026-04-02T12:05:00.000Z",
    ...overrides,
  };
}

function citation(overrides: Partial<PublicForecastCitation> = {}): PublicForecastCitation {
  return {
    id: "citation-1",
    prediction_id: "prediction-1",
    source_type: "CONCLUSION",
    source_id: "cited",
    quoted_span: "cited span",
    support_label: "DIRECT",
    retrieval_score: 0.91,
    is_revoked: false,
    ...overrides,
  };
}

function source(overrides: Partial<PublicForecastSource> = {}): PublicForecastSource {
  return {
    id: "source-row-1",
    prediction_id: "prediction-1",
    source_type: "CONCLUSION",
    source_id: "cited",
    source_text: "This retrieved source includes a cited span and surrounding context.",
    quoted_span: "cited span",
    support_label: "DIRECT",
    retrieval_score: 0.91,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: "/c/cited",
    ...overrides,
  };
}

describe("forecast detail panels", () => {
  it("ResolutionPanel shows correct values for YES and NO outcomes", () => {
    const yes = renderToStaticMarkup(
      <ResolutionPanel
        calibration={calibration()}
        market={market()}
        resolution={resolution("YES")}
      />,
    );
    const no = renderToStaticMarkup(
      <ResolutionPanel
        calibration={calibration()}
        market={market()}
        resolution={resolution("NO")}
      />,
    );

    expect(yes).toContain("Resolved YES");
    expect(yes).toContain("Brier: 0.04");
    expect(yes).toContain("Log-loss: 0.21");
    expect(yes).toContain("Bucket: 0.8");
    expect(yes).toContain("78% YES (n=23)");
    expect(no).toContain("Resolved NO");
  });

  it("ResolutionPanel marks CANCELLED outcomes withdrawn and omits scoring metrics", () => {
    const html = renderToStaticMarkup(
      <ResolutionPanel
        calibration={calibration()}
        market={market()}
        resolution={resolution("CANCELLED", {
          brier_score: null,
          log_loss: null,
          calibration_bucket: null,
        })}
      />,
    );

    expect(html).toContain("Withdrawn");
    expect(html).toContain("Prediction withdrawn from calibration");
    expect(html).not.toContain("Brier:");
    expect(html).not.toContain("Log-loss:");
  });

  it("BetsPanel hides when paperBets is empty and renders settled P&L when present", () => {
    expect(renderToStaticMarkup(<BetsPanel paperBets={[]} />)).toBe("");

    const html = renderToStaticMarkup(<BetsPanel paperBets={[bet()]} />);
    expect(html).toContain("Paper bets");
    expect(html).toContain("YES");
    expect(html).toContain("$100.00");
    expect(html).toContain("+$47.54");
  });

  it("AuditTrail marks cited vs dropped sources", () => {
    const html = renderToStaticMarkup(
      <AuditTrail
        citations={[citation()]}
        sources={[
          source(),
          source({
            id: "source-row-2",
            source_id: "dropped",
            source_text: "Dropped source text that the model could have used.",
            quoted_span: "Dropped",
            retrieval_score: 0.79,
          }),
        ]}
      />,
    );

    expect(html).toContain("CONCLUSION/cited");
    expect(html).toContain("0.91");
    expect(html).toContain("CITED");
    expect(html).toContain("CONCLUSION/dropped");
    expect(html).toContain("0.79");
    expect(html).toContain("dropped");
  });
});
