import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import TopicClusters from "@/app/currents/TopicClusters";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { DEFAULT_FILTER } from "@/lib/filterMatch";

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

function opinion(
  id: string,
  topic: string | null,
  overrides: Partial<PublicOpinion> = {},
): PublicOpinion {
  return {
    id,
    organization_id: "org-1",
    event_id: `event-${id}`,
    stance: "complicates",
    confidence: 0.7,
    headline: `Headline ${id}`,
    body_markdown: `Body ${id}`,
    uncertainty_notes: [],
    topic_hint: topic,
    model_name: "test-model",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
    ...overrides,
  };
}

describe("TopicClusters", () => {
  it("groups opinions by topic and renders only the top three per cluster", () => {
    const html = renderToStaticMarkup(
      <TopicClusters
        opinions={[
          opinion("climate-1", "climate"),
          opinion("climate-2", "climate"),
          opinion("climate-3", "climate"),
          opinion("climate-4", "climate"),
          opinion("labor-1", "labor"),
        ]}
      />,
    );

    expect(html).toContain("climate");
    expect(html).toContain("labor");
    expect(html).toContain("Headline climate-1");
    expect(html).toContain("Headline climate-2");
    expect(html).toContain("Headline climate-3");
    expect(html).not.toContain("Headline climate-4");
    expect(html).toContain("+1 more");
  });

  it("links +N more to the topic-filtered feed URL", () => {
    const html = renderToStaticMarkup(
      <TopicClusters
        filter={{
          ...DEFAULT_FILTER,
          stance: ["disagrees"],
          since: "24h",
          view: "clusters",
        }}
        opinions={[
          opinion("climate-1", "climate"),
          opinion("climate-2", "climate"),
          opinion("climate-3", "climate"),
          opinion("climate-4", "climate"),
        ]}
      />,
    );

    expect(html).toContain(
      'href="/currents?topic=climate&amp;stance=disagrees&amp;since=24h"',
    );
  });
});
