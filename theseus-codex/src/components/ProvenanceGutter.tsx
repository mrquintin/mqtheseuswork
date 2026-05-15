"use client";

import { type CSSProperties, useState } from "react";

import {
  bandFor,
  barColorFor,
  describeBand,
  isWeakEvidence,
  publishThresholdFor,
  splitSentences,
  summaryForScreenReader,
  type SentenceProvenanceReport,
} from "@/lib/sentenceProvenance";

import ProvenancePanel from "./ProvenancePanel";
import ProvenanceWeakPill from "./ProvenanceWeakPill";

interface ProvenanceGutterProps {
  bodyMarkdown: string;
  report: SentenceProvenanceReport;
  visible: boolean;
  /**
   * Firm's publish-worthy provenance bar. Sentences below it carry a
   * "weak evidence" pill. Optional — defaults to the threshold the
   * report ships, or the library constant.
   */
  publishThreshold?: number;
  /** Optional debug id used by tests to scope queries. */
  testId?: string;
}

// The gutter is a narrow left-margin strip. Each sentence gets a 2px
// bar; weak sentences additionally get a pill, so the strip stays
// slim but has room for the marker.
const GUTTER_WIDTH = "18px";

const listStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.35rem",
  width: GUTTER_WIDTH,
};

const segmentStyle: CSSProperties = {
  alignItems: "center",
  background: "transparent",
  border: "none",
  borderRadius: "2px",
  cursor: "pointer",
  display: "flex",
  gap: "3px",
  height: "1.5rem",
  margin: 0,
  padding: 0,
  width: GUTTER_WIDTH,
};

const barBaseStyle: CSSProperties = {
  alignSelf: "stretch",
  borderRadius: "1px",
  flex: "none",
  // R-024: 2 px minimum width. The previous 1 px was approximately
  // invisible on light theme at the strong-evidence end of the ramp.
  // 2 px keeps the rule slim without becoming a wash.
  width: "2px",
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
 * Renders the provenance gutter beside an article body: one thin
 * left-margin bar per sentence, its colour ramping from a near-neutral
 * margin tone at full provenance toward amber as provenance drops.
 *
 * The bar never carries meaning that is not also available textually —
 * each segment is a focusable button whose aria-label states the
 * provenance band, the number, and the supporting-source count, and
 * which opens the provenance panel on activation. Sentences below the
 * firm's publish-worthy threshold also get a "weak evidence" pill so a
 * reader can find the article's softest claims by scanning the margin.
 *
 * When the toolbar toggle hides the gutter we still emit a
 * screen-reader-only summary list, so a keyboard/AT reader can request
 * a per-sentence provenance summary without flipping the visual bar on.
 */
export default function ProvenanceGutter({
  bodyMarkdown,
  report,
  visible,
  publishThreshold,
  testId,
}: ProvenanceGutterProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const sentenceTexts = splitSentences(bodyMarkdown).map((s) => s.text);
  const sentences = report.sentences.slice(0, sentenceTexts.length);
  const threshold = publishThreshold ?? publishThresholdFor(report);

  if (!visible) {
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
    >
      <div aria-orientation="vertical" role="list" style={listStyle}>
        {sentences.map((s, idx) => {
          const band = bandFor(s.provenance);
          const weak = isWeakEvidence(s.provenance, threshold);
          const summary = summaryForScreenReader(s);
          return (
            <button
              aria-label={`Sentence ${idx + 1}: ${summary}`}
              data-band={band}
              data-provenance={s.provenance.toFixed(3)}
              data-testid={`provenance-cell-${idx}`}
              data-weak={weak ? "true" : "false"}
              key={`prov-cell-${s.text_hash}-${idx}`}
              onClick={() => setActiveIndex(idx)}
              role="listitem"
              style={segmentStyle}
              title={`${describeBand(band)} · ${Math.round(s.provenance * 100)}/100${
                weak ? " · weak evidence" : ""
              }`}
              type="button"
            >
              <span
                aria-hidden="true"
                style={{ ...barBaseStyle, background: barColorFor(s.provenance) }}
              />
              {weak ? <ProvenanceWeakPill variant="marker" /> : null}
              <span style={srOnly}>{summary}</span>
            </button>
          );
        })}
      </div>

      {/* The panel is rendered only when a bar is activated — closed it
          returns null, so nothing of it hydrates until the click. */}
      <ProvenancePanel
        onClose={() => setActiveIndex(null)}
        open={activeSentence !== null}
        publishThreshold={threshold}
        report={report}
        sentence={activeSentence}
        sentenceText={activeText}
      />
    </div>
  );
}
