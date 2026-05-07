import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import OpinionCard from "@/app/currents/OpinionCard";
import XPostEmbed from "@/app/currents/XPostEmbed";
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
      source: "X_TWITTER",
      external_id: "external-1",
      author_handle: "analyst",
      text: "The mayor announced a new transit funding plan on X.",
      url: "https://x.com/analyst/status/external-1",
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

  it("renders the observed X post as the object being analyzed", () => {
    const html = renderToStaticMarkup(<OpinionCard opinion={opinion()} />);

    expect(html).toContain("twitter-tweet");
    expect(html).toContain('data-theme="dark"');
    expect(html).toContain('data-theseus-x-embed="card"');
    expect(html).toContain("background:var(--currents-bg-elevated)");
    expect(html).toContain("border-radius:16px");
    expect(html).toContain("overflow:hidden");
    expect(html).toContain("https://twitter.com/analyst/status/external-1");
    expect(html).toContain("@analyst");
    expect(html).toContain("The mayor announced a new transit funding plan on X.");
    expect(html).toContain("X post");
    expect(html).not.toContain("source X post");
  });

  it("paints standalone X embeds against the Currents page surface", () => {
    const html = renderToStaticMarkup(
      <XPostEmbed
        fallbackText="Standalone post copy."
        surface="page"
        url="https://x.com/analyst/status/external-2"
      />,
    );

    expect(html).toContain("twitter-tweet");
    expect(html).toContain('data-theseus-x-embed="page"');
    expect(html).toContain("background:var(--currents-bg)");
    expect(html).toContain("https://twitter.com/analyst/status/external-2");
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
