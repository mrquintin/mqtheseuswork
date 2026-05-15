import Link from "next/link";

import {
  READER_GUIDE_STEPS,
  currentTourStep,
  tourProgressLabel,
  type TourState,
} from "@/lib/readerTour";

// The last stop's index — used only to label the advance button.
const READER_GUIDE_LAST_INDEX = READER_GUIDE_STEPS.length - 1;

/**
 * The reading-tour overlay — a small dismissible panel that explains
 * what the reader is looking at at each stop of the guide.
 *
 * Presentational only: it takes the tour state and a set of callbacks
 * and renders. All transitions live in `tourReducer`; all state lives
 * in <ReaderTour>. Keeping this component handler-driven and pure is
 * what lets the snapshot test render it with no-op callbacks.
 *
 * It renders nothing while the tour is `idle` or `dismissed` — the
 * overlay only exists once a reader opts in, and it leaves no residue
 * when dismissed.
 */

export type ReaderTourOverlayProps = {
  state: TourState;
  onNext: () => void;
  onPrev: () => void;
  onDismiss: () => void;
  onRestart: () => void;
  onExport: () => void;
};

export default function ReaderTourOverlay({
  state,
  onNext,
  onPrev,
  onDismiss,
  onRestart,
  onExport,
}: ReaderTourOverlayProps) {
  if (state.status === "idle" || state.status === "dismissed") return null;

  const step = currentTourStep(state);
  const complete = state.status === "complete";

  return (
    <div
      aria-label="Reading tour"
      aria-live="polite"
      data-testid="reader-tour-overlay"
      data-tour-status={state.status}
      role="dialog"
      style={overlayStyle}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
        <p className="mono" style={eyebrowStyle}>
          {complete ? "Tour complete" : tourProgressLabel(state)}
        </p>
        <button
          aria-label="Dismiss the reading tour"
          data-testid="reader-tour-dismiss"
          onClick={onDismiss}
          style={dismissStyle}
          type="button"
        >
          Dismiss ✕
        </button>
      </div>

      {complete ? (
        <>
          <p style={bodyStyle}>
            You&apos;ve completed the tour. This changes nothing — no badge, no
            gate, no access you did not already have. It is only a record, and
            only if you want one.
          </p>
          <div style={actionsStyle}>
            <button
              data-testid="reader-tour-export"
              onClick={onExport}
              style={primaryButtonStyle}
              type="button"
            >
              Export tour record
            </button>
            <button
              data-testid="reader-tour-restart"
              onClick={onRestart}
              style={secondaryButtonStyle}
              type="button"
            >
              Restart tour
            </button>
          </div>
        </>
      ) : step ? (
        <>
          <h2 style={titleStyle}>{step.title}</h2>
          <p style={bodyStyle}>{step.tourNote}</p>
          <ul style={linkListStyle}>
            {step.links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  rel={link.external ? "noreferrer" : undefined}
                  style={stepLinkStyle}
                  target={link.external ? "_blank" : undefined}
                >
                  {link.label} →
                </Link>
              </li>
            ))}
          </ul>
          <div style={actionsStyle}>
            <button
              data-testid="reader-tour-prev"
              disabled={state.stepIndex === 0}
              onClick={onPrev}
              style={secondaryButtonStyle}
              type="button"
            >
              ← Previous
            </button>
            <button
              data-testid="reader-tour-next"
              onClick={onNext}
              style={primaryButtonStyle}
              type="button"
            >
              {state.stepIndex >= READER_GUIDE_LAST_INDEX ? "Finish tour" : "Next →"}
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  right: "1.25rem",
  bottom: "1.25rem",
  zIndex: 200,
  maxWidth: "min(28rem, calc(100vw - 2.5rem))",
  background: "var(--public-bg-soft, #14140f)",
  border: "1px solid var(--amber, #d4a017)",
  borderRadius: "6px",
  padding: "1rem 1.1rem",
  boxShadow: "0 12px 40px rgba(0, 0, 0, 0.45)",
};

const eyebrowStyle: React.CSSProperties = {
  fontSize: "0.6rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--amber, #d4a017)",
  margin: 0,
};

const dismissStyle: React.CSSProperties = {
  background: "transparent",
  border: 0,
  color: "var(--public-muted, #999)",
  cursor: "pointer",
  fontSize: "0.7rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  padding: 0,
};

const titleStyle: React.CSSProperties = {
  fontSize: "1.05rem",
  lineHeight: 1.25,
  margin: "0.55rem 0 0",
  color: "var(--public-fg, #e8e1d3)",
};

const bodyStyle: React.CSSProperties = {
  fontSize: "0.9rem",
  lineHeight: 1.55,
  margin: "0.5rem 0 0",
  color: "var(--public-fg, #e8e1d3)",
};

const linkListStyle: React.CSSProperties = {
  listStyle: "none",
  padding: 0,
  margin: "0.7rem 0 0",
  display: "grid",
  gap: "0.3rem",
};

const stepLinkStyle: React.CSSProperties = {
  fontSize: "0.85rem",
  color: "var(--amber, #d4a017)",
  textDecoration: "none",
};

const actionsStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.5rem",
  marginTop: "0.9rem",
};

const primaryButtonStyle: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  fontFamily: "inherit",
  fontSize: "0.72rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  border: "1px solid var(--amber, #d4a017)",
  background: "var(--amber, #d4a017)",
  color: "#120d08",
  cursor: "pointer",
};

const secondaryButtonStyle: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  fontFamily: "inherit",
  fontSize: "0.72rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  border: "1px solid var(--public-rule, #444)",
  background: "transparent",
  color: "var(--public-fg, #e8e1d3)",
  cursor: "pointer",
};
