import { gzipSync } from "node:zlib";

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  PUBLISH_WORTHY_THRESHOLD,
  SENTENCE_PROVENANCE_SCHEMA,
  bandFor,
  barColorFor,
  isWeakEvidence,
  publishThresholdFor,
  shortHash,
  summaryForScreenReader,
  weakEvidenceCount,
  type SentenceProvenanceReport,
} from "@/lib/sentenceProvenance";

// ── React hook harness ──────────────────────────────────────────────
// The polished gutter/panel are client components; we render them to
// static markup with a tiny stand-in for the three hooks they use.
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

// Three sentences spanning the band ramp AND the publish-worthy bar:
//  - strong (0.82): strong band, above the bar — no pill.
//  - moderate (0.50): moderate band, *below* the 0.55 bar — pill. This
//    is the honesty case: a "moderate-looking" sentence still flagged.
//  - weak (0.16): weak band, below the bar — pill.
const STRONG = "First sentence cites a strong source [S1].";
const MODERATE = "Second sentence rests on the shaky one [S2].";
const WEAK = "Third sentence has no markers and inherits.";
const SAMPLE_BODY = `${STRONG} ${MODERATE} ${WEAK}`;

function makeReport(): SentenceProvenanceReport {
  return {
    schema: SENTENCE_PROVENANCE_SCHEMA,
    conclusion_id: "concl-1",
    overall_provenance: 0.5,
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
        source_kind: "current_event",
        source_id: "src-beta",
        edge_weight: 0.5,
        credibility: 0.3,
        effective: 0.15,
        public: true,
        citation_verdict: "refutes",
      },
    },
    sentences: [
      {
        index: 0,
        text_hash: shortHash(STRONG),
        provenance: 0.82,
        source_labels: ["S1"],
        private_source_count: 0,
      },
      {
        index: 1,
        text_hash: shortHash(MODERATE),
        provenance: 0.5,
        source_labels: ["S2"],
        private_source_count: 1,
      },
      {
        index: 2,
        text_hash: shortHash(WEAK),
        provenance: 0.16,
        source_labels: [],
        private_source_count: 0,
      },
    ],
  };
}

afterEach(() => {
  vi.doUnmock("react");
  vi.resetModules();
});

// ── A. Visual treatment: the left-margin bar ramp ───────────────────
describe("barColorFor — parchment-dim→ember ramp (R-024)", () => {
  it("anchors at parchment-dim for full provenance and ember for zero", () => {
    // R-024: the bar ramps from `--parchment-dim` (strong) to
    // `--ember` (weak) so the soft end is discoverable on the light
    // theme. Endpoints are the RGB equivalents of those CSS vars.
    expect(barColorFor(1)).toBe("rgb(138, 129, 112)");
    expect(barColorFor(0)).toBe("rgb(172, 54, 37)");
  });

  it("ramps monotonically toward amber as provenance drops", () => {
    const red = (s: string) => Number(s.slice(4, -1).split(",")[0]);
    const strong = barColorFor(0.82);
    const moderate = barColorFor(0.5);
    const weak = barColorFor(0.16);
    // Three distinct levels, each warmer (more red) than the last.
    expect(new Set([strong, moderate, weak]).size).toBe(3);
    expect(red(strong)).toBeLessThan(red(moderate));
    expect(red(moderate)).toBeLessThan(red(weak));
  });
});

