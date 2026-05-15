/**
 * URL-state codec for the Explorer.
 *
 * Every meaningful navigation state — chosen reducer, current
 * selection, overlay toggles, focused conclusion, AND the viewport
 * (zoom + pan centre) — round-trips through the URL so a founder can
 * paste a link and land on exactly the same view. The "save view"
 * feature is a list of these URLs, dressed up as first-class objects
 * with a name and an optional description.
 *
 * The codec is deliberately string-based and stable: future fields
 * append new keys; unknown keys decode to defaults. Selection ids
 * are encoded as a comma-separated list (compact, predictable, no
 * base64 ceremony unless we actually outgrow URL length). Numeric
 * viewport fields are quantised to 4 decimal places so a wheel-zoom
 * gesture produces a finite, canonical URL rather than a 17-digit
 * float — and so encode∘decode∘encode is a fixed point.
 */

import type { Reducer } from "@/lib/dimReduce";

export type Overlay = "contradicts" | "supports";

/** Viewport: pan centre in unit-square coords, plus a zoom scale. */
export interface ExplorerViewport {
  /** Pan centre X in [0,1] unit-square coordinates. */
  cx: number;
  /** Pan centre Y in [0,1] unit-square coordinates. */
  cy: number;
  /** Zoom scale. 1 = fit-to-bounds; >1 zooms in. */
  scale: number;
}

export interface ExplorerState {
  reducer: Reducer;
  /** Selected conclusion ids. Order is not preserved. */
  selection: string[];
  /** Active overlay toggles. */
  overlays: { contradicts: boolean; supports: boolean };
  /** Conclusion that owns the open side panel, if any. */
  focused: string | null;
  /** Viewport — zoom level and pan centre. Linkable like everything else. */
  viewport: ExplorerViewport;
}

export interface SavedView {
  id: string;
  /** Human-given name. */
  label: string;
  /** Optional longer note explaining what the view is for. */
  description?: string;
  query: string; // serialised URLSearchParams (no leading "?")
  savedAt: string; // ISO timestamp
}

const VALID_REDUCERS: ReadonlySet<Reducer> = new Set<Reducer>(["pca", "umap"]);

export const DEFAULT_VIEWPORT: ExplorerViewport = { cx: 0.5, cy: 0.5, scale: 1 };

export const DEFAULT_EXPLORER_STATE: ExplorerState = {
  reducer: "pca",
  selection: [],
  overlays: { contradicts: false, supports: false },
  focused: null,
  viewport: { ...DEFAULT_VIEWPORT },
};

/** Zoom is clamped to a sane band — both in the codec and the canvas. */
export const ZOOM_MIN = 0.25;
export const ZOOM_MAX = 16;
/** Pan centre may drift slightly outside the unit square (overscroll). */
const CENTER_MIN = -0.5;
const CENTER_MAX = 1.5;

const SAVED_VIEWS_KEY = "explorer.savedViews.v1";

// ── Numeric helpers ────────────────────────────────────────────────

function clamp(value: number, lo: number, hi: number): number {
  if (!Number.isFinite(value)) return lo;
  return value < lo ? lo : value > hi ? hi : value;
}

/** Quantise to 4 dp and drop a trailing-zero tail. Canonical + compact. */
function quantise(value: number): number {
  return Number(value.toFixed(4));
}

function nearlyEqual(a: number, b: number): boolean {
  return Math.abs(a - b) < 1e-9;
}

export function clampViewport(v: ExplorerViewport): ExplorerViewport {
  return {
    cx: clamp(quantise(v.cx), CENTER_MIN, CENTER_MAX),
    cy: clamp(quantise(v.cy), CENTER_MIN, CENTER_MAX),
    scale: clamp(quantise(v.scale), ZOOM_MIN, ZOOM_MAX),
  };
}

export function viewportsEqual(a: ExplorerViewport, b: ExplorerViewport): boolean {
  return (
    nearlyEqual(a.cx, b.cx) &&
    nearlyEqual(a.cy, b.cy) &&
    nearlyEqual(a.scale, b.scale)
  );
}

// ── Codec ──────────────────────────────────────────────────────────

