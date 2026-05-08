import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  organization: { findUnique: vi.fn(), findMany: vi.fn() },
  publishedConclusion: { findMany: vi.fn() },
  conclusion: { findMany: vi.fn() },
  eventOpinion: { findMany: vi.fn() },
  forecastPrediction: { findMany: vi.fn() },
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));
vi.mock("@/lib/methodologyProfiles", () => ({
  parseMethodologyPayload: () => ({
    schema: "theseus.methodology.v1",
    reviewerNarrative: "",
    profiles: [],
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

import ConclusionView from "@/components/ConclusionView";
import { listPublishedConclusions, type PublishedArticleCitation, type PublishedConclusion } from "@/lib/conclusionsRead";

const previousOrgId = process.env.THESEUS_PUBLIC_ORG_ID;

function conclusion(citations: PublishedArticleCitation[]): PublishedConclusion {
  return {
    id: "article-1",
    kind: "ARTICLE",
    slug: "firm-source-rendering",
    version: 1,
    sourceConclusionId: "conclusion-1",
    publishedAt: "2026-05-01T12:00:00.000Z",
    doi: "",
    zenodoRecordId: "",
    discountedConfidence: 0.7,
    statedConfidence: 0.8,
    calibrationDiscountReason: "",
    payload: {
      schema: "theseus.publicConclusion.v1",
      conclusionText: "A compact article title.",
      rationale: "Article rationale.",
      topicHint: "sources",
      evidenceSummary: "Article evidence summary.",
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
      article: {
        kind: "THEMATIC",
        bodyMarkdown: "The article body cites firm-side material.",
        sourceIds: [],
        citations,
      },
    },
  };
}

function renderConclusion(row: PublishedConclusion): string {
  return renderToStaticMarkup(<ConclusionView row={row} allVersions={[row]} responses={[]} />);
}

describe("ConclusionView firm source list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.THESEUS_PUBLIC_ORG_ID = "org-1";
    dbMock.organization.findUnique.mockResolvedValue({ id: "org-1", deletedAt: null });
    dbMock.organization.findMany.mockResolvedValue([]);
    dbMock.publishedConclusion.findMany.mockResolvedValue([]);
    dbMock.conclusion.findMany.mockResolvedValue([]);
    dbMock.eventOpinion.findMany.mockResolvedValue([]);
    dbMock.forecastPrediction.findMany.mockResolvedValue([]);
  });

  afterEach(() => {
    if (previousOrgId === undefined) {
      delete process.env.THESEUS_PUBLIC_ORG_ID;
    } else {
      process.env.THESEUS_PUBLIC_ORG_ID = previousOrgId;
    }
  });

  it("renders compact rows without boilerplate source cards", () => {
    const row = conclusion([
      {
        label: "S1 event opinion",
        sourceKind: "event_opinion",
        sourceId: "opinion-1",
        quotedSpan: "A quoted source span that should not render.",
        publicUrl: "/currents/opinion-1",
        linkable: true,
        sourceConclusionText: "The firm thinks the public signal is directionally real.",
        sourceConclusionTitle: "Public signal opinion",
      },
      {
        label: "S2",
        sourceKind: "principle",
        sourceId: "principle-1",
        quotedSpan: "A private quoted span that should not render.",
        publicUrl: null,
        linkable: false,
        sourceConclusionText: "Repeated reasoning only compounds if later readers can audit it.",
        sourceConclusionTitle: null,
      },
      {
        label: "S3",
        sourceKind: "upload",
        sourceId: "upload-private",
        quotedSpan: "Private upload text that should not render.",
        publicUrl: null,
        linkable: false,
        sourceConclusionText: null,
        sourceConclusionTitle: null,
      },
    ]);

    const html = renderConclusion(row);

    expect(html.match(/class="firm-source-row"/g) ?? []).toHaveLength(3);
    expect(html).toContain('<h2 id="article-sources-title">Sources</h2>');
    expect(html).toContain('href="/currents/opinion-1"');
    expect(html).toContain("The firm thinks the public signal is directionally real.");
    expect(html).toContain("Repeated reasoning only compounds if later readers can audit it.");
    expect(html).toContain("Internal source recorded by the firm");
    expect(html).not.toMatch(/<a[^>]*>Repeated reasoning only compounds if later readers can audit it\.<\/a>/);
    expect(html).not.toContain("Open public source");
    expect(html).not.toContain("Cited span:");
    expect(html).not.toContain("S1 event opinion");
    expect(html).not.toContain("event opinion");
    expect(html).not.toContain("Firm-side sources");
  });

  it("removes a stale link when the cited source comes from a private upload", async () => {
    dbMock.publishedConclusion.findMany.mockResolvedValue([
      {
        id: "article-1",
        kind: "ARTICLE",
        slug: "private-source-article",
        version: 1,
        sourceConclusionId: "article-source",
        publishedAt: new Date("2026-05-01T12:00:00.000Z"),
        doi: "",
        zenodoRecordId: "",
        discountedConfidence: 0.7,
        statedConfidence: 0.8,
        calibrationDiscountReason: "",
        payloadJson: JSON.stringify({
          schema: "theseus.publicConclusion.v1",
          conclusionText: "Article that cites a private source.",
          rationale: "The rendered citation must not expose a private link.",
          article: {
            kind: "THEMATIC",
            bodyMarkdown: "The article body.",
            citations: [
              {
                label: "S1",
                source_kind: "conclusion",
                source_id: "source-private",
                quoted_span: "Private span.",
                public_url: "/c/private-source/v/1",
              },
            ],
          },
        }),
      },
    ]);
    dbMock.conclusion.findMany.mockResolvedValue([
      {
        id: "source-private",
        text: "The private source conclusion remains visible as plain prose.",
        topicHint: "private",
        sources: [
          {
            upload: {
              visibility: "private",
              publishedAt: new Date("2026-05-01T11:00:00.000Z"),
              slug: "private-source",
            },
          },
        ],
      },
    ]);

    const [row] = await listPublishedConclusions();
    const html = renderConclusion(row);

    expect(row.payload.article?.citations[0]).toMatchObject({
      publicUrl: null,
      linkable: false,
      sourceConclusionText: "The private source conclusion remains visible as plain prose.",
    });
    expect(html).toContain("The private source conclusion remains visible as plain prose.");
    expect(html).not.toContain('href="/c/private-source/v/1"');
  });
});
