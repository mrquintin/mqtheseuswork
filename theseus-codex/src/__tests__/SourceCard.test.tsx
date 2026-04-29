import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import SourceCard from "@/app/currents/[id]/SourceCard";
import type { PublicSource } from "@/lib/currentsTypes";

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

function source(overrides: Partial<PublicSource> = {}): PublicSource {
  return {
    id: "citation-1",
    opinion_id: "opinion-1",
    source_kind: "conclusion",
    source_id: "conclusion-slug",
    source_text: "Theseus argued durable compounding depends on disciplined evidence.",
    quoted_span: "durable compounding",
    retrieval_score: 0.91,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: "/c/conclusion-slug",
    ...overrides,
  };
}

describe("SourceCard", () => {
  it("renders revoked sources with the reason instead of hiding them", () => {
    const html = renderToStaticMarkup(
      <SourceCard
        source={source({
          is_revoked: true,
          revoked_reason: "source retired",
        })}
      />,
    );

    expect(html).toContain("Revoked: source retired");
    expect(html).toContain("line-through");
    expect(html).toContain("durable compounding");
  });

  it("uses the provided canonical path for conclusion links", () => {
    const html = renderToStaticMarkup(<SourceCard source={source()} />);

    expect(html).toContain('href="/c/conclusion-slug"');
    expect(html).toContain("Go to canonical");
  });

  it("falls back to a claim canonical link when canonical_path is missing", () => {
    const html = renderToStaticMarkup(
      <SourceCard
        source={source({
          source_kind: "claim",
          source_id: "claim-7",
          canonical_path: null,
        })}
      />,
    );

    expect(html).toContain('href="/conclusions/claim-7#claim-claim-7"');
  });
});
