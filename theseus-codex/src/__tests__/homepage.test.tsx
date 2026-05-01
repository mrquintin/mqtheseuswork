import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicOpinion } from "@/lib/currentsTypes";
import type { PublishedConclusion } from "@/lib/conclusionsRead";

const mocks = vi.hoisted(() => ({
  getFounder: vi.fn(),
  listCurrents: vi.fn(),
  listPublishedArticles: vi.fn(),
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

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)}>Public header</header>
  ),
}));

vi.mock("@/app/(home)/DualPulseSection", () => ({
  default: () => (
    <section data-testid="dual-pulse">
      <h2>Theseus thinks out loud</h2>
    </section>
  ),
}));

vi.mock("@/app/(home)/TransparencyFooter", () => ({
  default: () => <footer>Transparency footer</footer>,
}));

vi.mock("@/lib/auth", () => ({
  getFounder: mocks.getFounder,
}));

vi.mock("@/lib/currentsApi", () => ({
  listCurrents: mocks.listCurrents,
}));

vi.mock("@/lib/conclusionsRead", () => ({
  listPublishedArticles: mocks.listPublishedArticles,
}));

import PublicHomePage from "@/app/page";

function opinion(overrides: Partial<PublicOpinion> = {}): PublicOpinion {
  return {
    id: "opinion-1",
    organization_id: "org-1",
    event_id: "event-1",
    stance: "complicates",
    confidence: 0.72,
    headline: "The market is over-reading the headline risk",
    body_markdown:
      "The firm sees a real change in tone, but the evidence does not yet support the consensus trade.",
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "test-model",
    generated_at: "2026-04-30T15:15:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: {
      id: "event-1",
      source: "x",
      external_id: "external-1",
      author_handle: "source",
      text: "A public event happened.",
      url: "https://example.com/event",
      captured_at: "2026-04-30T15:14:00.000Z",
      observed_at: "2026-04-30T15:13:00.000Z",
      topic_hint: "markets",
    },
    citations: [],
    ...overrides,
  };
}

function article(overrides: Partial<PublishedConclusion> = {}): PublishedConclusion {
  return {
    id: "article-1",
    kind: "ARTICLE",
    slug: "intellectual-capital-is-recorded-reasoning",
    version: 1,
    sourceConclusionId: "conclusion-1",
    publishedAt: "2026-04-30T14:00:00.000Z",
    doi: "10.1234/theseus.article",
    zenodoRecordId: "zenodo-1",
    discountedConfidence: 0.81,
    statedConfidence: 0.86,
    calibrationDiscountReason: "test fixture",
    payload: {
      schema: "theseus.publicConclusion.v1",
      conclusionText: "Intellectual capital is recorded reasoning under pressure.",
      rationale:
        "The memo argues that intellectual capital is not merely expertise, but a reusable record of judgment.",
      topicHint: "identity",
      evidenceSummary:
        "Reasoning compounds only when later decisions can inspect the claims, evidence, and objections that produced it.",
      exitConditions: [],
      strongestObjection: { objection: "", firmAnswer: "" },
      openQuestionsAdjacent: [],
      voiceComparisons: [],
      timeline: [],
      whatWouldChangeOurMind: [],
      citations: [],
    },
    ...overrides,
  };
}

async function renderHomepage(): Promise<string> {
  const element = await PublicHomePage();
  return renderToStaticMarkup(element);
}

describe("PublicHomePage", () => {
  beforeEach(() => {
    mocks.getFounder.mockResolvedValue(null);
    mocks.listCurrents.mockResolvedValue({ items: [] });
    mocks.listPublishedArticles.mockResolvedValue([]);
  });

  it("snapshots the empty public homepage", async () => {
    const html = await renderHomepage();

    expect(html).toMatchSnapshot();
    expect(html).toContain("A destination for intellectual capital");
    expect(html).toContain(
      "The firm has not yet published anything publicly. Reach out:",
    );
  });

  it("snapshots the populated public homepage", async () => {
    mocks.getFounder.mockResolvedValue({ id: "founder-1" });
    mocks.listCurrents.mockResolvedValue({
      items: [
        opinion(),
        opinion({
          id: "opinion-2",
          headline: "Energy policy is mispriced by timelines",
          generated_at: "2026-04-30T14:10:00.000Z",
        }),
        opinion({
          id: "opinion-3",
          headline: "AI capex risk is second-order, not absent",
          generated_at: "2026-04-30T13:05:00.000Z",
        }),
      ],
    });
    mocks.listPublishedArticles.mockResolvedValue([
      article(),
      article({
        id: "article-2",
        slug: "capital-decisions-need-a-reasoning-ledger",
        payload: {
          ...article().payload,
          conclusionText: "Capital decisions need a reasoning ledger.",
        },
      }),
    ]);

    const html = await renderHomepage();

    expect(html).toMatchSnapshot();
    expect(html).toContain("LATEST FROM THE FIRM · CURRENTS");
    expect(html).toContain("PUBLICATIONS · ESSAYS &amp; MEMOS");
    expect(html).toContain('data-testid="homepage-current-card"');
  });
});
