import React, { type ReactNode } from "react";
import { NextRequest } from "next/server";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OperatorPage from "@/app/(authed)/forecasts/operator/page";
import ForecastDetailPage from "@/app/forecasts/[id]/page";
import ForecastsPage from "@/app/forecasts/page";
import PortfolioPage from "@/app/forecasts/portfolio/page";
import PublicBlogIndex from "@/app/page";
import { middleware } from "@/middleware";
import { getFounder } from "@/lib/auth";
import { listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { db } from "@/lib/db";
import {
  getForecast,
  getForecastBets,
  getForecastResolution,
  getForecastSources,
  getMarket,
  getPortfolioBets,
  getPortfolioCalibration,
  getPortfolioSummary,
  listForecasts,
} from "@/lib/forecastsApi";
import { listOperatorLiveBets } from "@/lib/forecastsOperatorApi";
import type {
  OperatorBet,
  PortfolioSummary,
  PublicBet,
  PublicForecast,
  PublicForecastSource,
  PublicMarket,
} from "@/lib/forecastsTypes";
import { listPublishedArticles } from "@/lib/conclusionsRead";

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn(),
}));

vi.mock("@/lib/conclusionsRead", () => ({
  listPublishedArticles: vi.fn(),
}));

vi.mock("@/lib/currentsApi", () => ({
  listCurrents: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  db: {
    upload: {
      findMany: vi.fn(),
    },
  },
}));

vi.mock("@/lib/forecastsApi", () => ({
  getForecast: vi.fn(),
  getForecastBets: vi.fn(),
  getForecastResolution: vi.fn(),
  getForecastSources: vi.fn(),
  getMarket: vi.fn(),
  getPortfolioBets: vi.fn(),
  getPortfolioCalibration: vi.fn(),
  getPortfolioSummary: vi.fn(),
  listForecasts: vi.fn(),
}));

vi.mock("@/lib/forecastsOperatorApi", () => ({
  listOperatorLiveBets: vi.fn(),
}));

vi.mock("@/lib/useLiveForecasts", () => ({
  useLiveForecasts: (seed: PublicForecast[]) => ({
    connected: true,
    forecasts: seed,
    resolutions: {},
  }),
}));

vi.mock("next/navigation", () => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  }),
  usePathname: vi.fn(() => "/"),
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

type ElementProps = {
  children?: ReactNode;
  [key: string]: unknown;
};

const NOW = "2026-04-30T12:00:00.000Z";

function opinion(id: string): PublicOpinion {
  return {
    id,
    organization_id: "org-smoke",
    event_id: `event-${id}`,
    stance: "supports",
    confidence: 0.71,
    headline: `Opinion smoke ${id}`,
    body_markdown: `Opinion smoke body ${id}`,
    uncertainty_notes: [],
    topic_hint: "policy",
    model_name: "fixture",
    generated_at: NOW,
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
  };
}

function market(overrides: Partial<PublicMarket> = {}): PublicMarket {
  return {
    id: "market-smoke",
    organization_id: "org-smoke",
    source: "POLYMARKET",
    external_id: "poly-smoke",
    title: "Will the smoke market resolve YES?",
    description: "Fixture market.",
    resolution_criteria: "Resolves YES if the fixture says yes.",
    category: "policy",
    current_yes_price: 0.57,
    current_no_price: 0.43,
    volume: 1200,
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
    id: "forecast-smoke",
    market_id: "market-smoke",
    organization_id: "org-smoke",
    probability_yes: 0.68,
    confidence_low: 0.58,
    confidence_high: 0.78,
    headline: "Forecast smoke headline",
    reasoning: "Source smoke-one supports the prediction [1]. Source smoke-two adds context [2].",
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
        id: "citation-smoke-1",
        prediction_id: "forecast-smoke",
        source_type: "CONCLUSION",
        source_id: "smoke-one",
        quoted_span: "supports the prediction",
        support_label: "DIRECT",
        retrieval_score: 0.94,
        is_revoked: false,
      },
      {
        id: "citation-smoke-2",
        prediction_id: "forecast-smoke",
        source_type: "CONCLUSION",
        source_id: "smoke-two",
        quoted_span: "adds context",
        support_label: "INDIRECT",
        retrieval_score: 0.88,
        is_revoked: false,
      },
    ],
    resolution: null,
    ...overrides,
  };
}