// ── A + C. Gutter snapshot: bars at three levels, pills below the bar ─
describe("ProvenanceGutter — bar + weak-evidence pill", () => {
  it("snapshot: each sentence renders a band, a provenance value, and its bar colour", async () => {
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

    for (const s of report.sentences) {
      expect(html).toContain(`data-testid="provenance-cell-${s.index}"`);
      expect(html).toContain(`data-band="${bandFor(s.provenance)}"`);
      expect(html).toContain(`data-provenance="${s.provenance.toFixed(3)}"`);
      // The bar is a thin coloured rule, not a background wash.
      expect(html).toContain(barColorFor(s.provenance));
    }
    expect(html).toContain("width:2px");
  });

  it("flags every sub-threshold sentence with a weak-evidence pill", async () => {
    const harness: Hooks = { cursor: 0, hooks: [] };
    mockReact(harness);
    const { default: ProvenanceGutter } = await import("@/components/ProvenanceGutter");

    harness.cursor = 0;
    const html = renderToStaticMarkup(
      ProvenanceGutter({
        bodyMarkdown: SAMPLE_BODY,
        report: makeReport(),
        visible: true,
      }) as React.ReactElement,
    );

    // 0.82 clears the 0.55 bar; 0.50 and 0.16 do not.
    expect(html).toMatch(
      /data-band="strong"[^>]*data-provenance="0\.820"[^>]*data-weak="false"/,
    );
    expect(html).toMatch(
      /data-band="moderate"[^>]*data-provenance="0\.500"[^>]*data-weak="true"/,
    );
    expect(html).toMatch(
      /data-band="weak"[^>]*data-provenance="0\.160"[^>]*data-weak="true"/,
    );
    // One pill per sub-threshold sentence — found without scrolling.
    const pills = html.match(/data-testid="provenance-weak-pill"/g) ?? [];
    expect(pills).toHaveLength(2);
    expect(weakEvidenceCount(makeReport())).toBe(2);
  });

  it("honours an explicit publishThreshold prop over the report default", async () => {
    const harness: Hooks = { cursor: 0, hooks: [] };
    mockReact(harness);
    const { default: ProvenanceGutter } = await import("@/components/ProvenanceGutter");

    harness.cursor = 0;
    // A very low bar: only the 0.16 sentence is now "weak".
    const html = renderToStaticMarkup(
      ProvenanceGutter({
        bodyMarkdown: SAMPLE_BODY,
        report: makeReport(),
        visible: true,
        publishThreshold: 0.2,
      }) as React.ReactElement,
    );
    const pills = html.match(/data-testid="provenance-weak-pill"/g) ?? [];
    expect(pills).toHaveLength(1);
  });
});

// ── F. a11y: a screen reader can request provenance by sentence ─────
describe("ProvenanceGutter — accessibility", () => {
  it("exposes a per-sentence summary list even when the bar is hidden", async () => {
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

    expect(html).not.toContain('data-testid="provenance-cell-0"');
    expect(html).toContain("Provenance summary");
    for (const s of report.sentences) {
      expect(html).toContain(`Sentence ${s.index + 1}:`);
      expect(html).toContain(summaryForScreenReader(s));
    }
  });

  it("gives every visible bar a textual aria-label — colour is never the only signal", async () => {
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

    for (const s of report.sentences) {
      expect(html).toContain(`Sentence ${s.index + 1}: ${summaryForScreenReader(s)}`);
    }
    expect(html).toMatch(/Strong evidence support/);
    expect(html).toMatch(/Weak evidence support/);
  });
});

// ── D. Panel redesign: a transparent receipt, not an error ──────────
describe("ProvenancePanel — provenance receipt", () => {
  async function renderPanel(
    sentenceIndex: number,
    report: SentenceProvenanceReport,
    sentenceText: string,
  ): Promise<string> {
    const harness: Hooks = { cursor: 0, hooks: [] };
    mockReact(harness);
    const { default: ProvenancePanel } = await import("@/components/ProvenancePanel");
    harness.cursor = 0;
    return renderToStaticMarkup(
      ProvenancePanel({
        open: true,
        onClose: () => {},
        sentence: report.sentences[sentenceIndex],
        sentenceText,
        report,
      }) as React.ReactElement,
    );
  }

  it("shows the sentence, its sources, cascade weight, credibility and verdict", async () => {
    const html = await renderPanel(1, makeReport(), MODERATE);

    // Reads as a receipt, not an error.
    expect(html).toContain("Provenance receipt");
    expect(html).toContain("Assembled from the firm");
    // The sentence itself.
    expect(html).toContain(MODERATE);
    // Source row: label, cascade weight, credibility, verdict.
    expect(html).toContain("Cascade weight");
    expect(html).toContain("Credibility");
    expect(html).toContain("Verdict");
    expect(html).toContain('data-testid="provenance-panel-weight-S2"');
    expect(html).toContain('data-testid="provenance-panel-cred-S2"');
    expect(html).toContain('data-testid="provenance-panel-verdict-S2"');
    expect(html).toContain(">50%<"); // edge_weight 0.5
    expect(html).toContain(">30%<"); // credibility 0.3
    expect(html).toContain(">refutes<"); // citation_verdict "refutes"
  });

  it("marks a sub-threshold sentence weak — calmly, as disclosure", async () => {
    const html = await renderPanel(1, makeReport(), MODERATE);
    expect(html).toContain('data-testid="provenance-panel-weak"');
    expect(html).toContain("weak evidence");
    expect(html).toContain("publish-worthy bar");
  });

  it("does not show a weak banner for an above-threshold sentence", async () => {
    const html = await renderPanel(0, makeReport(), STRONG);
    expect(html).not.toContain('data-testid="provenance-panel-weak"');
    expect(html).toContain("Provenance receipt");
  });

  it("counts private sources without naming them", async () => {
    // Sentence 1 carries one public source (S2) and, alongside it, a
    // private source the firm never names. The redaction note reports
    // the count; the private id/label must not appear anywhere.
    const report = makeReport();
    report.sources.SPRIV = {
      label: "SPRIV",
      source_kind: "upload",
      source_id: "PRIVATE-LEAK-CANARY",
      edge_weight: 0.8,
      credibility: 0.7,
      effective: 0.56,
      public: false,
      citation_verdict: "holds",
    };
    report.sentences[1].source_labels = ["S2", "SPRIV"];
    report.sentences[1].private_source_count = 1;

    const html = await renderPanel(1, report, MODERATE);

    expect(html).toContain('data-testid="provenance-panel-private-note"');
    expect(html).toContain("held privately by the firm");
    // The public source still shows; the private one is fully redacted.
    expect(html).toContain('data-testid="provenance-panel-source"');
    expect(html).toContain("S2");
    expect(html).not.toContain("PRIVATE-LEAK-CANARY");
    expect(html).not.toContain("SPRIV");
  });
});

