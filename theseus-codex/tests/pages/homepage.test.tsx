import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PublicBlogIndex from "@/app/page";
import { getFounder } from "@/lib/auth";
import { listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { getPortfolioSummary, listForecasts } from "@/lib/forecastsApi";
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

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/"),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
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

describe("homepage performance shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getFounder).mockResolvedValue(null);
    vi.mocked(listPublishedArticles).mockResolvedValue([]);
    vi.mocked(listCurrents).mockResolvedValue({
      items: [opinion("1"), opinion("2"), opinion("3"), opinion("4")],
    });
  });

  it("renders the public signal surface without blocking on forecast or portfolio APIs", async () => {
    const html = await renderHomepage();

    expect(listCurrents).toHaveBeenCalledWith(
      { limit: 3 },
      { next: { revalidate: 60, tags: ["public-home-currents"] } },
    );
    expect(getFounder).not.toHaveBeenCalled();
    expect(listForecasts).not.toHaveBeenCalled();
    expect(getPortfolioSummary).not.toHaveBeenCalled();
    expect(html).toContain("Opinion headline 1");
    expect(html).toContain("LIVE PUBLIC SURFACES");
    expect(html).toContain("Currents");
    expect(html).toContain("Forecasts");
    expect(html).toContain("Real-world X posts");
    expect(html).toContain("Prediction-market forecasts");
  });

  it("limits the homepage Currents preview to three cards", async () => {
    const html = await renderHomepage();

    expect(html).toContain("Opinion headline 1");
    expect(html).toContain("Opinion headline 2");
    expect(html).toContain("Opinion headline 3");
    expect(html).not.toContain("Opinion headline 4");
  });
});
