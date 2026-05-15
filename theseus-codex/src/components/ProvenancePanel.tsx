"use client";

import { type CSSProperties, useEffect, useRef } from "react";

import {
  isWeakEvidence,
  publishThresholdFor,
  type SentenceProvenance,
  type SentenceProvenanceReport,
  summaryForScreenReader,
} from "@/lib/sentenceProvenance";

import ProvenanceWeakPill from "./ProvenanceWeakPill";

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

// A receipt-like four-column ledger: source, the cascade edge weight,
// the source's credibility, and the citation verdict.
const sourceGrid: CSSProperties = {
  display: "grid",
  gap: "0.35rem 0.85rem",
  gridTemplateColumns: "minmax(0, 1.4fr) auto auto auto",
};

const headerRowStyle: CSSProperties = {
  ...captionStyle,
  ...sourceGrid,
  fontSize: "0.62rem",
  paddingBottom: "0.35rem",
};

const rowStyle: CSSProperties = {
  ...sourceGrid,
  borderTop: "1px solid var(--currents-border, #3a3024)",
  padding: "0.5rem 0",
};

const monoStyle: CSSProperties = {
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.78rem",
};

const weakBannerStyle: CSSProperties = {
  alignItems: "center",
  background: "rgba(214, 156, 63, 0.10)",
  borderLeft: "2px solid var(--currents-amber-deep, #6b4f23)",
  borderRadius: "2px",
  color: "var(--currents-parchment-dim, #d8c9ad)",
  display: "flex",
  flexWrap: "wrap",
  fontSize: "0.8rem",
  gap: "0.5rem",
  lineHeight: 1.45,
  margin: "0.6rem 0 0.2rem",
  padding: "0.5rem 0.6rem",
};

interface ProvenancePanelProps {
  open: boolean;
  onClose: () => void;
  sentence: SentenceProvenance | null;
  sentenceText: string;
  report: SentenceProvenanceReport;
  /** Firm's publish-worthy bar; defaults to the report's threshold. */
  publishThreshold?: number;
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

/**
 * The provenance panel: a transparent receipt for one sentence. It
 * shows the sentence itself, then every public source behind it with
 * the cascade edge weight, the source's credibility, and the citation
 * verdict. When the sentence falls below the firm's publish-worthy
 * bar the panel says so plainly — calmly, as disclosure, not as an
 * error state.
 *
 * Private sources are never named here: they raise the provenance
 * number and are counted in the redaction note, but their identity
 * stays with the firm.
 *
 * The panel renders nothing until `open`, so its markup hydrates only
 * once a reader clicks a bar — the provenance *data* ships inline with
 * the article, the panel UI does not.
 */
export default function ProvenancePanel({
  open,
  onClose,
  sentence,
  sentenceText,
  report,
  publishThreshold,
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

  const threshold = publishThreshold ?? publishThresholdFor(report);
  const weak = isWeakEvidence(sentence.provenance, threshold);
  const screenReaderSummary = summaryForScreenReader(sentence);
  // The upstream public projection already drops private sources from
  // `report.sources`; we also filter on `public` here so a private
  // identity cannot reach the panel even if a future serialisation
  // path forgets to project. Their weight still rides in the score.
  const visibleSources = sentence.source_labels
    .map((label) => report.sources[label])
    .filter((c): c is NonNullable<typeof c> => Boolean(c) && c.public);
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
        <div style={captionStyle}>Provenance receipt</div>
        <h2
          id="provenance-panel-title"
          style={{
            color: "var(--currents-parchment, #efe6d4)",
            fontFamily: "'EB Garamond', serif",
            fontSize: "1.05rem",
            lineHeight: 1.35,
            margin: "0.25rem 0 0.2rem",
          }}
        >
          What carries this sentence · {pct(sentence.provenance)}
        </h2>

        {weak ? (
          <div data-testid="provenance-panel-weak" role="note" style={weakBannerStyle}>
            <ProvenanceWeakPill variant="label" />
            <span>
              Below the firm&apos;s publish-worthy bar ({pct(threshold)}). The firm
              published this sentence anyway — here is exactly what supports it.
            </span>
          </div>
        ) : null}

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
            No direct citations on this sentence — its provenance reflects the
            article&apos;s overall evidence base.
          </p>
        ) : null}

        {visibleSources.length ? (
          <div data-testid="provenance-panel-sources" role="table" style={{ marginTop: "0.5rem" }}>
            <div style={{ ...captionStyle, paddingBottom: "0.1rem" }}>Supporting sources</div>
            <div role="row" style={headerRowStyle}>
              <span>Source</span>
              <span>Cascade weight</span>
              <span>Credibility</span>
              <span>Verdict</span>
            </div>
            {visibleSources.map((source) => (
              <div
                data-testid="provenance-panel-source"
                key={source.label}
                role="row"
                style={rowStyle}
              >
                <span style={{ ...monoStyle, color: "var(--currents-amber, #d69c3f)" }}>
                  {source.label}
                  <span style={{ color: "var(--currents-muted, #948374)" }}>
                    {" "}
                    · {source.source_kind}
                  </span>
                </span>
                <span
                  data-testid={`provenance-panel-weight-${source.label}`}
                  style={{ ...monoStyle, color: "var(--currents-parchment-dim, #d8c9ad)" }}
                >
                  {pct(source.edge_weight)}
                </span>
                <span
                  data-testid={`provenance-panel-cred-${source.label}`}
                  style={{ ...monoStyle, color: "var(--currents-parchment-dim, #d8c9ad)" }}
                >
                  {pct(source.credibility)}
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

        <p
          data-testid="provenance-panel-footer"
          style={{
            color: "var(--currents-muted, #948374)",
            fontSize: "0.72rem",
            lineHeight: 1.5,
            margin: "0.85rem 0 0",
          }}
        >
          Assembled from the firm&apos;s cascade graph at publish time — every public
          source behind this sentence is listed above.
        </p>

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
