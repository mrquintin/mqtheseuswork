import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import AuditTrail from "@/app/currents/[id]/AuditTrail";
import type { PublicOpinion, PublicSource } from "@/lib/currentsTypes";

function opinion(): PublicOpinion {
  return {
    id: "opinion-1",
    organization_id: "org-1",
    event_id: "event-1",
    stance: "complicates",
    confidence: 0.78,
    headline: "The headline",
    body_markdown: "The body",
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "claude-haiku-4-5",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
  };
}

function source(overrides: Partial<PublicSource> = {}): PublicSource {
  return {
    id: "citation-1",
    opinion_id: "opinion-1",
    source_kind: "conclusion",
    source_id: "source-1",
    source_text: "Source text",
    quoted_span: "Source",
    retrieval_score: 0.88,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: "/c/source-1",
    ...overrides,
  };
}

describe("AuditTrail", () => {
  it("omits the revoked-source count when no sources are revoked", () => {
    const html = renderToStaticMarkup(
      <AuditTrail opinion={opinion()} sources={[source()]} />,
    );

    expect(html).toContain("confidence 78%");
    expect(html).not.toContain("source revoked");
    expect(html).not.toContain("sources revoked");
  });

  it("shows the revoked-source count when at least one source is revoked", () => {
    const html = renderToStaticMarkup(
      <AuditTrail
        opinion={opinion()}
        sources={[
          source({ is_revoked: true, revoked_reason: "retired" }),
          source({ id: "citation-2", source_id: "source-2" }),
        ]}
      />,
    );

    expect(html).toContain("1 source revoked");
  });
});
