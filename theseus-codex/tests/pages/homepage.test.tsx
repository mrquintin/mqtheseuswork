import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PublicBlogIndex from "@/app/page";
import { getFounder } from "@/lib/auth";
import { listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { db } from "@/lib/db";
import { getPortfolioSummary, listForecasts } from "@/lib/forecastsApi";
import type {
  PortfolioSummary,
  PublicForecast,
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

vi.mock("@/lib/forecastsApi", () => ({
  getPortfolioSummary: vi.fn(),
  listForecasts: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  db: {
    upload: {
      findMany: vi.fn(),
    },
  },
}));

vi.mock("next/navigation", () => ({
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
    organization_id: "org-1",
    event_id: `event-${id}`,
    stance: "complicates",
    confidence: 0.72,
    headline: `Opinion headline ${id}`,
    body_markdown: `Opinion body ${id}`,
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "test-model",
    generated_at: NOW,
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
  };
}

function market(id: string): PublicMarket {
  return {
    id: `market-${id}`,
    organization_id: "org-1",
    source: "POLYMARKET",
    external_id: `poly-${id}`,
    title: `Market ${id}`,
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

function forecast(id: string): PublicForecast {
  return {
    id,
    market_id: `market-${id}`,
    organization_id: "org-1",
    probability_yes: 0.64,
    confidence_low: 0.54,
    confidence_high: 0.74,
    headline: `Forecast headline ${id}`,
    reasoning: `Forecast reasoning ${id}`,
    status: "PUBLISHED",
    abstention_reason: null,
    topic_hint: "policy",
    model_name: "test-model",
    live_authorized_at: null,
    created_at: NOW,
    updated_at: NOW,
    revoked_sources_count: 0,
    market: market(id),
    citations: [],
    resolution: null,
  };
}

function portfolioSummary(
  overrides: Partial<PortfolioSummary> & Record<string, unknown> = {},
): PortfolioSummary & Record<string, unknown> {
  return {
    organization_id: "org-1",
    paper_balance_usd: 10000,
    paper_pnl_curve: [],
    calibration: [],
    mean_brier_90d: null,
    total_bets: 0,
    kill_switch_engaged: false,
    kill_switch_reason: null,
    updated_at: NOW,
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

async function renderHomepage() {
  const element = await PublicBlogIndex();
  const resolved = await resolveAsyncServerComponents(element);
  return renderToStaticMarkup(<>{resolved}</>);
}

describe("homepage dual pulse", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getFounder).mockResolvedValue(null);
    vi.mocked(db.upload.findMany).mockResolvedValue([]);
    vi.mocked(listPublishedArticles).mockResolvedValue([]);
    vi.mocked(listCurrents).mockResolvedValue({
      items: [opinion("1"), opinion("2"), opinion("3"), opinion("4")],
    });
    vi.mocked(listForecasts).mockResolvedValue({
      items: [forecast("1"), forecast("2"), forecast("3"), forecast("4")],
    });
    vi.mocked(getPortfolioSummary).mockResolvedValue(portfolioSummary());
  });

  it("renders both pulse windows with the desktop breakpoint rule", async () => {
    const html = await renderHomepage();

    expect(listCurrents).toHaveBeenCalledWith({ limit: 4, seeded: true });
    expect(listForecasts).toHaveBeenCalledWith({ limit: 4, seeded: true });
    expect(html).toContain("CURRENTS - live opinion");
    expect(html).toContain("FORECASTS - live predictions");
    expect(html).toContain("Opinion headline 1");
    expect(html).toContain("Forecast headline 1");
    expect(html).toContain("desktop&gt;=1024 tablet=720-1023 mobile&lt;720");
    expect(html).toContain("@media (min-width: 1024px)");
    expect(html).toContain("border-left: 1px solid rgba(232, 225, 211, 0.12)");
  });

  it("declares the mobile stacked breakpoint and tab toggle", async () => {
    const html = await renderHomepage();

    expect(html).toContain('aria-label="Pulse feed selector"');
    expect(html).toContain("Currents");
    expect(html).toContain("Forecasts");
    expect(html).toContain("@media (max-width: 719px)");
    expect(html).toContain('data-active="true"');
    expect(html).toContain('data-active="false"');
  });

  it("keeps Currents live and renders the Forecasts empty state", async () => {
    vi.mocked(listForecasts).mockResolvedValueOnce({ items: [] });

    const html = await renderHomepage();

    expect(html).toContain("Opinion headline 1");
    expect(html).toContain("No predictions yet - the model abstains");
  });

  it("reflects disabled and enabled live-trading postures from portfolio summary", async () => {
    vi.mocked(getPortfolioSummary).mockResolvedValueOnce(
      portfolioSummary({ live_trading_enabled: false }),
    );
    const disabled = await renderHomepage();

    vi.mocked(getPortfolioSummary).mockResolvedValueOnce(
      portfolioSummary({ liveTradingStatus: "ENABLED-AWAITING-AUTH" }),
    );
    const enabled = await renderHomepage();

    expect(disabled).toContain('data-live-trading-posture="DISABLED"');
    expect(enabled).toContain('data-live-trading-posture="ENABLED"');
  });
});
