import { describe, expect, it } from "vitest";

import {
  buildConversationGeometry,
  buildYearEndConversationStats,
  transcriptChunkAnchor,
  type ConversationChunkInput,
} from "@/lib/conversationGeometry";

const handoffChunks: ConversationChunkInput[] = [
  {
    id: "chunk-a",
    index: 0,
    text: "Should the archive preserve geometry geometry for debate?",
    startMs: 0,
    speakerLabel: "Michael",
  },
  {
    id: "chunk-b",
    index: 1,
    text: "Yes, geometry should preserve debate context and context.",
    startMs: 10_000,
    speakerLabel: "Ada",
  },
  {
    id: "chunk-c",
    index: 2,
    text: "So geometry context becomes the bridge for later decisions.",
    startMs: 20_000,
    speakerLabel: "Michael",
  },
];

function singleCatalyst(fromText: string, toText: string) {
  const geometry = buildConversationGeometry([
    {
      id: "source",
      index: 0,
      text: fromText,
      speakerLabel: "Michael",
    },
    {
      id: "target",
      index: 1,
      text: toText,
      speakerLabel: "Ada",
    },
  ]);

  return geometry.catalysts[0]!;
}

describe("conversation geometry", () => {
  it("builds two-speaker handoffs and speaker weighting from chunk rows", () => {
    const geometry = buildConversationGeometry(handoffChunks);

    expect(geometry.hasSpeakerLabels).toBe(true);
    expect(geometry.hasRealSpeakerLabels).toBe(true);
    expect(geometry.totalTurns).toBe(3);
    expect(geometry.totalWords).toBe(25);
    expect(geometry.totalHandoffs).toBe(2);

    const michael = geometry.speakers.find((speaker) => speaker.label === "Michael");
    expect(michael).toMatchObject({
      id: "michael",
      turns: 2,
      wordCount: 17,
      questionTurns: 1,
      firstChunkId: "chunk-a",
      lastChunkId: "chunk-c",
      topRepeatedTerms: ["geometry"],
    });
    expect(michael?.shareOfWords).toBeCloseTo(17 / 25);
    expect(michael?.averageTurnLength).toBeCloseTo(8.5);

    const michaelToAda = geometry.edges.find(
      (edge) => edge.sourceLabel === "Michael" && edge.targetLabel === "Ada",
    );
    expect(michaelToAda).toMatchObject({
      source: "michael",
      target: "ada",
      count: 1,
      sharedTerms: ["preserve", "geometry", "debate"],
    });
    expect(michaelToAda?.weight).toBeGreaterThan(1);
  });

  it("classifies adjacent question-response catalyst moments deterministically", () => {
    const geometry = buildConversationGeometry(handoffChunks);

    expect(geometry.catalysts).toHaveLength(2);
    expect(geometry.catalysts[0]).toMatchObject({
      id: "chunk-a->chunk-b",
      fromChunkId: "chunk-a",
      toChunkId: "chunk-b",
      sourceLabel: "Michael",
      targetLabel: "Ada",
      kind: "question-response",
      score: 8,
      sharedTerms: ["preserve", "geometry", "debate"],
      fromExcerpt: "Should the archive preserve geometry geometry for debate?",
      toExcerpt: "Yes, geometry should preserve debate context and context.",
      anchor: transcriptChunkAnchor("chunk-b"),
    });
    expect(geometry.catalysts[1]).toMatchObject({
      fromChunkId: "chunk-b",
      toChunkId: "chunk-c",
      kind: "causal-continuation",
      score: 6,
      sharedTerms: ["geometry", "context"],
      anchor: transcriptChunkAnchor("chunk-c"),
    });
  });

  it.each([
    [
      "question-response",
      "What follows from this premise?",
      "It follows from the premise that evidence should stay attached.",
    ],
    [
      "agreement",
      "The archive should stay inspectable.",
      "Exactly, inspectable records keep the archive useful.",
    ],
    [
      "disagreement",
      "This label proves causality.",
      "But that overstates what the transcript shows.",
    ],
    [
      "causal-continuation",
      "The archive lost context.",
      "Because the citations were detached, the reader could not audit it.",
    ],
    [
      "conceptual-carry",
      "Archive geometry needs durable citation context.",
      "Citation context keeps archive geometry reviewable.",
    ],
    [
      "neutral-handoff",
      "The meeting starts after lunch.",
      "Tomorrow we schedule the recording.",
    ],
  ] as const)("classifies %s handoffs from adjacent transcript cues", (kind, fromText, toText) => {
    expect(singleCatalyst(fromText, toText).kind).toBe(kind);
  });

  it("creates catalyst anchors only for adjacent speaker handoffs", () => {
    const geometry = buildConversationGeometry([
      {
        id: "same-speaker-source",
        index: 0,
        text: "This is still the same speaker.",
        speakerLabel: "Michael",
      },
      {
        id: "handoff-source",
        index: 1,
        text: "Now the handoff question matters?",
        speakerLabel: "Michael",
      },
      {
        id: "handoff-target",
        index: 2,
        text: "It matters because the target line is the evidence.",
        speakerLabel: "Ada",
      },
    ]);

    expect(geometry.catalysts).toHaveLength(1);
    expect(geometry.catalysts[0]).toMatchObject({
      id: "handoff-source->handoff-target",
      sourceLabel: "Michael",
      targetLabel: "Ada",
      anchor: transcriptChunkAnchor("handoff-target"),
    });
  });

  it("keeps generic and missing speaker labels as analysis objects without treating them as real identities", () => {
    const geometry = buildConversationGeometry([
      {
        id: "generic-a",
        index: 0,
        text: "Speaker labels are present but generic.",
        speakerLabel: "Speaker 1",
      },
      {
        id: "generic-b",
        index: 1,
        text: "A missing label remains explicitly unattributed.",
        speakerLabel: null,
      },
      {
        id: "generic-c",
        index: 2,
        text: "A second generic speaker stays separate.",
        speakerLabel: "Speaker 2",
      },
    ]);

    expect(geometry.hasSpeakerLabels).toBe(true);
    expect(geometry.hasRealSpeakerLabels).toBe(false);
    expect(geometry.speakers.map((speaker) => speaker.label).sort()).toEqual([
      "Speaker 1",
      "Speaker 2",
      "Unattributed",
    ]);
  });

  it("locks same-year current-year aggregate output without revealing live stats", () => {
    const locked = buildYearEndConversationStats(
      2026,
      [
        {
          id: "upload-current",
          title: "Current-year fixture",
          createdAt: new Date("2026-05-01T00:00:00.000Z"),
          chunks: handoffChunks,
        },
      ],
      new Date("2026-12-31T23:59:59.000Z"),
    );

    expect(locked).toEqual({
      year: 2026,
      status: "locked",
      transcriptCount: 0,
      totalTurns: 0,
      totalHandoffs: 0,
      participantCount: 0,
      topSpeakerLabel: null,
      topSpeakerShare: 0,
      topBridgeLabel: null,
    });
  });

  it("reveals closed-year aggregate stats after the year boundary", () => {
    const ready = buildYearEndConversationStats(
      2025,
      [
        {
          id: "upload-closed",
          title: "Closed-year fixture",
          createdAt: new Date("2025-05-01T00:00:00.000Z"),
          chunks: handoffChunks,
        },
        {
          id: "upload-out-of-year",
          title: "Out-of-year fixture",
          createdAt: new Date("2024-05-01T00:00:00.000Z"),
          chunks: [
            {
              id: "out-of-year",
              index: 0,
              text: "This out of year transcript should not change the aggregate.",
              speakerLabel: "Zeno",
            },
          ],
        },
      ],
      new Date("2026-01-01T00:00:00.000Z"),
    );

    expect(ready.status).toBe("ready");
    expect(ready.transcriptCount).toBe(1);
    expect(ready.totalTurns).toBe(3);
    expect(ready.totalHandoffs).toBe(2);
    expect(ready.participantCount).toBe(2);
    expect(ready.topSpeakerLabel).toBe("Michael");
    expect(ready.topSpeakerShare).toBeCloseTo(17 / 25);
    expect(ready.topBridgeLabel).toBe("Michael -> Ada");
  });

  it("returns a ready zero aggregate for a closed year with no transcripts", () => {
    const ready = buildYearEndConversationStats(
      2025,
      [],
      new Date("2026-01-01T00:00:00.000Z"),
    );

    expect(ready).toEqual({
      year: 2025,
      status: "ready",
      transcriptCount: 0,
      totalTurns: 0,
      totalHandoffs: 0,
      participantCount: 0,
      topSpeakerLabel: null,
      topSpeakerShare: 0,
      topBridgeLabel: null,
    });
  });

  it("keeps a closed-year one-speaker aggregate stable without a bridge", () => {
    const ready = buildYearEndConversationStats(
      2025,
      [
        {
          id: "single-speaker",
          title: "Single speaker fixture",
          createdAt: new Date("2025-05-01T00:00:00.000Z"),
          chunks: [
            {
              id: "single-a",
              index: 0,
              text: "One speaker carries the entire short conversation.",
              speakerLabel: "Michael",
            },
            {
              id: "single-b",
              index: 1,
              text: "The second turn remains the same speaker.",
              speakerLabel: "Michael",
            },
          ],
        },
      ],
      new Date("2026-01-01T00:00:00.000Z"),
    );

    expect(ready).toMatchObject({
      year: 2025,
      status: "ready",
      transcriptCount: 1,
      totalTurns: 2,
      totalHandoffs: 0,
      participantCount: 1,
      topSpeakerLabel: "Michael",
      topBridgeLabel: null,
    });
    expect(ready.topSpeakerShare).toBe(1);
  });
});
