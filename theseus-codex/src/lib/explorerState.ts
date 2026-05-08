/**
 * URL-state codec for the Explorer.
 *
 * Every meaningful navigation state — chosen reducer, current
 * selection, overlay toggles, focused conclusion — round-trips
 * through the URL so a founder can paste a link and land on the same
 * view. The "save view" feature is just a list of these URLs.
 *
 * The codec is deliberately string-based and stable: future fields
 * append new keys; unknown keys decode to defaults. Selection ids
 * are encoded as a comma-separated list (compact, predictable, no
 * base64 ceremony unless we actually outgrow URL length).
 */

import type { Reducer } from "@/lib/dimReduce";

export type Overlay = "contradicts" | "supports";

export interface ExplorerState {
  reducer: Reducer;
  /** Selected conclusion ids. Order is not preserved. */
  selection: string[];
  /** Active overlay toggles. */
  overlays: { contradicts: boolean; supports: boolean };
  /** Conclusion that owns the open side panel, if any. */
  focused: string | null;
}

export interface SavedView {
  id: string;
  label: string;
  query: string; // serialised URLSearchParams (no leading "?")
  savedAt: string; // ISO timestamp
}

const VALID_REDUCERS: ReadonlySet<Reducer> = new Set<Reducer>(["pca", "umap"]);

export const DEFAULT_EXPLORER_STATE: ExplorerState = {
  reducer: "pca",
  selection: [],
  overlays: { contradicts: false, supports: false },
  focused: null,
};

const SAVED_VIEWS_KEY = "explorer.savedViews.v1";

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
  return {
    reducer,
    selection: Array.from(new Set(selection)),
    overlays: {
      contradicts: params.get("oc") === "1",
      supports: params.get("os") === "1",
    },
    focused: params.get("f") || null,
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
    return parsed.filter(
      (v): v is SavedView =>
        v && typeof v.id === "string" && typeof v.label === "string" && typeof v.query === "string",
    );
  } catch {
    return [];
  }
}

export function saveView(label: string, state: ExplorerState): SavedView[] {
  const views = loadSavedViews();
  const params = encodeExplorerState(state);
  const query = params.toString();
  const trimmed = label.trim() || "Untitled view";
  const next: SavedView = {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    label: trimmed,
    query,
    savedAt: new Date().toISOString(),
  };
  // Drop a duplicate query so the list stays clean.
  const deduped = views.filter((v) => v.query !== query);
  const updated = [next, ...deduped].slice(0, 50);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(SAVED_VIEWS_KEY, JSON.stringify(updated));
    } catch {
      // ignore
    }
  }
  return updated;
}

export function deleteSavedView(id: string): SavedView[] {
  const views = loadSavedViews().filter((v) => v.id !== id);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(SAVED_VIEWS_KEY, JSON.stringify(views));
    } catch {
      // ignore
    }
  }
  return views;
}
