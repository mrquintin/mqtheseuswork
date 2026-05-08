"use client";

import { type CSSProperties, useEffect, useState } from "react";

import {
  markFirstUseTipShown,
  readToggle,
  shouldShowFirstUseTip,
  writeToggle,
  type SentenceProvenanceReport,
} from "@/lib/sentenceProvenance";

import AnswerMarkdown from "./AnswerMarkdown";
import ProvenanceGutter from "./ProvenanceGutter";

interface ProvenanceArticleProps {
  bodyMarkdown: string;
  report: SentenceProvenanceReport;
}

const layoutStyle: CSSProperties = {
  display: "grid",
  gap: "0.85rem",
  gridTemplateColumns: "auto 1fr",
};

const toolbarStyle: CSSProperties = {
  alignItems: "center",
  display: "flex",
  gap: "0.55rem",
  marginBottom: "0.55rem",
};

const toggleButtonStyle: CSSProperties = {
  background: "transparent",
  border: "1px solid var(--currents-border, #3a3024)",
  borderRadius: "999px",
  color: "var(--currents-parchment-dim, #d8c9ad)",
  cursor: "pointer",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.72rem",
  letterSpacing: "0.06em",
  padding: "0.25rem 0.7rem",
};

const tipStyle: CSSProperties = {
  background: "var(--currents-bg-elevated, #1d1a16)",
  border: "1px solid var(--currents-amber-deep, #6b4f23)",
  borderRadius: "4px",
  color: "var(--currents-parchment-dim, #d8c9ad)",
  fontSize: "0.78rem",
  lineHeight: 1.45,
  marginBottom: "0.6rem",
  padding: "0.5rem 0.7rem",
};

/**
 * Article-body wrapper that renders the markdown body alongside the
 * provenance gutter. Keeps the toggle state local-only so the parent
 * (a server component) need not be turned into a client component.
 */
export default function ProvenanceArticle({
  bodyMarkdown,
  report,
}: ProvenanceArticleProps) {
  const [visible, setVisible] = useState<boolean>(false);
  const [showTip, setShowTip] = useState<boolean>(false);

  useEffect(() => {
    setVisible(readToggle());
    setShowTip(shouldShowFirstUseTip());
  }, []);

  const onToggle = () => {
    setVisible((prev) => {
      const next = !prev;
      writeToggle(next);
      if (next && showTip) {
        markFirstUseTipShown();
        setShowTip(false);
      }
      return next;
    });
  };

  return (
    <div data-testid="provenance-article">
      <div role="toolbar" style={toolbarStyle}>
        <button
          aria-pressed={visible}
          data-testid="provenance-toggle"
          onClick={onToggle}
          style={{
            ...toggleButtonStyle,
            background: visible ? "rgba(214, 156, 63, 0.18)" : "transparent",
            color: visible
              ? "var(--currents-amber, #d69c3f)"
              : "var(--currents-parchment-dim, #d8c9ad)",
          }}
          type="button"
        >
          {visible ? "Hide provenance" : "Show provenance"}
        </button>
        <span
          aria-hidden="true"
          style={{
            color: "var(--currents-muted, #948374)",
            fontSize: "0.72rem",
          }}
        >
          gutter shades sentences by evidence weight
        </span>
      </div>

      {visible && showTip ? (
        <div data-testid="provenance-tip" role="note" style={tipStyle}>
          The gutter shades each sentence by the strength of its supporting evidence.
          Click a faintly-shaded cell to see which sources carry that sentence.
        </div>
      ) : null}

      <div style={layoutStyle}>
        <ProvenanceGutter
          bodyMarkdown={bodyMarkdown}
          report={report}
          visible={visible}
        />
        <div className="public-article-body">
          <AnswerMarkdown>{bodyMarkdown}</AnswerMarkdown>
        </div>
      </div>

      {/* Mobile-only sticky toolbar — keeps the provenance toggle reachable
          while reading. Hidden on desktop via the `.public-mobile-toolbar`
          rule in globals.css. */}
      <div
        className="public-mobile-toolbar"
        data-testid="provenance-mobile-toolbar"
        role="toolbar"
      >
        <button
          aria-pressed={visible}
          data-testid="provenance-toggle-mobile"
          onClick={onToggle}
          style={{
            ...toggleButtonStyle,
            background: visible ? "rgba(214, 156, 63, 0.18)" : "transparent",
            color: visible
              ? "var(--currents-amber, #d69c3f)"
              : "var(--currents-parchment-dim, #d8c9ad)",
          }}
          type="button"
        >
          {visible ? "Hide provenance" : "Show provenance"}
        </button>
      </div>
    </div>
  );
}
