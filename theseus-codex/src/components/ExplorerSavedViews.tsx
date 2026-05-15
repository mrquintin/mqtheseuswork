"use client";

import { useMemo, useState } from "react";

import {
  diffSavedViews,
  type SavedView,
  type SavedViewDiff,
} from "@/lib/explorerState";

/**
 * Saved views, promoted to first-class objects.
 *
 * v2 stored a saved view as a bare label + query string and surfaced
 * them in a cramped toolbar dropdown. This panel gives each view a
 * name AND an optional description, supports rename-in-place, and —
 * the headline feature — diffs any two views against each other so a
 * founder can answer "what actually changed between these two saves?"
 * without eyeballing two URLs.
 */

interface ExplorerSavedViewsProps {
  savedViews: SavedView[];
  onSave: (label: string, description?: string) => void;
  onSelect: (view: SavedView) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, patch: { label?: string; description?: string }) => void;
}

export default function ExplorerSavedViews({
  savedViews,
  onSave,
  onSelect,
  onDelete,
  onRename,
}: ExplorerSavedViewsProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  // Two-slot diff selection. Picking a third view drops the oldest.
  const [diffPair, setDiffPair] = useState<string[]>([]);

  const byId = useMemo(() => {
    const map = new Map<string, SavedView>();
    for (const v of savedViews) map.set(v.id, v);
    return map;
  }, [savedViews]);

  const diff: { a: SavedView; b: SavedView; result: SavedViewDiff } | null =
    useMemo(() => {
      if (diffPair.length !== 2) return null;
      const a = byId.get(diffPair[0]);
      const b = byId.get(diffPair[1]);
      if (!a || !b) return null;
      return { a, b, result: diffSavedViews(a, b) };
    }, [diffPair, byId]);

  const submitSave = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onSave(trimmed, description.trim() || undefined);
    setName("");
    setDescription("");
  };

  const toggleDiff = (id: string) => {
    setDiffPair((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      return [...prev, id].slice(-2);
    });
  };

  const startEdit = (view: SavedView) => {
    setEditingId(view.id);
    setEditName(view.label);
    setEditDescription(view.description ?? "");
  };

  const commitEdit = () => {
    if (!editingId) return;
    onRename(editingId, {
      label: editName,
      description: editDescription,
    });
    setEditingId(null);
  };

  return (
    <section
      className="portal-card"
      aria-label="Saved views"
      style={{ padding: "0.85rem 0.95rem", display: "flex", flexDirection: "column", gap: "0.7rem" }}
    >
      <div className="mono" style={sectionLabel}>
        Saved views{savedViews.length > 0 ? ` · ${savedViews.length}` : ""}
      </div>

      {/* Save the current view. Name required, description optional. */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submitSave();
            }
          }}
          placeholder="Name this view"
          aria-label="Saved view name"
          style={inputStyle}
        />
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submitSave();
            }
          }}
          placeholder="Description (optional)"
          aria-label="Saved view description"
          style={inputStyle}
        />
        <button
          type="button"
          onClick={submitSave}
          disabled={!name.trim()}
          style={{ ...buttonStyle, opacity: name.trim() ? 1 : 0.5 }}
        >
          Save current view
        </button>
      </div>

      {savedViews.length === 0 ? (
        <p style={emptyHint}>
          No saved views yet. Name the current selection, overlays, and zoom to
          come back to them — or share the link.
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "0.3rem" }}>
          {savedViews.map((view) => {
            const inDiff = diffPair.includes(view.id);
            const isEditing = editingId === view.id;
            return (
              <li
                key={view.id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 2,
                  padding: "0.45rem 0.55rem",
                  background: inDiff ? "rgba(212,160,23,0.10)" : "transparent",
                }}
              >
                {isEditing ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      aria-label={`Rename ${view.label}`}
                      style={inputStyle}
                    />
                    <input
                      type="text"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      aria-label={`Describe ${view.label}`}
                      placeholder="Description (optional)"
                      style={inputStyle}
                    />
                    <div style={{ display: "flex", gap: "0.3rem" }}>
                      <button type="button" onClick={commitEdit} style={buttonStyle}>
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingId(null)}
                        style={ghostButtonStyle}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.4rem" }}>
                      <button
                        type="button"
                        onClick={() => onSelect(view)}
                        style={viewNameButton}
                      >
                        {view.label}
                      </button>
                      <span className="mono" style={{ fontSize: "0.55rem", color: "var(--parchment-dim)" }}>
                        {formatTimestamp(view.savedAt)}
                      </span>
                    </div>
                    {view.description ? (
                      <p style={descriptionText}>{view.description}</p>
                    ) : null}
                    <div style={{ display: "flex", gap: "0.3rem", marginTop: "0.35rem", flexWrap: "wrap" }}>
                      <button
                        type="button"
                        onClick={() => toggleDiff(view.id)}
                        aria-pressed={inDiff}
                        style={inDiff ? buttonStyle : ghostButtonStyle}
                      >
                        {inDiff ? "In diff" : "Diff"}
                      </button>
                      <button type="button" onClick={() => startEdit(view)} style={ghostButtonStyle}>
                        Rename
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          onDelete(view.id);
                          setDiffPair((prev) => prev.filter((x) => x !== view.id));
                        }}
                        aria-label={`Delete view ${view.label}`}
                        style={ghostButtonStyle}
                      >
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {diffPair.length === 1 ? (
        <p style={emptyHint}>Pick a second view to diff against.</p>
      ) : null}
      {diff ? <SavedViewDiffView a={diff.a} b={diff.b} diff={diff.result} /> : null}
    </section>
  );
}

