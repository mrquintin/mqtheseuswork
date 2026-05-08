import { beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  organization: { findUnique: vi.fn(), findMany: vi.fn() },
  publishedConclusion: { findMany: vi.fn() },
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));
vi.mock("@/lib/methodologyProfiles", () => ({
  parseMethodologyPayload: () => ({
    schema: "theseus.methodology.v1",
    reviewerNarrative: "",
    profiles: [],
  }),
}));

import { listPublishedConclusions, parsePublicationPayload } from "@/lib/conclusionsRead";

describe("parsePublicationPayload", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps generated article citations linkable only for public-safe URLs", () => {
    const payload = parsePublicationPayload({
      slug: "firm-perspective",
      payloadJson: JSON.stringify({
        schema: "theseus.publicConclusion.v1",
        conclusionText: "The firm believes public claims need public-safe sourcing.",
        rationale: "The firm believes citations should not expose private source surfaces.",
        article: {
          kind: "THEMATIC",
          bodyMarkdown: "The firm believes public claims need public-safe sourcing.",
          citations: [
            {
              label: "S1",
              source_kind: "event_opinion",
              source_id: "opinion-1",
              quoted_span: "Public opinion span.",
              public_url: "/currents/opinion-1",
            },
            {
              label: "S2",
              source_kind: "upload",
              source_id: "upload-private",
              quoted_span: "Private upload span.",
              public_url: "/transcripts/upload-private",
            },
            {
              label: "S3",
              source_kind: "current_event",
              source_id: "event-1",
              quoted_span: "External public span.",
              public_url: "https://x.com/source/status/1",
            },
          ],
        },
      }),
    });

    expect(payload.article?.citations).toMatchObject([
      { label: "S1", publicUrl: "/currents/opinion-1", linkable: true },
      { label: "S2", publicUrl: null, linkable: false },
      { label: "S3", publicUrl: "https://x.com/source/status/1", linkable: true },
    ]);
  });

  it("logs but does not fail when a public title exceeds 70 characters", async () => {
    const previousOrgId = process.env.THESEUS_PUBLIC_ORG_ID;
    const title = "A Mixed Case Public Title That Is Intentionally Longer Than Seventy Characters";
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    try {
      process.env.THESEUS_PUBLIC_ORG_ID = "org-1";
      dbMock.organization.findUnique.mockResolvedValue({ id: "org-1", deletedAt: null });
      dbMock.publishedConclusion.findMany.mockResolvedValue([
        {
          id: "published-1",
          kind: "ARTICLE",
          slug: "long-title",
          version: 1,
          sourceConclusionId: "conclusion-1",
          publishedAt: new Date("2026-05-01T12:00:00.000Z"),
          doi: "",
          zenodoRecordId: "",
          discountedConfidence: 0.5,
          statedConfidence: 0.6,
          calibrationDiscountReason: "",
          payloadJson: JSON.stringify({
            schema: "theseus.publicConclusion.v1",
            conclusionText: title,
          }),
        },
      ]);

      const rows = await listPublishedConclusions();

      expect(rows[0].payload.conclusionText).toBe(title);
      expect(warn).toHaveBeenCalledWith(
        "[title-policy] long title (%d chars): %s",
        title.length,
        title,
      );
    } finally {
      warn.mockRestore();
      if (previousOrgId === undefined) {
        delete process.env.THESEUS_PUBLIC_ORG_ID;
      } else {
        process.env.THESEUS_PUBLIC_ORG_ID = previousOrgId;
      }
    }
  });
});
