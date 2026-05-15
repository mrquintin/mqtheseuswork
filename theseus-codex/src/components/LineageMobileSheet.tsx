"use client";

import { useState } from "react";

import type { LineageLaneId, LineageLaneModel } from "@/lib/lineage";

/**
 * Sticky bottom sheet of lane filters for the mobile lineage view.
 *
 * On a phone the lineage timeline reflows from side-by-side swim lanes
 * to a single chronological column (see `LineageTimeline`), so the
 * desktop toolbar's lane-checkbox row has nowhere sensible to sit. It
 * moves here: a collapsed pill pinned to the bottom of the viewport
 * ("Lanes · 5 of 7") that expands upward into the full checklist.
 *
 * The sheet is `position: fixed` and pays `env(safe-area-inset-bottom)`
 * so it clears the iOS Safari home indicator / bottom bar rather than
 * being overlapped by it. It is rendered on every viewport but hidden
 * above 720px by the `lineage-mobile-only` class.
 */

type Props = {
  lanes: LineageLaneModel[];
  onToggleLane: (id: LineageLaneId, on: boolean) => void;
};

export default function LineageMobileSheet({ lanes, onToggleLane }: Props) {
  const [expanded, setExpanded] = useState(false);
  const visibleCount = lanes.filter((l) => l.visible).length;

  return (
    <div
      className="lineage-mobile-only lineage-mobile-sheet"
      data-testid="lineage-mobile-sheet"
      data-expanded={expanded ? "true" : "false"}
    >
      <button
        type="button"
        className="lineage-mobile-sheet-handle"
        aria-expanded={expanded}
        aria-controls="lineage-mobile-sheet-body"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="mono">
          Lanes · {visibleCount} of {lanes.length}
        </span>
        <span aria-hidden="true">{expanded ? "▾" : "▴"}</span>
      </button>

      {expanded ? (
        <div
          id="lineage-mobile-sheet-body"
          className="lineage-mobile-sheet-body"
        >
          <fieldset className="lineage-mobile-sheet-fieldset">
            <legend className="mono lineage-mobile-sheet-legend">
              Show lanes
            </legend>
            {lanes.map((lane) => (
              <label key={lane.id} className="lineage-mobile-sheet-row">
                <input
                  type="checkbox"
                  checked={lane.visible}
                  onChange={(e) => onToggleLane(lane.id, e.target.checked)}
                  aria-label={`Show ${lane.label} lane`}
                />
                <span style={{ flex: 1 }}>{lane.label}</span>
                <span className="mono lineage-mobile-sheet-count">
                  {lane.eventCount}
                </span>
              </label>
            ))}
          </fieldset>
        </div>
      ) : null}

      <style>{`
        .lineage-mobile-sheet {
          position: fixed;
          left: 0;
          right: 0;
          bottom: 0;
          z-index: 30;
          background: rgba(14, 10, 6, 0.96);
          -webkit-backdrop-filter: blur(8px);
          backdrop-filter: blur(8px);
          border-top: 1px solid rgba(212, 160, 23, 0.22);
          /* Clear the iOS Safari home indicator / bottom bar instead of
             being overlapped by it. */
          padding-bottom: env(safe-area-inset-bottom, 0px);
        }
        [data-theme="light"] .lineage-mobile-sheet {
          background: rgba(242, 232, 217, 0.97);
        }
        .lineage-mobile-sheet-handle {
          width: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.5rem;
          background: transparent;
          border: 0;
          color: var(--amber);
          font-size: 0.62rem;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          padding: 0.7rem 1rem;
          cursor: pointer;
        }
        .lineage-mobile-sheet-body {
          max-height: 48vh;
          overflow-y: auto;
          padding: 0 1rem 0.85rem;
        }
        .lineage-mobile-sheet-fieldset {
          border: none;
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: 0.1rem;
        }
        .lineage-mobile-sheet-legend {
          font-size: 0.55rem;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          color: var(--amber-dim);
          margin-bottom: 0.35rem;
        }
        .lineage-mobile-sheet-row {
          display: flex;
          align-items: center;
          gap: 0.6rem;
          padding: 0.55rem 0.25rem;
          border-bottom: 1px solid var(--stroke);
          color: var(--parchment);
          font-size: 0.82rem;
          cursor: pointer;
        }
        .lineage-mobile-sheet-row:last-child { border-bottom: 0; }
        .lineage-mobile-sheet-row input { width: 18px; height: 18px; }
        .lineage-mobile-sheet-count {
          color: var(--parchment-dim);
          font-size: 0.7rem;
        }
      `}</style>
    </div>
  );
}