export function encodeExplorerState(state: ExplorerState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.reducer !== DEFAULT_EXPLORER_STATE.reducer) {
    params.set("r", state.reducer);
  }
  if (state.selection.length > 0) {
    // Stable, sorted, de-duplicated. Sorting makes the URL canonical
    // so the same selection always serialises to the same string —
    // important for save-view de-dup.
    const cleaned = Array.from(new Set(state.selection.filter(Boolean))).sort();
    params.set("sel", cleaned.join(","));
  }
  if (state.overlays.contradicts) params.set("oc", "1");
  if (state.overlays.supports) params.set("os", "1");
  if (state.focused) params.set("f", state.focused);
  // Viewport: each axis is omitted when it sits at its default, so a
  // pristine view still serialises to "".
  const vp = clampViewport(state.viewport);
  if (!nearlyEqual(vp.scale, DEFAULT_VIEWPORT.scale)) {
    params.set("z", String(vp.scale));
  }
  if (!nearlyEqual(vp.cx, DEFAULT_VIEWPORT.cx)) {
    params.set("cx", String(vp.cx));
  }
  if (!nearlyEqual(vp.cy, DEFAULT_VIEWPORT.cy)) {
    params.set("cy", String(vp.cy));
  }
  return params;
}

export function decodeExplorerState(input: URLSearchParams | string): ExplorerState {
  const params = typeof input === "string" ? new URLSearchParams(input) : input;
  const rawReducer = params.get("r");
  const reducer: Reducer = rawReducer && VALID_REDUCERS.has(rawReducer as Reducer)
    ? (rawReducer as Reducer)
    : DEFAULT_EXPLORER_STATE.reducer;
  const rawSel = params.get("sel") || "";
  const selection = rawSel
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  // Viewport. A malformed or absent number falls back to the default
  // for that axis; values are clamped so a hand-edited URL can't push
  // the canvas into an un-navigable state.
  const parseNum = (key: string, fallback: number): number => {
    const raw = params.get(key);
    if (raw === null || raw.trim() === "") return fallback;
    const n = Number(raw);
    return Number.isFinite(n) ? n : fallback;
  };
  const viewport = clampViewport({
    scale: parseNum("z", DEFAULT_VIEWPORT.scale),
    cx: parseNum("cx", DEFAULT_VIEWPORT.cx),
    cy: parseNum("cy", DEFAULT_VIEWPORT.cy),
  });

  return {
    reducer,
    selection: Array.from(new Set(selection)),
    overlays: {
      contradicts: params.get("oc") === "1",
      supports: params.get("os") === "1",
    },
    focused: params.get("f") || null,
    viewport,
  };
}

export function explorerStateToQuery(state: ExplorerState): string {
  const params = encodeExplorerState(state);
  const str = params.toString();
  return str ? `?${str}` : "";
}

export function explorerStatesEqual(a: ExplorerState, b: ExplorerState): boolean {
  return encodeExplorerState(a).toString() === encodeExplorerState(b).toString();
}

// ── Saved views (localStorage) ─────────────────────────────────────

export function loadSavedViews(): SavedView[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SAVED_VIEWS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (v): v is SavedView =>
          v &&
          typeof v.id === "string" &&
          typeof v.label === "string" &&
          typeof v.query === "string",
      )
      .map((v) => ({
        id: v.id,
        label: v.label,
        description:
          typeof v.description === "string" && v.description.trim()
            ? v.description
            : undefined,
        query: v.query,
        savedAt: typeof v.savedAt === "string" ? v.savedAt : new Date(0).toISOString(),
      }));
  } catch {
    return [];
  }
}

function persistSavedViews(views: SavedView[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SAVED_VIEWS_KEY, JSON.stringify(views));
  } catch {
    // localStorage may be unavailable / full; the caller still gets
    // the updated array back for in-memory state.
  }
}

export function saveView(
  label: string,
  state: ExplorerState,
  description?: string,
): SavedView[] {
  const views = loadSavedViews();
  const params = encodeExplorerState(state);
  const query = params.toString();
  const trimmedLabel = label.trim() || "Untitled view";
  const trimmedDescription = description?.trim() || undefined;
  const next: SavedView = {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    label: trimmedLabel,
    description: trimmedDescription,
    query,
    savedAt: new Date().toISOString(),
  };
  // Drop a duplicate query so the list stays clean — the freshest
  // name/description wins.
  const deduped = views.filter((v) => v.query !== query);
  const updated = [next, ...deduped].slice(0, 50);
  persistSavedViews(updated);
  return updated;
}

