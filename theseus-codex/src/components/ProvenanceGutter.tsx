"use client";

import { type CSSProperties, useState } from "react";

import {
  bandFor,
  describeBand,
  splitSentences,
  summaryForScreenReader,
  tintFor,
  type SentenceProvenanceReport,
} from "@/lib/sentenceProvenance";

import ProvenancePanel from "./ProvenancePanel";

interface ProvenanceGutterProps {
  bodyMarkdown: string;
  report: SentenceProvenanceReport;
  visible: boolean;
  /** Optional debug id used by tests to scope queries. */
  testId?: string;
}

const gutterContainerStyle: CSSProperties = {
  display: "grid",
  gap: "0.6rem",
  // Two columns: a thin gutter strip, then the article body slot
  // managed by the parent. The component renders ONLY the gutter so
  // the article body keeps its existing typography.
  gridTemplateColumns: "10px 1fr",
  position: "relative",
};

const cellBaseStyle: CSSProperties = {
  borderRadius: "2px",
  cursor: "pointer",
  height: "1.5rem",
  margin: 0,
  padding: 0,
  width: "10px",
};

const srOnly: CSSProperties = {
  border: 0,
  clip: "rect(0 0 0 0)",
  height: "1px",
  margin: "-1px",
  overflow: "hidden",
  padding: 0,
  position: "absolute",
  whiteSpace: "nowrap",
  width: "1px",
};

/**
 * Renders the gutter shading next to an article body. The shading
 * does not carry any meaning that is not also available textually —
 * each cell is a focusable button whose aria-label states the
 * provenance band and number, and which opens a panel listing the
 * supporting sources on activation.
 *
 * The gutter prefers to read the precomputed report (shipped with
 * article HTML) but the parent can also pass a fallback report. In
 * either case sentences are matched to gutter cells by index.
 */
export default function ProvenanceGutter({
  bodyMarkdown,
  report,
  visible,
  testId,
}: ProvenanceGutterProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const sentenceTexts = splitSentences(bodyMarkdown).map((s) => s.text);
  const sentences = report.sentences.slice(0, sentenceTexts.length);

  if (!visible) {
    // Even when hidden we leave a screen-reader-only summary so a
    // keyboard-only reader can still ask for "provenance summary for
    // this sentence" without flipping the visual toggle on.
    return (
      <div data-testid={testId ?? "provenance-gutter"} style={srOnly}>
        <h3>Provenance summary</h3>
        <ul>
          {sentences.map((s, idx) => (
            <li key={`prov-summary-${s.text_hash}-${idx}`}>
              Sentence {idx + 1}: {summaryForScreenReader(s)}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const activeSentence = activeIndex !== null ? sentences[activeIndex] ?? null : null;
  const activeText = activeIndex !== null ? sentenceTexts[activeIndex] ?? "" : "";

  return (
    <div
      aria-label="Sentence provenance heatmap"
      data-testid={testId ?? "provenance-gutter"}
      role="group"
      style={gutterContainerStyle}
    >
      <div
        aria-orientation="vertical"
        role="list"
        style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}
      >
        {sentences.map((s, idx) => {
          const band = bandFor(s.provenance);
          const tint = tintFor(band);
          const summary = summaryForScreenReader(s);
          return (
            <button
              aria-label={`Sentence ${idx + 1}: ${summary}`}
              data-band={band}
              data-provenance={s.provenance.toFixed(3)}
              data-testid={`provenance-cell-${idx}`}
              key={`prov-cell-${s.text_hash}-${idx}`}
              onClick={() => setActiveIndex(idx)}
              role="listitem"
              style={{
                ...cellBaseStyle,
                background: tint,
                border: `1px solid ${tint}`,
              }}
              title={`${describeBand(band)} · ${Math.round(s.provenance * 100)}/100`}
              type="button"
            >
              <span style={srOnly}>{summary}</span>
            </button>
          );
        })}
      </div>
      <div aria-hidden="true" />

      <ProvenancePanel
        onClose={() => setActiveIndex(null)}
        open={activeSentence !== null}
        report={report}
        sentence={activeSentence}
        sentenceText={activeText}
      />
    </div>
  );
}
