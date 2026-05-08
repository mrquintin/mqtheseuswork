import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SENTENCE_PROVENANCE_SCHEMA,
  bandFor,
  fallbackReport,
  reportMatchesBody,
  shortHash,
  splitSentences,
  summaryForScreenReader,
  type SentenceProvenanceReport,
} from "@/lib/sentenceProvenance";

interface Hooks {
  cursor: number;
  hooks: unknown[];
}

function mockReact(harness: Hooks) {
  vi.doMock("react", async () => {
    const actual = await vi.importActual<typeof import("react")>("react");
    return {
      ...actual,
      useEffect: () => {
        harness.cursor += 1;
      },
      useRef: <T,>(initial: T) => {
        const index = harness.cursor++;
        if (!harness.hooks[index]) harness.hooks[index] = { current: initial };
        return harness.hooks[index];
      },
      useState: <T,>(initial: T | (() => T)) => {
        const index = harness.cursor++;
        if (!(index in harness.hooks)) {
          harness.hooks[index] =
            typeof initial === "function" ? (initial as () => T)() : initial;
        }
        return [harness.hooks[index] as T, () => {}] as const;
      },
    };
  });
}

function makeReport(): SentenceProvenanceReport {
  // Three sentences: one strong (alpha), one weak (beta), one inheriting overall.
  const strong = "First sentence cites a strong source [S1].";
  const weak = "Second sentence rests on the shaky one [S2].";
  const ambient = "Third sentence has no markers and inherits.";
  return {
    schema: SENTENCE_PROVENANCE_SCHEMA,
    conclusion_id: "concl-1",
    overall_provenance: 0.55,
    sources: {
      S1: {
        label: "S1",
        source_kind: "upload",
        source_id: "src-alpha",
        edge_weight: 0.9,
        credibility: 0.85,
        effective: 0.765,
        public: true,
        citation_verdict: "holds",
      },
      S2: {
        label: "S2",
        source_kind: "upload",
        source_id: "src-beta",
        edge_weight: 0.5,
        credibility: 0.2,
        effective: 0.1,
        public: true,
        citation_verdict: null,
      },
    },
    sentences: [
      {
        index: 0,
        text_hash: shortHash(strong),
        provenance: 0.78,
        source_labels: ["S1"],
        private_source_count: 0,
      },
      {
        index: 1,
        text_hash: shortHash(weak),
        provenance: 0.18,
        source_labels: ["S2"],
        private_source_count: 1,
      },
      {
        index: 2,
        text_hash: shortHash(ambient),
        provenance: 0.5,
        source_labels: [],
        private_source_count: 0,
      },
    ],
  };
}

const SAMPLE_BODY =
  "First sentence cites a strong source [S1]. Second sentence rests on the shaky one [S2]. Third sentence has no markers and inherits.";

afterEach(() => {
  vi.doUnmock("react");
  vi.resetModules();
});

describe("sentenceProvenance helpers", () => {
  it("splits markdown into sentences and extracts citation labels", () => {
    const sentences = splitSentences(SAMPLE_BODY);
    expect(sentences.map((s) => s.labels)).toEqual([["S1"], ["S2"], []]);
    expect(sentences).toHaveLength(3);
  });

  it("matches band thresholds: weak < 0.35 ≤ moderate < 0.6 ≤ strong", () => {
    expect(bandFor(0.1)).toBe("weak");
    expect(bandFor(0.5)).toBe("moderate");
    expect(bandFor(0.9)).toBe("strong");
  });

  it("rejects a report whose sentence count diverges from the body", () => {
    const report = makeReport();
    expect(reportMatchesBody(report, SAMPLE_BODY)).toBe(true);
    expect(reportMatchesBody(report, "Only one sentence here.")).toBe(false);
  });

  it("falls back conservatively when no precomputed report is available", () => {
    const fb = fallbackReport("concl-2", SAMPLE_BODY, [
      {
        label: "S1",
        sourceKind: "upload",
        sourceId: "src-alpha",
        quotedSpan: "...",
        publicUrl: "/c/x/v/1",
        linkable: true,
        sourceConclusionText: null,
        sourceConclusionTitle: null,
      },
    ]);
    expect(fb.sentences).toHaveLength(3);
    // Cited sentences get 0.5; uncited gets 0.4 — strictly weaker than
    // the heatmap of a real report, by design.
    expect(fb.sentences[0].provenance).toBe(0.5);
    expect(fb.sentences[2].provenance).toBe(0.4);
  });
});