/** Rename or re-describe an existing saved view in place. */
export function updateSavedView(
  id: string,
  patch: { label?: string; description?: string },
): SavedView[] {
  const views = loadSavedViews().map((v) => {
    if (v.id !== id) return v;
    const nextLabel =
      patch.label !== undefined ? patch.label.trim() || v.label : v.label;
    const nextDescription =
      patch.description !== undefined
        ? patch.description.trim() || undefined
        : v.description;
    return { ...v, label: nextLabel, description: nextDescription };
  });
  persistSavedViews(views);
  return views;
}

export function deleteSavedView(id: string): SavedView[] {
  const views = loadSavedViews().filter((v) => v.id !== id);
  persistSavedViews(views);
  return views;
}

// ── Saved-view diffing ─────────────────────────────────────────────

export interface SavedViewDiff {
  reducer: { changed: boolean; a: Reducer; b: Reducer };
  overlays: {
    changed: boolean;
    a: { contradicts: boolean; supports: boolean };
    b: { contradicts: boolean; supports: boolean };
  };
  selection: {
    changed: boolean;
    /** ids present in both views. */
    common: string[];
    /** ids present in b but not a. */
    added: string[];
    /** ids present in a but not b. */
    removed: string[];
  };
  focused: { changed: boolean; a: string | null; b: string | null };
  viewport: { changed: boolean; a: ExplorerViewport; b: ExplorerViewport };
  /** True when the two views select the same set but differ elsewhere. */
  sameSelectionDifferentOverlays: boolean;
  /** True when the two views share overlays but select different sets. */
  sameOverlaysDifferentSelection: boolean;
  /** True when nothing meaningful differs between the two views. */
  identical: boolean;
}

function overlaysEqual(
  a: { contradicts: boolean; supports: boolean },
  b: { contradicts: boolean; supports: boolean },
): boolean {
  return a.contradicts === b.contradicts && a.supports === b.supports;
}

/**
 * Structurally diff two saved views. Both are decoded from their
 * stored query strings, so this works on the canonical state — not on
 * whatever the user happened to type. The result is shaped to answer
 * the two questions the UI asks directly: "same selection, different
 * overlays?" and "same overlays, different selection?".
 */
export function diffSavedViews(a: SavedView, b: SavedView): SavedViewDiff {
  const sa = decodeExplorerState(a.query);
  const sb = decodeExplorerState(b.query);

  const setA = new Set(sa.selection);
  const setB = new Set(sb.selection);
  const common = sa.selection.filter((id) => setB.has(id)).sort();
  const added = sb.selection.filter((id) => !setA.has(id)).sort();
  const removed = sa.selection.filter((id) => !setB.has(id)).sort();
  const selectionChanged = added.length > 0 || removed.length > 0;

  const overlaysChanged = !overlaysEqual(sa.overlays, sb.overlays);
  const reducerChanged = sa.reducer !== sb.reducer;
  const focusedChanged = sa.focused !== sb.focused;
  const viewportChanged = !viewportsEqual(sa.viewport, sb.viewport);

  return {
    reducer: { changed: reducerChanged, a: sa.reducer, b: sb.reducer },
    overlays: { changed: overlaysChanged, a: sa.overlays, b: sb.overlays },
    selection: { changed: selectionChanged, common, added, removed },
    focused: { changed: focusedChanged, a: sa.focused, b: sb.focused },
    viewport: { changed: viewportChanged, a: sa.viewport, b: sb.viewport },
    sameSelectionDifferentOverlays:
      !selectionChanged && (overlaysChanged || reducerChanged),
    sameOverlaysDifferentSelection: !overlaysChanged && selectionChanged,
    identical:
      !selectionChanged &&
      !overlaysChanged &&
      !reducerChanged &&
      !focusedChanged &&
      !viewportChanged,
  };
}
