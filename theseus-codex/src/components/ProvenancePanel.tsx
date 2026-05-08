"use client";

import { type CSSProperties, useEffect, useRef } from "react";

import {
  bandFor,
  describeBand,
  type SentenceProvenance,
  type SentenceProvenanceReport,
  summaryForScreenReader,
} from "@/lib/sentenceProvenance";

const overlayStyle: CSSProperties = {
  background: "rgba(0, 0, 0, 0.45)",
  inset: 0,
  position: "fixed",
  zIndex: 10030,
};

const panelStyle: CSSProperties = {
  background: "var(--currents-bg-elevated, #1d1a16)",
  border: "1px solid var(--currents-border, #3a3024)",
  borderRadius: "6px",
  bottom: "auto",
  boxShadow: "0 18px 45px rgba(0, 0, 0, 0.45)",
  color: "var(--currents-parchment, #efe6d4)",
  left: "50%",
  maxHeight: "80vh",
  maxWidth: "min(560px, calc(100vw - 32px))",
  overflow: "auto",
  padding: "1.1rem 1.2rem",
  position: "fixed",
  top: "8vh",
  transform: "translateX(-50%)",
  width: "100%",
  zIndex: 10031,
};

const captionStyle: CSSProperties = {
  color: "var(--currents-muted, #948374)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.7rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
};

const rowStyle: CSSProperties = {
  borderTop: "1px solid var(--currents-border, #3a3024)",
  display: "grid",
  gap: "0.35rem 0.75rem",
  gridTemplateColumns: "auto 1fr auto",
  padding: "0.6rem 0",
};

const monoStyle: CSSProperties = {
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.78rem",
};

interface ProvenancePanelProps {
  open: boolean;
  onClose: () => void;
  sentence: SentenceProvenance | null;
  sentenceText: string;
  report: SentenceProvenanceReport;
}

function pct(value: number): string {
  return `${Math.max(0, Math.min(100, Math.round(value * 100)))}%`;
}

function verdictLabel(value: string | null): string {
  if (!value) return "—";
  const normalized = value.toLowerCase();
  if (normalized === "holds" || normalized === "true") return "supports";
  if (normalized === "refutes" || normalized === "false") return "refutes";
  return value;
}

export default function ProvenancePanel({
  open,
  onClose,
  sentence,
  sentenceText,
  report,
}: ProvenancePanelProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const focusable = dialogRef.current;
    if (focusable) focusable.focus();
  }, [open]);

  if (!open || !sentence) return null;

  const band = bandFor(sentence.provenance);
  const screenReaderSummary = summaryForScreenReader(sentence);
  const visibleSources = sentence.source_labels
    .map((label) => report.sources[label])
    .filter((c): c is NonNullable<typeof c> => Boolean(c));
  const hasPrivate = sentence.private_source_count > 0;

  return (
    <>
      <div
        aria-hidden="true"
        data-testid="provenance-panel-overlay"
        onClick={onClose}
        style={overlayStyle}
      />
      <div
        aria-labelledby="provenance-panel-title"
        aria-modal="true"
        data-testid="provenance-panel"
        ref={dialogRef}
        role="dialog"
        style={panelStyle}
        tabIndex={-1}
      >
        <div style={captionStyle}>{describeBand(band)}</div>
        <h2
          id="provenance-panel-title"
          style={{
            color: "var(--currents-parchment, #efe6d4)",
            fontFamily: "'EB Garamond', serif",
            fontSize: "1.05rem",
            lineHeight: 1.35,
            margin: "0.25rem 0 0.6rem",
          }}
        >
          Sentence provenance · {pct(sentence.provenance)}
        </h2>
        <p style={{ ...monoStyle, color: "var(--currents-muted, #948374)" }}>
          <span aria-live="polite" data-testid="provenance-panel-summary">
            {screenReaderSummary}
          </span>
        </p>
        <blockquote
          style={{
            borderLeft: "2px solid var(--currents-amber-deep, #6b4f23)",
            color: "var(--currents-parchment-dim, #d8c9ad)",
            fontFamily: "'EB Garamond', serif",
            fontSize: "0.95rem",
            lineHeight: 1.5,
            margin: "0.7rem 0 0.85rem",
            padding: "0.05rem 0 0.05rem 0.7rem",
          }}
        >
          {sentenceText}
        </blockquote>

        {visibleSources.length === 0 && !hasPrivate ? (
          <p style={{ ...monoStyle, color: "var(--currents-muted, #948374)" }}>
            No direct citations on this sentence — provenance reflects the article&apos;s overall
            evidence base.
          </p>
        ) : null}

        {visibleSources.length ? (
          <div role="list" style={{ marginTop: "0.5rem" }}>
            <div style={{ ...captionStyle, paddingBottom: "0.25rem" }}>Supporting sources</div>
            {visibleSources.map((source) => (
              <div
                data-testid="provenance-panel-source"
                key={source.label}
                role="listitem"
                style={rowStyle}
              >
                <span style={{ ...monoStyle, color: "var(--currents-amber, #d69c3f)" }}>
                  {source.label}
                </span>
                <span style={{ fontSize: "0.85rem", lineHeight: 1.4 }}>
                  {source.source_kind} · cred {pct(source.credibility)} · edge{" "}
                  {pct(source.edge_weight)}
                </span>
                <span
                  data-testid={`provenance-panel-verdict-${source.label}`}
                  style={{ ...monoStyle, color: "var(--currents-parchment-dim, #d8c9ad)" }}
                >
                  {verdictLabel(source.citation_verdict)}
                </span>
              </div>
            ))}
          </div>
        ) : null}

        {hasPrivate ? (
          <p
            data-testid="provenance-panel-private-note"
            style={{
              borderTop: "1px solid var(--currents-border, #3a3024)",
              color: "var(--currents-muted, #948374)",
              fontSize: "0.78rem",
              lineHeight: 1.5,
              margin: "0.85rem 0 0",
              paddingTop: "0.6rem",
            }}
          >
            {sentence.private_source_count} additional supporting source
            {sentence.private_source_count === 1 ? " is" : "s are"} held privately by the firm.
            Their identities are redacted from public view, but their weight is included in this
            provenance number.
          </p>
        ) : null}

        <button
          aria-label="Close provenance panel"
          onClick={onClose}
          style={{
            background: "transparent",
            border: "1px solid var(--currents-border, #3a3024)",
            borderRadius: "4px",
            color: "var(--currents-parchment-dim, #d8c9ad)",
            cursor: "pointer",
            fontSize: "0.78rem",
            marginTop: "1rem",
            padding: "0.35rem 0.75rem",
          }}
          type="button"
        >
          Close
        </button>
      </div>
    </>
  );
}
