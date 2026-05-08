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
import MethodologyPage from "@/app/methodology/page";
import ConclusionView from "@/components/ConclusionView";

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
      methodology: {
        schema: "theseus.methodology.v1",
        reviewerNarrative: "",
        profiles: [],
      },
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

async function renderMethodologyPage(): Promise<string> {
  const element = await MethodologyPage();
  return renderToStaticMarkup(element);
}

function renderConclusion(row: PublishedConclusion): string {
  return renderToStaticMarkup(<ConclusionView row={row} allVersions={[row]} responses={[]} />);
}

function resetPublicMocks() {
  mocks.getFounder.mockResolvedValue(null);
  mocks.listCurrents.mockResolvedValue({ items: [] });
  mocks.listPublishedArticles.mockResolvedValue([]);
}

describe("PublicHomePage", () => {
  beforeEach(resetPublicMocks);

  it("snapshots the empty public homepage", async () => {
    const html = await renderHomepage();

    expect(html).toMatchSnapshot();
    expect(html).toContain("A working system for recording firm reasoning");
    expect(html).toContain(
      "The firm has not yet published anything publicly. Reach out:",
    );
    expect(html).not.toContain("/responses");
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
    expect(html).not.toContain("/responses");
  });
});

describe("Public methodology surfaces", () => {
  beforeEach(resetPublicMocks);

  it("explains the object-level conclusion versus reusable method distinction", async () => {
    const html = await renderMethodologyPage();

    expect(html).toContain("Two different public records");
    expect(html).toContain("object-level");
    expect(html).toContain("reusable");
    expect(html).toContain("the conclusion does not transfer automatically with it");
    expect(html).toContain("does not expose raw deliberation");
  });

  it("renders public methodology profiles without exposing private source anchors", () => {
    const privateSourceTitle = "PRIVATE_SESSION_TRANSCRIPT_DO_NOT_RENDER";
    const base = article();
    const row = article({
      payload: {
        ...base.payload,
        methodology: {
          schema: "theseus.methodology.v1",
          reviewerNarrative: "The reviewer approved this as a method summary rather than a source excerpt.",
          profiles: [
            {
              patternType: "first_principles_decomposition",
              title: "Purpose before mechanism",
              summary: "The reasoning first fixes the purpose, then judges mechanisms by that purpose.",
              reasoningMoves: ["Separate terminal purpose from implementation mechanism."],
              transferTargets: ["institution-design questions"],
              assumptions: ["The purpose can be named without hiding the operative tradeoff."],
              failureModes: ["Treating the abstraction as proof in another domain."],
              evidenceAnchors: [{ sourceTitle: privateSourceTitle, sentenceIndex: 42 }],
              confidence: 0.84,
            },
          ],
        },
      },
    });

    const html = renderConclusion(row);

    expect(html).toContain("Method used to reach this view");
    expect(html).toContain("Methodology orientation");
    expect(html).toContain("Purpose before mechanism");
    expect(html).toContain("Reasoning moves");
    expect(html).toContain("Working assumptions");
    expect(html).toContain("Potential transfer targets");
    expect(html).toContain("Failure modes");
    expect(html).toContain("not a raw transcript");
    expect(html).toContain("claim that the conclusion automatically transfers");
    expect(html).not.toContain(privateSourceTitle);
    expect(html).not.toContain("sourceTitle");
    expect(html).not.toContain("sentenceIndex");
  });

  it("renders generated articles as firm perspective and withholds private citation links", () => {
    const privateQuotedSpan = "PRIVATE_SOURCE_CONTENT_DO_NOT_RENDER";
    const base = article();
    const row = article({
      payload: {
        ...base.payload,
        article: {
          kind: "THEMATIC",
          bodyMarkdown:
            "The firm believes public claims should cite the firm's source record without reproducing the source record.",
          sourceIds: ["opinion-1", "upload-private"],
          citations: [
            {
              label: "S1",
              sourceKind: "event_opinion",
              sourceId: "opinion-1",
              quotedSpan: "The public Currents opinion states the relevant position.",
              publicUrl: "/currents/opinion-1",
              linkable: true,
              sourceConclusionText: "The public Currents opinion states the relevant position.",
              sourceConclusionTitle: "Public Currents opinion",
            },
            {
              label: "S2",
              sourceKind: "upload",
              sourceId: "upload-private",
              quotedSpan: privateQuotedSpan,
              publicUrl: null,
              linkable: false,
              sourceConclusionText: null,
              sourceConclusionTitle: null,
            },
          ],
        },
      },
    });

    const html = renderConclusion(row);

    expect(html).toContain("The firm&#x27;s perspective");
    expect(html).toContain("The firm believes public claims should cite");
    expect(html).toContain("Sources");
    expect(html).toContain('href="/currents/opinion-1"');
    expect(html).toContain("Internal source recorded by the firm");
    expect(html).not.toContain("Open public source");
    expect(html).not.toContain("Cited span:");
    expect(html).not.toContain(privateQuotedSpan);
  });
});
