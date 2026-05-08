"use client";

import type { Reducer } from "@/lib/dimReduce";
import type { ExplorerState, SavedView } from "@/lib/explorerState";

interface ExplorerToolbarProps {
  state: ExplorerState;
  onChange: (next: ExplorerState) => void;
  onSaveView: (label: string) => void;
  onClearSelection: () => void;
  savedViews: SavedView[];
  onSelectSavedView: (view: SavedView) => void;
  onDeleteSavedView: (id: string) => void;
  selectionCount: number;
  totalCount: number;
}

const REDUCER_OPTIONS: Array<{ value: Reducer; label: string; hint: string }> = [
  { value: "pca", label: "PCA", hint: "principal components" },
  { value: "umap", label: "UMAP", hint: "neighbour preserving" },
];

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

export default function ExplorerToolbar({
  state,
  onChange,
  onSaveView,
  onClearSelection,
  savedViews,
  onSelectSavedView,
  onDeleteSavedView,
  selectionCount,
  totalCount,
}: ExplorerToolbarProps) {
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
        <span
          className="mono"
          style={{
            fontSize: "0.65rem",
            color: "var(--parchment-dim)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
          }}
        >
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
        <span
          className="mono"
          style={{
            fontSize: "0.65rem",
            color: "var(--parchment-dim)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
          }}
        >
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
        <button
          type="button"
          style={buttonStyle(false)}
          onClick={onClearSelection}
        >
          Clear
        </button>
      )}

      <button
        type="button"
        style={buttonStyle(false)}
        onClick={() => {
          const label =
            (typeof window !== "undefined"
              ? window.prompt("Name this view")
              : null) || "";
          if (label.trim()) onSaveView(label.trim());
        }}
      >
        Save view
      </button>

      {savedViews.length > 0 && (
        <details style={{ position: "relative" }}>
          <summary
            style={{
              ...buttonStyle(false),
              listStyle: "none",
              userSelect: "none",
            }}
          >
            Views ({savedViews.length})
          </summary>
          <div
            style={{
              position: "absolute",
              right: 0,
              top: "calc(100% + 4px)",
              minWidth: 240,
              background: "var(--stone)",
              border: "1px solid var(--border)",
              borderRadius: 2,
              padding: "0.4rem",
              zIndex: 50,
              maxHeight: 280,
              overflowY: "auto",
            }}
          >
            {savedViews.map((view) => (
              <div
                key={view.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "0.4rem",
                  padding: "0.3rem 0.4rem",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <button
                  type="button"
                  onClick={() => onSelectSavedView(view)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--parchment)",
                    cursor: "pointer",
                    fontSize: "0.78rem",
                    textAlign: "left",
                    flex: 1,
                  }}
                >
                  {view.label}
                </button>
                <button
                  type="button"
                  aria-label={`Delete view ${view.label}`}
                  onClick={() => onDeleteSavedView(view.id)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--parchment-dim)",
                    cursor: "pointer",
                    fontSize: "0.7rem",
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
