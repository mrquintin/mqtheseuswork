import { describe, expect, it } from "vitest";

import {
  computeBounds,
  filterOverlayEdges,
  lassoSelect,
  pointInPolygon,
  type ExplorerEdge,
} from "@/components/ExplorerCanvas";
import { hashEmbeddings, reduce } from "@/lib/dimReduce";
import {
  DEFAULT_EXPLORER_STATE,
  decodeExplorerState,
  encodeExplorerState,
  explorerStateToQuery,
  type ExplorerState,
} from "@/lib/explorerState";

// Synthetic embedding fixtures: three planted clusters in 8-D space.
// Each cluster has 6 members plus one outlier, so we can verify lasso
// selection, projection, and overlay isolation deterministically.
function plantCluster(
  base: number[],
  n: number,
  jitter: number,
  seed: number,
): number[][] {
  const out: number[][] = [];
  let s = seed;
  const rand = () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return (s & 0xffff) / 0xffff - 0.5;
  };
  for (let i = 0; i < n; i++) {
    out.push(base.map((b) => b + rand() * jitter));
  }
  return out;
}

const CLUSTER_A = plantCluster([1, 0, 0, 0, 0, 0, 0, 0], 6, 0.05, 1);
const CLUSTER_B = plantCluster([0, 1, 0, 0, 0, 0, 0, 0], 6, 0.05, 2);
const CLUSTER_C = plantCluster([0, 0, 1, 0, 0, 0, 0, 0], 6, 0.05, 3);

const ALL_EMBEDDINGS = [...CLUSTER_A, ...CLUSTER_B, ...CLUSTER_C];
const ALL_IDS = ALL_EMBEDDINGS.map((_, i) => `c-${i}`);

const ID_BY_INDEX = (i: number) => ALL_IDS[i];
const CLUSTER_A_IDS = new Set(CLUSTER_A.map((_, i) => ID_BY_INDEX(i)));
const CLUSTER_B_IDS = new Set(
  CLUSTER_B.map((_, i) => ID_BY_INDEX(CLUSTER_A.length + i)),
);

// ── Lasso ──────────────────────────────────────────────────────────

describe("pointInPolygon", () => {
  it("treats a square as inside / outside correctly", () => {
    const square = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ];
    expect(pointInPolygon({ x: 5, y: 5 }, square)).toBe(true);
    expect(pointInPolygon({ x: -1, y: 5 }, square)).toBe(false);
    expect(pointInPolygon({ x: 11, y: 5 }, square)).toBe(false);
  });

  it("returns false for degenerate polygons", () => {
    expect(pointInPolygon({ x: 1, y: 1 }, [])).toBe(false);
    expect(pointInPolygon({ x: 1, y: 1 }, [{ x: 0, y: 0 }, { x: 1, y: 1 }])).toBe(false);
  });
});

describe("lassoSelect on planted regions", () => {
  it("recovers the planted cluster", () => {
    const result = reduce(ALL_EMBEDDINGS, "pca");
    expect(result.points).toHaveLength(ALL_EMBEDDINGS.length);

    // Build the polygon to be a small box around the centroid of the
    // planted cluster A's projected coordinates. If the lasso covers
    // the planted region, every member of A is selected and no member
    // of B or C leaks in.
    const aProj = result.points.slice(0, CLUSTER_A.length);
    let cx = 0;
    let cy = 0;
    for (const p of aProj) {
      cx += p.x;
      cy += p.y;
    }
    cx /= aProj.length;
    cy /= aProj.length;
    const r = 0.4;
    const polygon = [
      { x: cx - r, y: cy - r },
      { x: cx + r, y: cy - r },
      { x: cx + r, y: cy + r },
      { x: cx - r, y: cy + r },
    ];

    const points = result.points.map((p, i) => ({ id: ID_BY_INDEX(i), x: p.x, y: p.y }));
    const selected = new Set(lassoSelect(points, polygon));

    // The lasso must cover every planted member. If even one member is
    // missing, the test fails — that's the regression we care about.
    for (const id of CLUSTER_A_IDS) expect(selected.has(id)).toBe(true);
    // Cluster B / C members must not be selected. They were planted on
    // orthogonal axes so a tight box around A excludes them.
    for (let i = CLUSTER_A.length; i < ALL_IDS.length; i++) {
      expect(selected.has(ID_BY_INDEX(i))).toBe(false);
    }
  });
});

// ── Overlays ───────────────────────────────────────────────────────

