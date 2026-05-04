import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({ db: {} }));
vi.mock("@/lib/methodologyProfiles", () => ({
  parseMethodologyPayload: () => ({
    schema: "theseus.methodology.v1",
    reviewerNarrative: "",
    profiles: [],
  }),
}));

import { parsePublicationPayload } from "@/lib/conclusionsRead";

describe("parsePublicationPayload", () => {
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
});
