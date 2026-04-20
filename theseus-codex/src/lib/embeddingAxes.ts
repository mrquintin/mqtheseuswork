/**
 * PCA projection of conclusion embeddings onto a 2D plane.
 *
 * Deliberately from-scratch: the Codex only has tens to low-thousands
 * of conclusions per org, so a tiny in-process power-iteration PCA is
 * fine. No external linear algebra dependency.
 *
 * Strategy:
 *   1. Parse each conclusion's JSON embedding into a float[] of equal
 *      dimension D.
 *   2. Centre the matrix (subtract mean vector).
 *   3. Top-2 eigenvectors of the D×D covariance matrix via power
 *      iteration with Gram–Schmidt deflation.
 *   4. Project every row onto those eigenvectors.
 *   5. Label each axis by examining the topicHints at each pole.
 */

export interface ProjectedConclusion {
  id: string;
  text: string;
  x: number;
  y: number;
  topicHint: string;
  confidenceTier: string;
}

export interface SemanticAxis {
  index: number;
  label: string;
  varianceExplained: number;
  positivePole: string[];
  negativePole: string[];
}

export interface EmbeddingProjection {
  conclusions: ProjectedConclusion[];
  axes: SemanticAxis[];
}

export interface ConclusionWithEmbedding {
  id: string;
  text: string;
  topicHint: string;
  confidenceTier: string;
  embeddingJson: string | null;
}

// ── Linear algebra helpers ──────────────────────────────────────────

function dot(a: number[], b: number[]): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}

function scale(a: number[], s: number): number[] {
  return a.map((v) => v * s);
}

function sub(a: number[], b: number[]): number[] {
  return a.map((v, i) => v - b[i]);
}

function norm(a: number[]): number {
  return Math.sqrt(dot(a, a));
}

function normalize(a: number[]): number[] {
  const n = norm(a);
  if (n === 0) return a;
  return scale(a, 1 / n);
}

/**
 * Given the centred embedding matrix X (N×D), approximate the top
 * eigenvector of Xᵀ X via power iteration. We never materialise Xᵀ X
 * — we just apply it as a sequence of matrix-vector products.
 */
function topEigenvector(
  centered: number[][],
  init: number[],
  iterations = 40,
): { vec: number[]; eigenvalue: number } {
  const D = init.length;
  let v = normalize(init);
  for (let iter = 0; iter < iterations; iter++) {
    // w = X v  (length N)
    const w = centered.map((row) => dot(row, v));
    // u = Xᵀ w (length D)
    const u = new Array(D).fill(0) as number[];
    for (let i = 0; i < centered.length; i++) {
      const coeff = w[i];
      const row = centered[i];
      for (let j = 0; j < D; j++) u[j] += coeff * row[j];
    }
    const n = norm(u);
    if (n === 0) break;
    v = scale(u, 1 / n);
  }
  // Eigenvalue estimate via Rayleigh quotient: ‖X v‖²
  const Xv = centered.map((row) => dot(row, v));
  const eigenvalue = dot(Xv, Xv);
  return { vec: v, eigenvalue };
}

// ── Public entry point ─────────────────────────────────────────────

