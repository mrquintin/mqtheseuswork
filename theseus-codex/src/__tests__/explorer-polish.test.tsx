import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Explorer polish (Round 17 prompt 35 refinement).
 *
 * Covers the four things the refinement is judged on:
 *   - URL state stability: every linkable field — including the new
 *     zoom + pan viewport — round-trips through the URL exactly, and
 *     the codec is canonical (encode∘decode∘encode is a fixed point);
 *   - level-of-detail: the zoom thresholds that hide labels and
 *     cluster the cloud, plus the visible-node ceiling that
 *     auto-disables the contradiction overlay;
 *   - saved views as first-class objects: CRUD + the two-view diff;
 *   - the empty/error/stale diagnostic, including the founder gate on
 *     the "rebuild index" action.
 */

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import ExplorerEmptyState from "@/components/ExplorerEmptyState";
import {
  OVERLAY_AUTO_OFF_NODES,
  computeLevelOfDetail,
  contradictionsOverlayVisible,
  focusFade,
} from "@/components/ExplorerCanvas";
import {
  DEFAULT_EXPLORER_STATE,
  ZOOM_MAX,
  clampViewport,
  decodeExplorerState,
  deleteSavedView,
  diffSavedViews,
  encodeExplorerState,
  explorerStatesEqual,
  loadSavedViews,
  saveView,
  updateSavedView,
  type ExplorerState,
  type SavedView,
} from "@/lib/explorerState";

// ── localStorage shim (vitest runs in the node env) ────────────────

function installLocalStorage() {
  const store = new Map<string, string>();
  const mock = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => {
      store.set(k, String(v));
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() {
      return store.size;
    },
  };
  vi.stubGlobal("window", { localStorage: mock });
  return mock;
}

// ── URL state round-trip ───────────────────────────────────────────

describe("explorer URL state — viewport round-trip", () => {
  it("round-trips zoom + pan losslessly", () => {
    const state: ExplorerState = {
      reducer: "umap",
      selection: ["c-2", "c-1"],
      overlays: { contradicts: true, supports: false },
      focused: "c-1",
      viewport: { cx: 0.3125, cy: 0.71, scale: 2.4 },
    };
    const decoded = decodeExplorerState(encodeExplorerState(state));
    expect(decoded.viewport).toEqual(state.viewport);
    expect(decoded.reducer).toBe("umap");
    expect(decoded.focused).toBe("c-1");
    expect(new Set(decoded.selection)).toEqual(new Set(state.selection));
  });

  it("keeps a default viewport out of the query", () => {
    const params = encodeExplorerState(DEFAULT_EXPLORER_STATE);
    expect(params.toString()).toBe("");
    expect(params.has("z")).toBe(false);
    expect(params.has("cx")).toBe(false);
    expect(params.has("cy")).toBe(false);
  });

  it("only the moved axes appear in the query", () => {
    const state: ExplorerState = {
      ...DEFAULT_EXPLORER_STATE,
      viewport: { cx: 0.5, cy: 0.5, scale: 3 },
    };
    const params = encodeExplorerState(state);
    expect(params.get("z")).toBe("3");
    expect(params.has("cx")).toBe(false);
    expect(params.has("cy")).toBe(false);
  });

  it("is a fixed point under encode∘decode∘encode (canonical)", () => {
    // A wheel gesture produces ugly floats; the codec must quantise
    // them to something stable so the same view always serialises the
    // same way.
    const messy: ExplorerState = {
      ...DEFAULT_EXPLORER_STATE,
      viewport: { cx: 0.333333333, cy: 0.6666666, scale: 1.847291 },
    };
    const once = encodeExplorerState(messy).toString();
    const twice = encodeExplorerState(
      decodeExplorerState(once),
    ).toString();
    expect(twice).toBe(once);
    // And the decoded state survives a second trip unchanged.
    const a = decodeExplorerState(once);
    const b = decodeExplorerState(encodeExplorerState(a));
    expect(explorerStatesEqual(a, b)).toBe(true);
  });

  it("clamps a hand-edited out-of-range zoom", () => {
    const decoded = decodeExplorerState("z=9999");
    expect(decoded.viewport.scale).toBe(ZOOM_MAX);
  });

  it("falls back to defaults for a malformed viewport number", () => {
    const decoded = decodeExplorerState("z=banana&cx=&cy=0.4");
    expect(decoded.viewport.scale).toBe(DEFAULT_EXPLORER_STATE.viewport.scale);
    expect(decoded.viewport.cx).toBe(DEFAULT_EXPLORER_STATE.viewport.cx);
    expect(decoded.viewport.cy).toBe(0.4);
  });

  it("clampViewport quantises to a canonical precision", () => {
    const clamped = clampViewport({ cx: 0.12345678, cy: 0.5, scale: 2.000001 });
    expect(clamped.cx).toBe(0.1235);
    expect(clamped.scale).toBe(2);
  });
});

