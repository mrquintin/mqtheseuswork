import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import OpinionCard from "@/app/currents/OpinionCard";
import type { PublicCitation, PublicOpinion } from "@/lib/currentsTypes";

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

function citation(index: number, sourceKind = "claim"): PublicCitation {
  return {
    id: `citation-${index}`,
    source_kind: sourceKind,
    source_id: `source-${index}`,
    quoted_span: `quoted span ${index}`,
    retrieval_score: 0.91,
    is_revoked: false,
  };
}

function opinion(overrides: Partial<PublicOpinion> = {}): PublicOpinion {
  return {
    id: "opinion-1",
    organization_id: "org-1",
    event_id: "event-1",
    stance: "complicates",
    confidence: 0.72,
    headline: "Markets misread the signal",
    body_markdown: "This is **supported** but *qualified* with `code`.",
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "test-model",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: {
      id: "event-1",
      source: "X",
      external_id: "external-1",
      author_handle: "analyst",
      text: "event text",
      url: "https://example.com/event",
      captured_at: "2026-04-29T12:00:00.000Z",
      observed_at: "2026-04-29T11:59:00.000Z",
      topic_hint: "macro",
    },
    citations: [citation(1, "conclusion"), citation(2, "claim")],
    ...overrides,
  };
}

describe("OpinionCard", () => {
  it("renders the stance pill, headline, and safe markdown body", () => {
    const html = renderToStaticMarkup(
      <OpinionCard
        opinion={opinion({
          body_markdown:
            "This is **supported** but *qualified* with `code` and [evidence](https://example.com/source).",
        })}
      />,
    );

    expect(html).toContain("complicates");
    expect(html).toContain("Markets misread the signal");
    expect(html).toContain("<strong>supported</strong>");
    expect(html).toContain("<em>qualified</em>");
    expect(html).toContain("<code");
    expect(html).toContain(">code</code>");
    expect(html).toContain('rel="noopener nofollow ugc"');
    expect(html).toContain('target="_blank"');
  });

  it("renders at most three citation chips and a +N more marker", () => {
    const html = renderToStaticMarkup(
      <OpinionCard
        opinion={opinion({
          citations: [
            citation(1, "conclusion"),
            citation(2, "claim"),
            citation(3, "claim"),
            citation(4, "claim"),
            citation(5, "claim"),
          ],
        })}
      />,
    );

    expect(html).toContain("/currents/opinion-1#src-source-1");
    expect(html).toContain("/currents/opinion-1#src-source-2");
    expect(html).toContain("/currents/opinion-1#src-source-3");
    expect(html).not.toContain("/currents/opinion-1#src-source-4");
    expect(html).toContain("+2 more");
  });

  it("escapes markdown containing script tags", () => {
    const html = renderToStaticMarkup(
      <OpinionCard
        opinion={opinion({
          body_markdown: 'Claim <script>alert("x")</script> stays inert.',
        })}
      />,
    );

    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&lt;/script&gt;");
  });

  it("links the follow-up CTA to the opinion ask anchor", () => {
    const html = renderToStaticMarkup(<OpinionCard opinion={opinion()} />);

    expect(html).toContain('href="/currents/opinion-1#ask"');
    expect(html).toContain("Ask a follow-up");
  });
});
