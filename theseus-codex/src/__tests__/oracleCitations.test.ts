import { describe, expect, it } from "vitest";

import {
  citationHref,
  resolveOracleCitations,
} from "@/lib/oracleCitations";

describe("resolveOracleCitations", () => {
  it("returns an empty map when the answer has no citation tokens", () => {
    const result = resolveOracleCitations({
      answer: "The firm has not recorded material on this.",
      sources: [],
    });

    expect(result.citations).toEqual({});
    expect(result.citationsResolved).toBe(0);
    expect(result.citationsUnresolved).toBe(0);
  });

  it("resolves conclusion and upload tokens by source id prefix", () => {
    const result = resolveOracleCitations({
      answer:
        "The firm treats transcript anchors as a first-class knowledge surface [C:conc1234]. " +
        "Podcast paragraphs should become explorable and durable [U:upl12345].",
      sources: [
        {
          type: "conclusion",
          id: "conc123456789",
          label: "firm",
          tier: "firm",
          topic: "knowledge surface",
          text: "Transcript anchors should be treated as a first-class knowledge surface in the Codex.",
          url: "/conclusions/conc123456789",
        },
        {
          type: "upload",
          id: "upl123456789",
          label: "Podcast memo",
          text: "Podcast paragraphs should become explorable and durable in the Codex.",
          url: "/upload/upl123456789",
        },
      ],
      uploadChunks: [
        {
          uploadId: "upl123456789",
          chunkId: "chunk-preface",
          chunkIndex: 0,
          text: "A preface about unrelated operating cadence.",
        },
        {
          uploadId: "upl123456789",
          chunkId: "chunk-selected",
          chunkIndex: 3,
          text: "Podcast paragraphs should become explorable and durable in the Codex, with anchors that open a new tab.",
        },
      ],
    });

    expect(result.citationsResolved).toBe(2);
    expect(result.citationsUnresolved).toBe(0);
    expect(result.citations["[C:conc1234]"]).toMatchObject({
      type: "conclusion",
      id: "conc123456789",
      tier: "firm",
      url: "/conclusions/conc123456789",
    });
    expect(result.citations["[U:upl12345]"]).toMatchObject({
      type: "upload",
      id: "upl123456789",
      title: "Podcast memo",
      url: "/transcripts/upl123456789",
      anchor: "chunk-chunk-selected",
    });
    expect(citationHref(result.citations["[U:upl12345]"]!)).toBe(
      "/transcripts/upl123456789?anchor=chunk-chunk-selected",
    );
  });

  it("records hallucinated tokens with null urls", () => {
    const result = resolveOracleCitations({
      answer: "This answer cites material that was not retrieved [C:notreal1] [U:ghost999].",
      sources: [
        {
          type: "conclusion",
          id: "conc123456789",
          label: "firm",
          tier: "firm",
          text: "A real conclusion.",
          url: "/conclusions/conc123456789",
        },
      ],
    });

    expect(result.citationsResolved).toBe(0);
    expect(result.citationsUnresolved).toBe(2);
    expect(result.citations["[C:notreal1]"]).toMatchObject({
      type: "conclusion",
      id: "notreal1",
      url: null,
    });
    expect(result.citations["[U:ghost999]"]).toMatchObject({
      type: "upload",
      id: "ghost999",
      url: null,
      anchor: null,
    });
  });
});