// ── Level-of-detail ────────────────────────────────────────────────

describe("computeLevelOfDetail — LOD thresholds", () => {
  it("clusters a dense cloud at low zoom", () => {
    const lod = computeLevelOfDetail(5000, 1);
    expect(lod.cluster).toBe(true);
    // Labels never paint while the cloud is clustered.
    expect(lod.showLabels).toBe(false);
  });

  it("never clusters a small cloud, even at zoom 1", () => {
    const lod = computeLevelOfDetail(200, 1);
    expect(lod.cluster).toBe(false);
  });

  it("stops clustering and shows labels once zoomed in", () => {
    // Same 5000-node cloud, but zoomed in past the label threshold.
    const lod = computeLevelOfDetail(5000, 3);
    expect(lod.cluster).toBe(false);
    expect(lod.showLabels).toBe(true);
  });

  it("hides labels below the zoom threshold", () => {
    const lod = computeLevelOfDetail(200, 1.5);
    expect(lod.showLabels).toBe(false);
  });
});

describe("contradiction overlay auto-disable", () => {
  it("is hidden when the toggle is off regardless of node count", () => {
    expect(contradictionsOverlayVisible(false, 10)).toBe(false);
  });

  it("self-disables above the visible-node ceiling", () => {
    expect(
      contradictionsOverlayVisible(true, OVERLAY_AUTO_OFF_NODES + 1),
    ).toBe(false);
  });

  it("shows when toggled on and under the ceiling", () => {
    expect(
      contradictionsOverlayVisible(true, OVERLAY_AUTO_OFF_NODES - 1),
    ).toBe(true);
  });
});

describe("focusFade — distance-from-focus edge fade", () => {
  it("is full strength at the focus node", () => {
    expect(focusFade(0, 400)).toBe(1);
  });

  it("monotonically dims with distance", () => {
    const near = focusFade(50, 400);
    const far = focusFade(300, 400);
    expect(near).toBeGreaterThan(far);
    expect(far).toBeGreaterThan(0);
  });

  it("floors at the falloff distance", () => {
    const atFalloff = focusFade(400, 400);
    const beyond = focusFade(4000, 400);
    expect(atFalloff).toBeCloseTo(beyond, 5);
    expect(atFalloff).toBeLessThan(0.25);
  });
});

// ── Saved views: CRUD ──────────────────────────────────────────────