describe("ProvenanceGutter", () => {
  it("snapshot: report data round-trips through the rendered gutter cells", async () => {
    const harness: Hooks = { cursor: 0, hooks: [] };
    mockReact(harness);
    const { default: ProvenanceGutter } = await import("@/components/ProvenanceGutter");

    const report = makeReport();
    harness.cursor = 0;
    const html = renderToStaticMarkup(
      ProvenanceGutter({
        bodyMarkdown: SAMPLE_BODY,
        report,
        visible: true,
      }) as React.ReactElement,
    );

    // One cell per sentence — the heatmap data round-trips through the
    // article view: sentence count and per-cell provenance match the
    // input report.
    for (const sentence of report.sentences) {
      expect(html).toContain(`data-testid="provenance-cell-${sentence.index}"`);
      expect(html).toContain(`data-band="${bandFor(sentence.provenance)}"`);
      expect(html).toContain(
        `data-provenance="${sentence.provenance.toFixed(3)}"`,
      );
    }
  });

  it("a11y: shading is not the only signal — every cell has a textual aria-label", async () => {
    const harness: Hooks = { cursor: 0, hooks: [] };
    mockReact(harness);
    const { default: ProvenanceGutter } = await import("@/components/ProvenanceGutter");

    const report = makeReport();
    harness.cursor = 0;
    const html = renderToStaticMarkup(
      ProvenanceGutter({
        bodyMarkdown: SAMPLE_BODY,
        report,
        visible: true,
      }) as React.ReactElement,
    );

    for (const sentence of report.sentences) {
      const summary = summaryForScreenReader(sentence);
      expect(html).toContain(summary);
    }
    // The strong/moderate/weak band words must appear in the aria-label
    // text — this is the redundant textual channel that prevents the
    // shading from being the sole information carrier.
    expect(html).toMatch(/Strong evidence support/);
    expect(html).toMatch(/Weak evidence support/);
  });

  it("hidden gutter still exposes a screen-reader provenance summary", async () => {
    const harness: Hooks = { cursor: 0, hooks: [] };
    mockReact(harness);
    const { default: ProvenanceGutter } = await import("@/components/ProvenanceGutter");

    const report = makeReport();
    harness.cursor = 0;
    const html = renderToStaticMarkup(
      ProvenanceGutter({
        bodyMarkdown: SAMPLE_BODY,
        report,
        visible: false,
      }) as React.ReactElement,
    );

    // No interactive cells when hidden, but the summary list is still
    // present so a screen reader can request "provenance summary for
    // this sentence".
    expect(html).not.toContain('data-testid="provenance-cell-0"');
    expect(html).toContain("Provenance summary");
    expect(html).toContain("Sentence 1");
  });

  it("perf: a 5,000-word synthetic article fits within the gutter render budget", () => {
    // Mirrors the Python perf test. The gutter ships a JSON payload
    // alongside HTML; we cap the *serialised* payload at 25KB gzipped
    // on the server, which we approximate here by checking the raw
    // JSON length stays well under the post-gzip cliff (≈3× headroom).
    const sentences = Array.from({ length: 250 }, (_, i) => ({
      index: i,
      text_hash: shortHash(`sentence ${i}`),
      provenance: 0.4 + ((i % 5) * 0.1),
      source_labels: i % 2 === 0 ? [`S${(i % 3) + 1}`] : [],
      private_source_count: 0,
    }));
    const report: SentenceProvenanceReport = {
      schema: SENTENCE_PROVENANCE_SCHEMA,
      conclusion_id: "perf",
      overall_provenance: 0.5,
      sources: {
        S1: {
          label: "S1",
          source_kind: "upload",
          source_id: "src-1",
          edge_weight: 0.8,
          credibility: 0.7,
          effective: 0.56,
          public: true,
          citation_verdict: null,
        },
      },
      sentences,
    };
    const blob = JSON.stringify(report);
    expect(blob.length).toBeLessThan(80 * 1024);
  });
});
