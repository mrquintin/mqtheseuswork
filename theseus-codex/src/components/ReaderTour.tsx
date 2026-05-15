"use client";

import { useReducer, useState } from "react";

import ReaderTourOverlay from "./ReaderTourOverlay";
import {
  INITIAL_TOUR_STATE,
  exportTourRecord,
  tourReducer,
} from "@/lib/readerTour";

/**
 * "Tour me" entry point for the reader guide.
 *
 * Holds the tour state via `tourReducer` and renders the dismissible
 * <ReaderTourOverlay>. The button is the only always-visible chrome;
 * everything else appears once the reader opts in and disappears the
 * moment they dismiss.
 *
 * Completing the tour produces a state whose only effect is the
 * exportable record — the file written by "Export tour record". It
 * gates nothing: no badge, no unlocked surface. A reader who never
 * presses the button reads exactly the same guide.
 */
export default function ReaderTour() {
  const [state, dispatch] = useReducer(tourReducer, INITIAL_TOUR_STATE);
  const [exported, setExported] = useState(false);

  function handleExport() {
    const record = exportTourRecord(state);
    if (!record) return;

    if (typeof window === "undefined") return;
    const blob = new Blob([JSON.stringify(record, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "theseus-reader-tour.json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setExported(true);
  }

  const tourRunning = state.status === "active" || state.status === "complete";

  return (
    <div data-testid="reader-tour">
      <button
        aria-pressed={tourRunning}
        data-testid="reader-tour-start"
        onClick={() => dispatch({ type: state.status === "idle" ? "start" : "restart" })}
        style={startButtonStyle}
        type="button"
      >
        {state.status === "idle" ? "Tour me" : "Restart the tour"}
      </button>
      {state.status === "dismissed" ? (
        <span data-testid="reader-tour-dismissed-note" style={noteStyle}>
          Tour dismissed. The guide below is unchanged — press the button to
          walk it again.
        </span>
      ) : null}
      {exported && state.status === "complete" ? (
        <span data-testid="reader-tour-exported-note" style={noteStyle}>
          Tour record exported.
        </span>
      ) : null}

      <ReaderTourOverlay
        onDismiss={() => dispatch({ type: "dismiss" })}
        onExport={handleExport}
        onNext={() => dispatch({ type: "next" })}
        onPrev={() => dispatch({ type: "prev" })}
        onRestart={() => {
          setExported(false);
          dispatch({ type: "restart" });
        }}
        state={state}
      />
    </div>
  );
}

const startButtonStyle: React.CSSProperties = {
  padding: "0.55rem 1.1rem",
  fontFamily: "inherit",
  fontSize: "0.68rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  border: "1px solid var(--amber, #d4a017)",
  background: "transparent",
  color: "var(--amber, #d4a017)",
  cursor: "pointer",
};

const noteStyle: React.CSSProperties = {
  marginLeft: "0.75rem",
  fontSize: "0.82rem",
  color: "var(--public-muted, #999)",
};