function source(id: string, quotedSpan: string): PublicForecastSource {
  return {
    id: `source-row-${id}`,
    prediction_id: "forecast-smoke",
    source_type: "CONCLUSION",
    source_id: id,
    source_text: `Fixture source ${id} says this evidence ${quotedSpan} for the public smoke path.`,
    quoted_span: quotedSpan,
    support_label: id === "smoke-one" ? "DIRECT" : "INDIRECT",
    retrieval_score: id === "smoke-one" ? 0.94 : 0.88,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: `/c/${id}`,
  };
}

function portfolioSummary(
  overrides: Partial<PortfolioSummary> & Record<string, unknown> = {},
): PortfolioSummary & Record<string, unknown> {
  return {
    organization_id: "org-smoke",
    paper_balance_usd: 10000,
    paper_pnl_curve: [],
    calibration: [
      {
        bucket: 0.7,
        prediction_count: 4,
        resolved_count: 4,
        mean_probability_yes: 0.69,
        empirical_yes_rate: 0.75,
        mean_brier: 0.18,
      },
    ],
    mean_brier_90d: 0.18,
    total_bets: 1,
    kill_switch_engaged: false,
    kill_switch_reason: null,
    updated_at: NOW,
    live_trading_enabled: false,
    ...overrides,
  };
}

function paperBet(overrides: Partial<PublicBet> & Record<string, unknown> = {}): PublicBet & Record<string, unknown> {
  return {
    id: "paper-bet-smoke",
    prediction_id: "forecast-smoke",
    mode: "PAPER",
    exchange: "POLYMARKET",
    side: "YES",
    stake_usd: 25,
    entry_price: 0.57,
    exit_price: null,
    status: "OPEN",
    settlement_pnl_usd: null,
    created_at: NOW,
    settled_at: null,
    prediction_headline: "Forecast smoke headline",
    ...overrides,
  };
}

function liveBet(overrides: Partial<OperatorBet> = {}): OperatorBet {
  return {
    id: "live-bet-smoke",
    prediction_id: "forecast-smoke",
    organization_id: "org-smoke",
    mode: "LIVE",
    exchange: "POLYMARKET",
    side: "YES",
    stake_usd: 25,
    entry_price: 0.57,
    exit_price: null,
    status: "AUTHORIZED",
    external_order_id: null,
    client_order_id: "client-live-bet-smoke",
    settlement_pnl_usd: null,
    live_authorized_at: NOW,
    confirmed_at: null,
    submitted_at: null,
    created_at: NOW,
    settled_at: null,
    ...overrides,
  };
}

async function resolveAsyncServerComponents(node: ReactNode): Promise<ReactNode> {
  if (Array.isArray(node)) {
    const resolved = await Promise.all(node.map(resolveAsyncServerComponents));
    return resolved.some((child, index) => child !== node[index]) ? resolved : node;
  }

  if (!React.isValidElement(node)) return node;

  if (
    typeof node.type === "function" &&
    node.type.constructor.name === "AsyncFunction"
  ) {
    const rendered = await (node.type as (props: ElementProps) => Promise<ReactNode>)(
      node.props as ElementProps,
    );
    return resolveAsyncServerComponents(rendered);
  }

  const props = node.props as ElementProps;
  if (!("children" in props)) return node;

  const children = await resolveAsyncServerComponents(props.children);
  if (children === props.children) return node;
  if (Array.isArray(children)) return React.cloneElement(node, undefined, ...children);
  return React.cloneElement(node, undefined, children);
}

async function htmlFor(node: ReactNode): Promise<string> {
  const resolved = await resolveAsyncServerComponents(node);
  return renderToStaticMarkup(<>{resolved}</>);
}