export function computeProjection(
  input: ConclusionWithEmbedding[],
): EmbeddingProjection {
  const parsed: {
    c: ConclusionWithEmbedding;
    vec: number[];
  }[] = [];
  for (const c of input) {
    if (!c.embeddingJson) continue;
    try {
      const v = JSON.parse(c.embeddingJson);
      if (Array.isArray(v) && v.length > 0 && v.every((x) => typeof x === "number")) {
        parsed.push({ c, vec: v as number[] });
      }
    } catch {
      // skip
    }
  }
  if (parsed.length < 3) {
    return { conclusions: [], axes: [] };
  }
  const D = parsed[0].vec.length;
  // Guard against ragged dimensions: skip any row whose length differs.
  const clean = parsed.filter((p) => p.vec.length === D);
  if (clean.length < 3) {
    return { conclusions: [], axes: [] };
  }

  // 1. Centre
  const mean = new Array(D).fill(0) as number[];
  for (const p of clean) {
    for (let j = 0; j < D; j++) mean[j] += p.vec[j];
  }
  for (let j = 0; j < D; j++) mean[j] /= clean.length;
  const centered = clean.map((p) => sub(p.vec, mean));

  // 2. Top-1 eigenvector via power iteration
  const seed1 = new Array(D).fill(0).map((_, i) => (i === 0 ? 1 : 0)) as number[];
  const { vec: e1, eigenvalue: lam1 } = topEigenvector(centered, seed1);

  // 3. Deflate and find top-2: project out e1 from each row, then
  //    re-run power iteration on the deflated matrix.
  const deflated = centered.map((row) => {
    const coeff = dot(row, e1);
    return sub(row, scale(e1, coeff));
  });
  // Seed with a vector orthogonal to e1 to avoid collapsing back to it.
  let seed2 = new Array(D).fill(0).map((_, i) => (i === 1 ? 1 : 0)) as number[];
  seed2 = sub(seed2, scale(e1, dot(seed2, e1)));
  if (norm(seed2) === 0) {
    seed2 = new Array(D).fill(0).map((_, i) => (i === 2 ? 1 : 0)) as number[];
    seed2 = sub(seed2, scale(e1, dot(seed2, e1)));
  }
  const { vec: e2, eigenvalue: lam2 } = topEigenvector(deflated, seed2);

  // 4. Project each row
  const projections = clean.map((p, i) => ({
    c: p.c,
    x: dot(centered[i], e1),
    y: dot(centered[i], e2),
  }));

  // 5. Variance explained: λ_k / Σ‖centered‖². The full trace is
  //    Σᵢ‖centeredᵢ‖² = Σ eigenvalues.
  let trace = 0;
  for (const row of centered) trace += dot(row, row);
  const var1 = trace > 0 ? lam1 / trace : 0;
  const var2 = trace > 0 ? lam2 / trace : 0;

  // 6. Axis labelling via topicHint sampling at the poles
  const sortedByX = [...projections].sort((a, b) => b.x - a.x);
  const sortedByY = [...projections].sort((a, b) => b.y - a.y);
  const axis1 = buildAxis(0, sortedByX, var1);
  const axis2 = buildAxis(1, sortedByY, var2);

  return {
    conclusions: projections.map((p) => ({
      id: p.c.id,
      text: p.c.text,
      x: p.x,
      y: p.y,
      topicHint: p.c.topicHint || "",
      confidenceTier: p.c.confidenceTier,
    })),
    axes: [axis1, axis2],
  };
}

function buildAxis(
  index: number,
  sorted: { c: ConclusionWithEmbedding }[],
  varianceExplained: number,
): SemanticAxis {
  const positive = sorted.slice(0, 3).map((p) => p.c.topicHint || p.c.text.slice(0, 40));
  const negative = sorted
    .slice(-3)
    .reverse()
    .map((p) => p.c.topicHint || p.c.text.slice(0, 40));
  const posLabel = dominantTopic(positive);
  const negLabel = dominantTopic(negative);
  const axisName = index === 0 ? "PC1" : "PC2";
  const label =
    posLabel && negLabel && posLabel !== negLabel
      ? `${negLabel} ↔ ${posLabel}`
      : `${axisName} (no dominant topic)`;
  return {
    index,
    label,
    varianceExplained,
    positivePole: positive,
    negativePole: negative,
  };
}

function dominantTopic(samples: string[]): string {
  const counts: Record<string, number> = {};
  for (const s of samples) {
    const k = (s || "").trim().toLowerCase();
    if (!k) continue;
    counts[k] = (counts[k] || 0) + 1;
  }
  let best = "";
  let bestCount = 0;
  for (const [k, v] of Object.entries(counts)) {
    if (v > bestCount) {
      best = k;
      bestCount = v;
    }
  }
  return best ? best.replace(/\b\w/g, (ch) => ch.toUpperCase()) : "";
}