function SavedViewDiffView({
  a,
  b,
  diff,
}: {
  a: SavedView;
  b: SavedView;
  diff: SavedViewDiff;
}) {
  const headline = diff.identical
    ? "These two views are identical."
    : diff.sameSelectionDifferentOverlays
      ? "Same selection — overlays / reducer differ."
      : diff.sameOverlaysDifferentSelection
        ? "Same overlays — selection differs."
        : "Multiple differences.";

  return (
    <div
      aria-label="Saved view diff"
      style={{
        border: "1px solid var(--gold-dim)",
        borderRadius: 2,
        padding: "0.55rem 0.6rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.4rem",
      }}
    >
      <div className="mono" style={sectionLabel}>
        Diff
      </div>
      <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--parchment)" }}>
        <strong>{a.label}</strong> <span style={{ color: "var(--parchment-dim)" }}>→</span>{" "}
        <strong>{b.label}</strong>
      </p>
      <p style={{ margin: 0, fontSize: "0.72rem", color: "var(--amber-dim)" }}>{headline}</p>

      <DiffRow
        label="Reducer"
        changed={diff.reducer.changed}
        value={
          diff.reducer.changed
            ? `${diff.reducer.a} → ${diff.reducer.b}`
            : diff.reducer.a
        }
      />
      <DiffRow
        label="Overlays"
        changed={diff.overlays.changed}
        value={
          diff.overlays.changed
            ? `${overlayLabel(diff.overlays.a)} → ${overlayLabel(diff.overlays.b)}`
            : overlayLabel(diff.overlays.a)
        }
      />
      <DiffRow
        label="Selection"
        changed={diff.selection.changed}
        value={
          diff.selection.changed
            ? `${diff.selection.common.length} shared · +${diff.selection.added.length} · −${diff.selection.removed.length}`
            : `${diff.selection.common.length} ids (unchanged)`
        }
      />
      <DiffRow
        label="Focus"
        changed={diff.focused.changed}
        value={
          diff.focused.changed
            ? `${diff.focused.a ?? "none"} → ${diff.focused.b ?? "none"}`
            : diff.focused.a ?? "none"
        }
      />
      <DiffRow
        label="Viewport"
        changed={diff.viewport.changed}
        value={
          diff.viewport.changed
            ? `${viewportLabel(diff.viewport.a)} → ${viewportLabel(diff.viewport.b)}`
            : viewportLabel(diff.viewport.a)
        }
      />
    </div>
  );
}

function DiffRow({
  label,
  changed,
  value,
}: {
  label: string;
  changed: boolean;
  value: string;
}) {
  return (
    <div style={{ display: "flex", gap: "0.5rem", fontSize: "0.72rem", alignItems: "baseline" }}>
      <span
        className="mono"
        style={{
          minWidth: "5rem",
          color: "var(--parchment-dim)",
          textTransform: "uppercase",
          fontSize: "0.55rem",
          letterSpacing: "0.08em",
        }}
      >
        {label}
      </span>
      <span
        style={{
          color: changed ? "var(--amber)" : "var(--parchment-dim)",
          fontWeight: changed ? 600 : 400,
        }}
      >
        {changed ? "● " : "○ "}
        {value}
      </span>
    </div>
  );
}

function overlayLabel(o: { contradicts: boolean; supports: boolean }): string {
  const parts: string[] = [];
  if (o.contradicts) parts.push("contradicts");
  if (o.supports) parts.push("supports");
  return parts.length ? parts.join(" + ") : "none";
}

function viewportLabel(v: { cx: number; cy: number; scale: number }): string {
  return `${v.scale.toFixed(2)}× @ (${v.cx.toFixed(2)}, ${v.cy.toFixed(2)})`;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const sectionLabel: React.CSSProperties = {
  fontSize: "0.6rem",
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "var(--amber-dim)",
};

const inputStyle: React.CSSProperties = {
  background: "var(--stone)",
  border: "1px solid var(--border)",
  borderRadius: 2,
  color: "var(--parchment)",
  fontSize: "0.78rem",
  padding: "0.35rem 0.5rem",
};

const buttonStyle: React.CSSProperties = {
  fontFamily: "'Cinzel', serif",
  fontSize: "0.65rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  padding: "0.3rem 0.55rem",
  background: "var(--gold)",
  color: "var(--stone)",
  border: "1px solid var(--border)",
  borderRadius: 2,
  cursor: "pointer",
};

const ghostButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: "transparent",
  color: "var(--parchment)",
};

const viewNameButton: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--parchment)",
  cursor: "pointer",
  fontFamily: "'EB Garamond', serif",
  fontSize: "0.9rem",
  textAlign: "left",
  padding: 0,
  flex: 1,
};

const descriptionText: React.CSSProperties = {
  margin: "0.2rem 0 0",
  fontSize: "0.72rem",
  color: "var(--parchment-dim)",
  lineHeight: 1.4,
};

const emptyHint: React.CSSProperties = {
  margin: 0,
  fontSize: "0.75rem",
  color: "var(--parchment-dim)",
  fontStyle: "italic",
  lineHeight: 1.45,
};