// ── E. Performance: inline provenance overhead stays small ──────────
describe("provenance payload size", () => {
  it("a 3,000-word article ships its provenance report well under 25KB gzipped", () => {
    // ~3,000 words at ~18 words/sentence ≈ 170 sentences.
    const sentences = Array.from({ length: 170 }, (_, i) => ({
      index: i,
      text_hash: shortHash(`sentence-${i}`),
      provenance: 0.3 + (i % 7) * 0.1,
      source_labels: i % 2 === 0 ? [`S${(i % 12) + 1}`] : [],
      private_source_count: i % 5 === 0 ? 1 : 0,
    }));
    const sources: SentenceProvenanceReport["sources"] = {};
    for (let i = 1; i <= 12; i++) {
      sources[`S${i}`] = {
        label: `S${i}`,
        source_kind: "upload",
        source_id: `source-artifact-${i}`,
        edge_weight: 0.7,
        credibility: 0.6,
        effective: 0.42,
        public: true,
        citation_verdict: "holds",
      };
    }
    const report: SentenceProvenanceReport = {
      schema: SENTENCE_PROVENANCE_SCHEMA,
      conclusion_id: "perf-3000",
      overall_provenance: 0.55,
      publish_threshold: PUBLISH_WORTHY_THRESHOLD,
      sources,
      sentences,
    };

    const gzipped = gzipSync(Buffer.from(JSON.stringify(report), "utf-8"));
    expect(gzipped.byteLength).toBeLessThan(25 * 1024);
  });
});

// ── C. Threshold honesty helpers ────────────────────────────────────
describe("publish-worthy threshold helpers", () => {
  it("publishThresholdFor honours a sane report override and falls back otherwise", () => {
    expect(publishThresholdFor({ publish_threshold: 0.7 })).toBe(0.7);
    expect(publishThresholdFor({})).toBe(PUBLISH_WORTHY_THRESHOLD);
    expect(publishThresholdFor(null)).toBe(PUBLISH_WORTHY_THRESHOLD);
    // Out-of-range overrides are ignored.
    expect(publishThresholdFor({ publish_threshold: 1.5 })).toBe(PUBLISH_WORTHY_THRESHOLD);
    expect(publishThresholdFor({ publish_threshold: 0 })).toBe(PUBLISH_WORTHY_THRESHOLD);
  });

  it("isWeakEvidence is a strict below-the-bar test", () => {
    expect(isWeakEvidence(0.54)).toBe(true);
    expect(isWeakEvidence(PUBLISH_WORTHY_THRESHOLD)).toBe(false);
    expect(isWeakEvidence(0.9)).toBe(false);
    expect(isWeakEvidence(Number.NaN)).toBe(true);
    expect(isWeakEvidence(0.4, 0.3)).toBe(false);
  });

  it("weakEvidenceCount totals the sub-threshold sentences", () => {
    expect(weakEvidenceCount(makeReport())).toBe(2);
    expect(weakEvidenceCount(makeReport(), 0.1)).toBe(0);
  });
});