describe("filterOverlayEdges", () => {
  // Two clusters; one contradiction edge inside A, one inside B, one
  // crossing A↔B. Test that with cluster A selected and contradicts
  // toggle on, only the A-internal edge is returned. Crucially the
  // crossing edge must NOT bleed in — that's the regression spec F
  // calls out.
  const aId = "a1";
  const aId2 = "a2";
  const bId = "b1";
  const bId2 = "b2";
  const edges: ExplorerEdge[] = [
    { a: aId, b: aId2, kind: "contradicts", score: 0.8 },
    { a: bId, b: bId2, kind: "contradicts", score: 0.7 },
    { a: aId, b: bId, kind: "contradicts", score: 0.9 },
    { a: aId, b: aId2, kind: "supports", score: 0.5 },
  ];

  it("renders globally when no selection is active", () => {
    const out = filterOverlayEdges(edges, { contradicts: true, supports: false }, new Set());
    expect(out).toHaveLength(3);
  });

  it("respects overlay toggles", () => {
    const out = filterOverlayEdges(edges, { contradicts: false, supports: false }, new Set());
    expect(out).toHaveLength(0);
  });

  it("does not bleed across selections", () => {
    const selectionA = new Set([aId, aId2]);
    const out = filterOverlayEdges(
      edges,
      { contradicts: true, supports: false },
      selectionA,
    );
    expect(out).toHaveLength(1);
    expect(out[0].a).toBe(aId);
    expect(out[0].b).toBe(aId2);

    // The crossing edge a↔b must not survive even though one endpoint
    // is in the selection.
    const hasCrossing = out.some(
      (e) => (e.a === aId && e.b === bId) || (e.a === bId && e.b === aId),
    );
    expect(hasCrossing).toBe(false);
  });

  it("can mix kinds when both overlays are on and selection is non-empty", () => {
    const selectionA = new Set([aId, aId2]);
    const out = filterOverlayEdges(
      edges,
      { contradicts: true, supports: true },
      selectionA,
    );
    expect(out).toHaveLength(2);
    expect(new Set(out.map((e) => e.kind))).toEqual(new Set(["contradicts", "supports"]));
  });
});

// ── computeBounds ──────────────────────────────────────────────────

describe("computeBounds", () => {
  it("returns null when empty", () => {
    expect(computeBounds([])).toBeNull();
  });

  it("computes axis-aligned extent", () => {
    const out = computeBounds([
      { x: -1, y: 2 },
      { x: 3, y: -4 },
      { x: 0.5, y: 0.5 },
    ]);
    expect(out).toEqual({ minX: -1, maxX: 3, minY: -4, maxY: 2 });
  });
});

// ── URL state round-trip ───────────────────────────────────────────

describe("explorer URL state codec", () => {
  it("round-trips defaults to an empty query", () => {
    const params = encodeExplorerState(DEFAULT_EXPLORER_STATE);
    expect(params.toString()).toBe("");
    expect(decodeExplorerState(params)).toEqual(DEFAULT_EXPLORER_STATE);
  });

  it("round-trips a non-trivial state losslessly", () => {
    const state: ExplorerState = {
      reducer: "umap",
      selection: ["c-3", "c-1", "c-2"],
      overlays: { contradicts: true, supports: false },
      focused: "c-1",
      viewport: { cx: 0.5, cy: 0.5, scale: 1 },
    };
    const encoded = encodeExplorerState(state);
    const decoded = decodeExplorerState(encoded);
    // The codec sorts and de-duplicates the selection, so compare as a set.
    expect(new Set(decoded.selection)).toEqual(new Set(state.selection));
    expect(decoded.reducer).toBe(state.reducer);
    expect(decoded.overlays).toEqual(state.overlays);
    expect(decoded.focused).toBe(state.focused);
  });

  it("ignores unknown reducer values", () => {
    const decoded = decodeExplorerState("r=banana&sel=a,b");
    expect(decoded.reducer).toBe(DEFAULT_EXPLORER_STATE.reducer);
    expect(new Set(decoded.selection)).toEqual(new Set(["a", "b"]));
  });

  it("explorerStateToQuery prefixes with ? when non-empty", () => {
    expect(explorerStateToQuery(DEFAULT_EXPLORER_STATE)).toBe("");
    const q = explorerStateToQuery({
      ...DEFAULT_EXPLORER_STATE,
      reducer: "umap",
    });
    expect(q.startsWith("?")).toBe(true);
    expect(q).toContain("r=umap");
  });
});

// ── Hashing / cache key stability ─────────────────────────────────-

describe("hashEmbeddings", () => {
  it("is stable for identical input", () => {
    const a = hashEmbeddings(ALL_EMBEDDINGS);
    const b = hashEmbeddings(ALL_EMBEDDINGS);
    expect(a).toBe(b);
  });

  it("differs when data changes", () => {
    const a = hashEmbeddings(ALL_EMBEDDINGS);
    const mutated = ALL_EMBEDDINGS.map((row) => row.slice());
    mutated[0][0] += 1.0;
    const b = hashEmbeddings(mutated);
    expect(a).not.toBe(b);
  });
});
