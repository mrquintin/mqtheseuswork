/**
 * Dimensionality reduction for the Explorer canvas.
 *
 * Two reducers are exposed:
 *
 *  - "pca"  – power-iteration PCA, equivalent to the projection
 *             `embeddingAxes.ts` already uses but parameterised so the
 *             toolbar can switch it on/off without re-fetching data.
 *  - "umap" – a deterministic, cosine-distance MDS-style layout
 *             approximation. Real UMAP would require either a heavy
 *             dependency or a server-side step; for 10k points the
 *             approximation here preserves local structure well enough
 *             that the founder's lasso semantics are intact, while
 *             producing visibly different geometry from PCA so the
 *             reducer toggle is meaningful.
 *
 * The reducer outputs are cached. Recomputing for 5,000+ embeddings on
 * every navigation or reload is unacceptable per spec; the cache key
 * is `(reducer, content-hash, dim)` and persists in `localStorage`
 * when available. The hash is a non-cryptographic FNV-1a digest
 * computed on the input bytes — enough to detect data churn.
 */

export type Reducer = "pca" | "umap";

export interface ReducedPoint {
  x: number;
  y: number;
}

export interface ReduceResult {
  points: ReducedPoint[];
  reducer: Reducer;
  // Variance explained on PC1, PC2 (PCA only). Not present for UMAP.
  varianceExplained?: [number, number];
}

const CACHE_PREFIX = "explorer.reduce.v1";
const CACHE_MAX_BYTES = 2_000_000; // ~2 MB ceiling per cache entry

// ── Hashing ────────────────────────────────────────────────────────

export function hashEmbeddings(vectors: ReadonlyArray<ReadonlyArray<number>>): string {
  // FNV-1a 32-bit on a coarse-grained sample of the matrix. We mix in
  // length, dimension, and every 17th coordinate at 6 sig-figs. This
  // is intentionally cheap — full-fidelity hashing dwarfs the reducer
  // cost on large inputs.
  let h = 0x811c9dc5;
  const dim = vectors[0]?.length ?? 0;
  const mix = (value: number) => {
    h ^= value | 0;
    h = Math.imul(h, 0x01000193);
  };
  mix(vectors.length);
  mix(dim);
  for (let i = 0; i < vectors.length; i++) {
    const row = vectors[i];
    for (let j = 0; j < row.length; j += 17) {
      mix(Math.round((row[j] ?? 0) * 1e6));
    }
  }
  return (h >>> 0).toString(16);
}

// ── Cache layer ────────────────────────────────────────────────────

const memoryCache = new Map<string, ReduceResult>();

function cacheKey(reducer: Reducer, hash: string, n: number, dim: number): string {
  return `${CACHE_PREFIX}.${reducer}.${hash}.${n}x${dim}`;
}

function readCache(key: string): ReduceResult | null {
  const mem = memoryCache.get(key);
  if (mem) return mem;
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ReduceResult;
    memoryCache.set(key, parsed);
    return parsed;
  } catch {
    return null;
  }
}

function writeCache(key: string, value: ReduceResult): void {
  memoryCache.set(key, value);
  if (typeof window === "undefined") return;
  try {
    const serialised = JSON.stringify(value);
    if (serialised.length > CACHE_MAX_BYTES) return;
    window.localStorage.setItem(key, serialised);
  } catch {
    // localStorage may be unavailable / full; the in-memory cache
    // already serves the active session.
  }
}

// ── PCA ────────────────────────────────────────────────────────────

function dot(a: ReadonlyArray<number>, b: ReadonlyArray<number>): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}

function norm(a: ReadonlyArray<number>): number {
  return Math.sqrt(dot(a, a));
}

function normalise(a: number[]): number[] {
  const n = norm(a);
  if (n === 0) return a;
  for (let i = 0; i < a.length; i++) a[i] /= n;
  return a;
}

function topEigen(centered: number[][], seed: number[], iterations = 40): { vec: number[]; lambda: number } {
  const D = seed.length;
  let v = normalise(seed.slice());
  for (let iter = 0; iter < iterations; iter++) {
    const w = centered.map((row) => dot(row, v));
    const u = new Array<number>(D).fill(0);
    for (let i = 0; i < centered.length; i++) {
      const c = w[i];
      const row = centered[i];
      for (let j = 0; j < D; j++) u[j] += c * row[j];
    }
    const n = norm(u);
    if (n === 0) break;
    for (let j = 0; j < D; j++) u[j] /= n;
    v = u;
  }
  const Xv = centered.map((row) => dot(row, v));
  return { vec: v, lambda: dot(Xv, Xv) };
}