describe("saved views — CRUD", () => {
  beforeEach(() => {
    installLocalStorage();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const baseState: ExplorerState = {
    ...DEFAULT_EXPLORER_STATE,
    selection: ["a", "b"],
    overlays: { contradicts: true, supports: false },
  };

  it("saves a view with a name and an optional description", () => {
    const views = saveView("Cluster A", baseState, "the planted region");
    expect(views).toHaveLength(1);
    expect(views[0].label).toBe("Cluster A");
    expect(views[0].description).toBe("the planted region");
    // And it persisted — a fresh load sees it.
    const reloaded = loadSavedViews();
    expect(reloaded).toHaveLength(1);
    expect(reloaded[0].label).toBe("Cluster A");
  });

  it("de-duplicates an identical query", () => {
    saveView("First", baseState);
    const views = saveView("Second", baseState);
    expect(views).toHaveLength(1);
    // The freshest name wins.
    expect(views[0].label).toBe("Second");
  });

  it("renames and re-describes a view in place", () => {
    const [created] = saveView("Original", baseState, "first note");
    const updated = updateSavedView(created.id, {
      label: "Renamed",
      description: "second note",
    });
    expect(updated[0].label).toBe("Renamed");
    expect(updated[0].description).toBe("second note");
    // Query untouched — a rename doesn't move the view.
    expect(updated[0].query).toBe(created.query);
  });

  it("clears a description when renamed with an empty string", () => {
    const [created] = saveView("Has note", baseState, "a note");
    const updated = updateSavedView(created.id, { description: "  " });
    expect(updated[0].description).toBeUndefined();
  });

  it("deletes a view", () => {
    const [created] = saveView("Doomed", baseState);
    const after = deleteSavedView(created.id);
    expect(after).toHaveLength(0);
    expect(loadSavedViews()).toHaveLength(0);
  });
});

// ── Saved views: diff ──────────────────────────────────────────────

describe("diffSavedViews", () => {
  function viewFrom(id: string, state: ExplorerState): SavedView {
    return {
      id,
      label: id,
      query: encodeExplorerState(state).toString(),
      savedAt: new Date(0).toISOString(),
    };
  }

  it("detects same selection, different overlays", () => {
    const sel = ["c-1", "c-2", "c-3"];
    const a = viewFrom("a", {
      ...DEFAULT_EXPLORER_STATE,
      selection: sel,
      overlays: { contradicts: true, supports: false },
    });
    const b = viewFrom("b", {
      ...DEFAULT_EXPLORER_STATE,
      selection: sel,
      overlays: { contradicts: false, supports: true },
    });
    const diff = diffSavedViews(a, b);
    expect(diff.selection.changed).toBe(false);
    expect(diff.overlays.changed).toBe(true);
    expect(diff.sameSelectionDifferentOverlays).toBe(true);
    expect(diff.sameOverlaysDifferentSelection).toBe(false);
    expect(diff.identical).toBe(false);
  });

  it("detects same overlays, different selection", () => {
    const overlays = { contradicts: true, supports: false };
    const a = viewFrom("a", {
      ...DEFAULT_EXPLORER_STATE,
      selection: ["c-1", "c-2"],
      overlays,
    });
    const b = viewFrom("b", {
      ...DEFAULT_EXPLORER_STATE,
      selection: ["c-2", "c-3"],
      overlays,
    });
    const diff = diffSavedViews(a, b);
    expect(diff.overlays.changed).toBe(false);
    expect(diff.selection.changed).toBe(true);
    expect(diff.sameOverlaysDifferentSelection).toBe(true);
    expect(diff.selection.common).toEqual(["c-2"]);
    expect(diff.selection.added).toEqual(["c-3"]);
    expect(diff.selection.removed).toEqual(["c-1"]);
  });

  it("reports two identical views as identical", () => {
    const state: ExplorerState = {
      ...DEFAULT_EXPLORER_STATE,
      selection: ["x"],
      viewport: { cx: 0.4, cy: 0.6, scale: 2 },
    };
    const diff = diffSavedViews(viewFrom("a", state), viewFrom("b", state));
    expect(diff.identical).toBe(true);
    expect(diff.viewport.changed).toBe(false);
  });

  it("flags a viewport-only change", () => {
    const a = viewFrom("a", DEFAULT_EXPLORER_STATE);
    const b = viewFrom("b", {
      ...DEFAULT_EXPLORER_STATE,
      viewport: { cx: 0.5, cy: 0.5, scale: 4 },
    });
    const diff = diffSavedViews(a, b);
    expect(diff.viewport.changed).toBe(true);
    expect(diff.identical).toBe(false);
  });
});

// ── Diagnostic rendering ───────────────────────────────────────────

describe("ExplorerEmptyState — index diagnostic", () => {
  it("renders the missing-index diagnostic with a founder rebuild action", () => {
    const html = renderToStaticMarkup(
      <ExplorerEmptyState
        status="empty"
        embedded={0}
        total={12}
        canRebuild={true}
      />,
    );
    expect(html).toContain("Embedding index is missing");
    expect(html).toContain("Rebuild index");
    expect(html).toContain("embedded 0/12");
    expect(html).toContain('data-explorer-status="empty"');
  });

  it("gates the rebuild action away from non-founders", () => {
    const html = renderToStaticMarkup(
      <ExplorerEmptyState
        status="empty"
        embedded={0}
        total={12}
        canRebuild={false}
      />,
    );
    expect(html).not.toContain("Rebuild index");
    expect(html).toContain("Ask a founder to rebuild the index");
  });

  it("surfaces the API error message on the error diagnostic", () => {
    const html = renderToStaticMarkup(
      <ExplorerEmptyState
        status="error"
        embedded={0}
        total={0}
        message="HTTP 503"
        canRebuild={true}
      />,
    );
    expect(html).toContain("Embedding index is unavailable");
    expect(html).toContain("HTTP 503");
  });

  it("renders the stale diagnostic when the index lags the corpus", () => {
    const html = renderToStaticMarkup(
      <ExplorerEmptyState
        status="stale"
        embedded={40}
        total={100}
        canRebuild={true}
      />,
    );
    expect(html).toContain("Embedding index is stale");
    expect(html).toContain("embedded 40/100");
  });

  it("shows a rebuild-in-progress label", () => {
    const html = renderToStaticMarkup(
      <ExplorerEmptyState
        status="empty"
        embedded={0}
        total={3}
        canRebuild={true}
        rebuilding={true}
      />,
    );
    expect(html).toContain("Rebuilding index…");
  });
});
