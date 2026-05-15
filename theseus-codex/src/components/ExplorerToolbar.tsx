"use client";

import type { Reducer } from "@/lib/dimReduce";
import {
  DEFAULT_VIEWPORT,
  ZOOM_MAX,
  ZOOM_MIN,
  clampViewport,
  viewportsEqual,
  type ExplorerState,
} from "@/lib/explorerState";

interface ExplorerToolbarProps {
  state: ExplorerState;
  onChange: (next: ExplorerState) => void;
  onClearSelection: () => void;
  selectionCount: number;
  totalCount: number;
}

const REDUCER_OPTIONS: Array<{ value: Reducer; label: string; hint: string }> = [
  { value: "pca", label: "PCA", hint: "principal components" },
  { value: "umap", label: "UMAP", hint: "neighbour preserving" },
];

const ZOOM_STEP = 1.4;

const buttonStyle = (active: boolean): React.CSSProperties => ({
  fontFamily: "'Cinzel', serif",
  fontSize: "0.72rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  padding: "0.35rem 0.65rem",
  background: active ? "var(--gold)" : "transparent",
  color: active ? "var(--stone)" : "var(--parchment)",
  border: "1px solid var(--border)",
  borderRadius: 2,
  cursor: "pointer",
});

const groupLabelStyle: React.CSSProperties = {
  fontSize: "0.65rem",
  color: "var(--parchment-dim)",
  textTransform: "uppercase",
  letterSpacing: "0.1em",
};

export default function ExplorerToolbar({
  state,
  onChange,
  onClearSelection,
  selectionCount,
  totalCount,
}: ExplorerToolbarProps) {
  const { viewport } = state;

  const zoomTo = (scale: number) => {
    onChange({
      ...state,
      viewport: clampViewport({ ...viewport, scale }),
    });
  };

  const resetView = () => {
    onChange({ ...state, viewport: { ...DEFAULT_VIEWPORT } });
  };

  const atDefaultView = viewportsEqual(viewport, DEFAULT_VIEWPORT);

  return (
    <div
      style={{
        display: "flex",
        gap: "0.75rem",
        flexWrap: "wrap",
        alignItems: "center",
        padding: "0.6rem 0.8rem",
        background: "var(--stone)",
        border: "1px solid var(--border)",
        borderRadius: 2,
        marginBottom: "0.75rem",
      }}
    >
      <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
        <span className="mono" style={groupLabelStyle}>
          Reducer
        </span>
        {REDUCER_OPTIONS.map((opt) => (
          <button
            type="button"
            key={opt.value}
            title={opt.hint}
            style={buttonStyle(state.reducer === opt.value)}
            onClick={() => onChange({ ...state, reducer: opt.value })}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
        <span className="mono" style={groupLabelStyle}>
          Overlays
        </span>
        <button
          type="button"
          style={buttonStyle(state.overlays.contradicts)}
          onClick={() =>
            onChange({
              ...state,
              overlays: { ...state.overlays, contradicts: !state.overlays.contradicts },
            })
          }
        >
          Contradicts
        </button>
        <button
          type="button"
          style={buttonStyle(state.overlays.supports)}
          onClick={() =>
            onChange({
              ...state,
              overlays: { ...state.overlays, supports: !state.overlays.supports },
            })
          }
        >
          Supports
        </button>
      </div>

      <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
        <span className="mono" style={groupLabelStyle}>
          Zoom
        </span>
        <button
          type="button"
          aria-label="Zoom out"
          title="Zoom out"
          disabled={viewport.scale <= ZOOM_MIN + 1e-6}
          style={buttonStyle(false)}
          onClick={() => zoomTo(viewport.scale / ZOOM_STEP)}
        >
          −
        </button>
        <span
          className="mono"
          aria-hidden="true"
          style={{
            fontSize: "0.68rem",
            color: "var(--parchment)",
            minWidth: "3.2rem",
            textAlign: "center",
          }}
        >
          {viewport.scale.toFixed(2)}×
        </span>
        <button
          type="button"
          aria-label="Zoom in"
          title="Zoom in"
          disabled={viewport.scale >= ZOOM_MAX - 1e-6}
          style={buttonStyle(false)}
          onClick={() => zoomTo(viewport.scale * ZOOM_STEP)}
        >
          +
        </button>
        <button
          type="button"
          style={buttonStyle(false)}
          disabled={atDefaultView}
          onClick={resetView}
          title="Reset zoom and pan"
        >
          Reset view
        </button>
      </div>

      <div
        className="mono"
        style={{
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          marginLeft: "auto",
        }}
      >
        {selectionCount > 0
          ? `${selectionCount} of ${totalCount} selected`
          : `${totalCount} conclusions`}
      </div>

      {selectionCount > 0 && (
        <button type="button" style={buttonStyle(false)} onClick={onClearSelection}>
          Clear
        </button>
      )}
    </div>
  );
}