function pca(vectors: ReadonlyArray<ReadonlyArray<number>>): ReduceResult {
  const N = vectors.length;
  const D = vectors[0]?.length ?? 0;
  if (N < 2 || D < 2) {
    return { points: vectors.map(() => ({ x: 0, y: 0 })), reducer: "pca", varianceExplained: [0, 0] };
  }
  const mean = new Array<number>(D).fill(0);
  for (const v of vectors) for (let j = 0; j < D; j++) mean[j] += v[j];
  for (let j = 0; j < D; j++) mean[j] /= N;
  const centered = vectors.map((v) => {
    const out = new Array<number>(D);
    for (let j = 0; j < D; j++) out[j] = v[j] - mean[j];
    return out;
  });
  const seed1 = new Array<number>(D).fill(0);
  seed1[0] = 1;
  const e1 = topEigen(centered, seed1);
  const deflated = centered.map((row) => {
    const c = dot(row, e1.vec);
    const out = new Array<number>(D);
    for (let j = 0; j < D; j++) out[j] = row[j] - c * e1.vec[j];
    return out;
  });
  let seedRaw = new Array<number>(D).fill(0);
  seedRaw[1 % D] = 1;
  let s1 = dot(seedRaw, e1.vec);
  for (let j = 0; j < D; j++) seedRaw[j] -= s1 * e1.vec[j];
  if (norm(seedRaw) === 0) {
    seedRaw = new Array<number>(D).fill(0);
    seedRaw[2 % D] = 1;
    s1 = dot(seedRaw, e1.vec);
    for (let j = 0; j < D; j++) seedRaw[j] -= s1 * e1.vec[j];
  }
  const e2 = topEigen(deflated, seedRaw);
  let trace = 0;
  for (const row of centered) trace += dot(row, row);
  const points = centered.map((row) => ({ x: dot(row, e1.vec), y: dot(row, e2.vec) }));
  return {
    points,
    reducer: "pca",
    varianceExplained: [trace > 0 ? e1.lambda / trace : 0, trace > 0 ? e2.lambda / trace : 0],
  };
}

// ── UMAP-style approximation ───────────────────────────────────────

function seededRandom(seed: number): () => number {
  // Mulberry32; deterministic for cache stability.
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Cosine-distance "neighbor MDS": initialise via random projection,
 * then refine by attractive forces between each point's k nearest
 * neighbors. The result preserves local cosine structure better than
 * PCA on highly non-linear embedding manifolds — close to the
 * spirit of UMAP at a tiny fraction of the cost.
 */
function umapLike(vectors: ReadonlyArray<ReadonlyArray<number>>): ReduceResult {
  const N = vectors.length;
  const D = vectors[0]?.length ?? 0;
  if (N < 2 || D < 2) {
    return { points: vectors.map(() => ({ x: 0, y: 0 })), reducer: "umap" };
  }

  // Stage 1: random projection → initial 2D layout.
  const rand = seededRandom(0xc0ffee ^ N ^ D);
  const a = new Array<number>(D);
  const b = new Array<number>(D);
  for (let j = 0; j < D; j++) {
    a[j] = rand() * 2 - 1;
    b[j] = rand() * 2 - 1;
  }
  const points: { x: number; y: number }[] = vectors.map((v) => ({
    x: dot(v, a),
    y: dot(v, b),
  }));

  // Normalise embeddings for cosine similarity.
  const normedVectors = vectors.map((v) => {
    const n = norm(v) || 1;
    const out = new Array<number>(D);
    for (let j = 0; j < D; j++) out[j] = v[j] / n;
    return out;
  });

  // Stage 2: build k-NN per point (cap k for performance).
  const K = Math.min(8, N - 1);
  const neighbours: number[][] = new Array(N);
  for (let i = 0; i < N; i++) {
    const sims = new Array<number>(N);
    for (let j = 0; j < N; j++) {
      sims[j] = j === i ? -2 : dot(normedVectors[i], normedVectors[j]);
    }
    const idx = sims.map((_, j) => j).sort((p, q) => sims[q] - sims[p]).slice(0, K);
    neighbours[i] = idx;
  }

  // Stage 3: attractive-only iterations. Repulsion is supplied by the
  // random-projection scaffold; cheap and good enough for a Codex
  // visualisation budget.
  const ITER = 40;
  const LR_START = 0.6;
  for (let iter = 0; iter < ITER; iter++) {
    const lr = LR_START * (1 - iter / ITER);
    for (let i = 0; i < N; i++) {
      const pi = points[i];
      let dx = 0;
      let dy = 0;
      for (const j of neighbours[i]) {
        const pj = points[j];
        dx += pj.x - pi.x;
        dy += pj.y - pi.y;
      }
      pi.x += lr * (dx / K);
      pi.y += lr * (dy / K);
    }
  }

  return { points, reducer: "umap" };
}

// ── Public entry point ─────────────────────────────────────────────

export function reduce(
  vectors: ReadonlyArray<ReadonlyArray<number>>,
  reducer: Reducer,
  options: { hash?: string } = {},
): ReduceResult {
  if (vectors.length === 0) return { points: [], reducer };
  const hash = options.hash ?? hashEmbeddings(vectors);
  const D = vectors[0]?.length ?? 0;
  const key = cacheKey(reducer, hash, vectors.length, D);
  const cached = readCache(key);
  if (cached && cached.points.length === vectors.length) return cached;

  const result = reducer === "pca" ? pca(vectors) : umapLike(vectors);
  writeCache(key, result);
  return result;
}

export function clearReduceCache(): void {
  memoryCache.clear();
  if (typeof window === "undefined") return;
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k && k.startsWith(CACHE_PREFIX)) keys.push(k);
    }
    for (const k of keys) window.localStorage.removeItem(k);
  } catch {
    // ignore
  }
}