describe("forecasts smoke fallback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getFounder).mockResolvedValue(null);
    vi.mocked(db.upload.findMany).mockResolvedValue([]);
    vi.mocked(listPublishedArticles).mockResolvedValue([]);
    vi.mocked(listCurrents).mockResolvedValue({
      items: [opinion("1"), opinion("2"), opinion("3"), opinion("4")],
    });
    vi.mocked(listForecasts).mockResolvedValue({
      items: [forecast(), forecast({ id: "forecast-smoke-2", headline: "Second smoke forecast" })],
    });
    vi.mocked(getForecast).mockResolvedValue(forecast());
    vi.mocked(getMarket).mockResolvedValue(market());
    vi.mocked(getForecastSources).mockResolvedValue([
      source("smoke-one", "supports the prediction"),
      source("smoke-two", "adds context"),
    ]);
    vi.mocked(getForecastResolution).mockRejectedValue(new Error("Forecasts API 404: not resolved"));
    vi.mocked(getForecastBets).mockResolvedValue([paperBet()]);
    vi.mocked(getPortfolioSummary).mockResolvedValue(portfolioSummary());
    vi.mocked(getPortfolioCalibration).mockResolvedValue({
      items: portfolioSummary().calibration,
    });
    vi.mocked(getPortfolioBets).mockResolvedValue({
      items: [paperBet()],
      next_offset: null,
    });
    vi.mocked(listOperatorLiveBets).mockResolvedValue({
      items: [liveBet()],
      next_offset: null,
    });
  });

  it("renders the homepage dual-window block", async () => {
    const html = await htmlFor(await PublicBlogIndex());

    expect(html).toContain("CURRENTS - live opinion");
    expect(html).toContain("FORECASTS - live predictions");
    expect(html).toContain("Forecast smoke headline");
  });

  it("renders the forecasts index with at least one ForecastCard", async () => {
    const html = await htmlFor(await ForecastsPage());

    expect(html).toContain("Forecast predictions");
    expect(html).toContain("Forecast smoke headline");
    expect(html).toContain("/forecasts/forecast-smoke");
  });

  it("renders the forecast detail headline, citations, and source drawer", async () => {
    const html = await htmlFor(
      await ForecastDetailPage({ params: Promise.resolve({ id: "forecast-smoke" }) }),
    );

    expect(html).toContain("Forecast smoke headline");
    expect(html).toContain("Forecast reasoning and citations");
    expect(html).toContain("Citation drawer");
    expect(html).toContain("supports the prediction");
    expect(html).toContain("forecast-drawer-citation-smoke-one");
  });

  it("renders portfolio calibration, Brier, and clear kill-switch state", async () => {
    const html = await htmlFor(
      await PortfolioPage({ searchParams: Promise.resolve({}) }),
    );

    expect(html).toContain("Forecasts Portfolio");
    expect(html).toContain("Calibration");
    expect(html).toContain("Brier");
    expect(html).toContain('data-kill-switch="clear"');
    expect(html).toContain('data-kill-switch-palette="green"');
    expect(html).toContain("clear");
  });

  it("requires auth for operator and renders disabled confirms for a founder when live trading is off", async () => {
    const res = middleware(new NextRequest("http://localhost:3000/forecasts/operator"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login?next=%2Fforecasts%2Foperator");
    await expect(OperatorPage()).rejects.toThrow("NEXT_REDIRECT:/login");

    vi.mocked(getFounder).mockResolvedValue({
      id: "founder-smoke",
      organizationId: "org-smoke",
      role: "founder",
    } as never);
    vi.mocked(listForecasts).mockResolvedValueOnce({
      items: [forecast({ live_authorized_at: NOW })],
    });
    const html = await htmlFor(await OperatorPage());

    expect(html).toContain("Forecasts operator");
    expect(html).toContain("Pending live authorizations");
    expect(html).toContain("Pending bet confirmations");
    expect(html).toContain('data-confirm-bet-id="live-bet-smoke"');
    expect(html).toContain("disabled");
    expect(html).toContain("DISABLED: Live trading is disabled by the server environment.");
  });

  it("renders authorize-live controls when the harness enables live trading", async () => {
    vi.stubEnv("FORECASTS_LIVE_TRADING_ENABLED", "true");
    vi.stubEnv("FORECASTS_MAX_STAKE_USD", "50");
    vi.mocked(getFounder).mockResolvedValue({
      id: "founder-smoke",
      organizationId: "org-smoke",
      role: "founder",
    } as never);
    vi.mocked(listForecasts).mockResolvedValueOnce({
      items: [forecast({ live_authorized_at: null })],
    });

    const html = await htmlFor(await OperatorPage());

    expect(html).toContain("Authorize live betting on this prediction");
    expect(html).not.toContain("Live trading disabled server-side.");
    vi.unstubAllEnvs();
  });
});
