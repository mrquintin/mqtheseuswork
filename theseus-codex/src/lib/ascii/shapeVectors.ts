/**
 * Shape-vector ASCII renderer — 6D variant.
 *
 * Adapted from Alex Harri's "ASCII characters are not pixels"
 * (alexharri.com/blog/ascii-rendering). The earlier build of this file
 * used only 2 sampling circles (upper + lower half of each cell), which
 * got us shape-aware selection but couldn't tell `p` from `q`, `-` from
 * `_`, or `/` from `\`. This version uses SIX sampling circles arranged
 * in a staggered 2×3 grid:
 *
 *     UL           UR            (upper-left, upper-right)
 *          ML           MR       (middle-left shifted down a hair,
 *                                 middle-right shifted up a hair —
 *                                 the staggering covers the gaps and
 *                                 gives better pickup for diagonals)
 *     LL           LR            (lower-left, lower-right)
 *
 * Each cell → 6 numbers (one per sampling circle), each number ∈ [0, 1].
 * Characters are pre-rasterized once at module load; each character's
 * shape vector is computed the same way. At render time we sample the
 * scene the same way, then find the nearest character by Euclidean
 * distance in 6-space. This is the full approach from the post.
 *
 * Performance: 6× more samples per cell than the old 2D version, but
 * our grid sizes (40–100 cols × 14–30 rows ≈ 1–3k cells) mean we're
 * still at ~15k samples/frame. That's comfortable for CPU at 30fps.
 * Nearest-neighbour lookup is brute-force over ~95 characters; a k-d
 * tree would help if grids get much bigger.
 */

/** The printable ASCII set we allow. */
export const ASCII_CHARS =
  " !\"#$%&'()*+,-./0123456789:;<=>?@" +
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ" +
  "[\\]^_`" +
  "abcdefghijklmnopqrstuvwxyz" +
  "{|}~";

export const CELL_W = 6; // px
export const CELL_H = 12; // px

/** Sampling circle radius — a bit smaller than in the 2D version because
 *  we now have six circles sharing the same cell, so they need to be
 *  tighter to avoid overlap. */
const SAMPLE_R = 2;

/** Six sampling-circle centres. Slightly staggered: middle circles are
 *  vertically offset from the upper/lower rows to cover diagonal chars. */
const CIRCLE_CENTRES: readonly (readonly [number, number])[] = [
  // UL             UR
  [CELL_W * 0.28, CELL_H * 0.22],
  [CELL_W * 0.72, CELL_H * 0.22],
  // ML (lowered)   MR (raised)
  [CELL_W * 0.28, CELL_H * 0.52],
  [CELL_W * 0.72, CELL_H * 0.48],
  // LL             LR
  [CELL_W * 0.28, CELL_H * 0.8],
  [CELL_W * 0.72, CELL_H * 0.8],
] as const;

/** Density threshold below which a pixel counts as ink. */
const INK_CUTOFF = 128;

/** 6-component shape vector, kept as a plain tuple for perf. */
export type ShapeVec = readonly [number, number, number, number, number, number];

export type ShapeEntry = {
  readonly char: string;
  readonly vector: ShapeVec;
};

/** Rasterize one character into a small offscreen canvas and compute its
 *  6D shape vector by counting ink density inside each sampling circle. */
function rasterizeAndComputeShape(
  ctx: CanvasRenderingContext2D,
  char: string,
  font: string,
): ShapeVec {
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, CELL_W, CELL_H);
  ctx.fillStyle = "#fff";
  ctx.font = font;
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  // 0.55 centres the glyph vertically with a small bias for descenders
  // (g, j, p, q, y) — matching the font-rendering behaviour we get on
  // the output canvas in AsciiCanvas.
  ctx.fillText(char, CELL_W * 0.5, CELL_H * 0.55);

  const img = ctx.getImageData(0, 0, CELL_W, CELL_H).data;

  const vec = new Array<number>(6) as [number, number, number, number, number, number];
  for (let c = 0; c < 6; c++) {
    const [cx, cy] = CIRCLE_CENTRES[c];
    let hits = 0;
    let total = 0;
    const x0 = Math.max(0, Math.floor(cx - SAMPLE_R));
    const x1 = Math.min(CELL_W, Math.ceil(cx + SAMPLE_R));
    const y0 = Math.max(0, Math.floor(cy - SAMPLE_R));
    const y1 = Math.min(CELL_H, Math.ceil(cy + SAMPLE_R));
    const r2 = SAMPLE_R * SAMPLE_R;
    for (let y = y0; y < y1; y++) {
      const dy = y + 0.5 - cy;
      for (let x = x0; x < x1; x++) {
        const dx = x + 0.5 - cx;
        if (dx * dx + dy * dy > r2) continue;
        total++;
        const idx = (y * CELL_W + x) * 4;
        if (img[idx] >= INK_CUTOFF) hits++;
      }
    }
    vec[c] = total > 0 ? hits / total : 0;
  }
  return vec;
}

/** Shape-vector table + per-component max (used for normalization). */
let cached: readonly ShapeEntry[] | null = null;
let cachedMaxes: ShapeVec = [1, 1, 1, 1, 1, 1] as const;

export function getShapeTable(): {
  entries: readonly ShapeEntry[];
  max: ShapeVec;
} {
  if (cached) return { entries: cached, max: cachedMaxes };
  if (typeof document === "undefined") {
    return { entries: [], max: cachedMaxes };
  }
  const canvas = document.createElement("canvas");
  canvas.width = CELL_W;
  canvas.height = CELL_H;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) {
    cached = [];
    return { entries: [], max: cachedMaxes };
  }

  const font = `${Math.floor(CELL_H * 0.85)}px "IBM Plex Mono", monospace`;

  const raw: ShapeEntry[] = [];
  const maxes: [number, number, number, number, number, number] = [0, 0, 0, 0, 0, 0];
  for (const char of ASCII_CHARS) {
    const v = rasterizeAndComputeShape(ctx, char, font);
    for (let i = 0; i < 6; i++) {
      if (v[i] > maxes[i]) maxes[i] = v[i];
    }
    raw.push({ char, vector: v });
  }
  // Normalize each component so every axis spans [0, 1]. Components that
  // are genuinely always zero stay zero (their axis just doesn't
  // contribute to lookups). Without normalization the shape-vector cluster
  // bunches in the bottom-left octant and lookups bias toward a few chars.
  const safe: ShapeVec = [
    maxes[0] > 0 ? maxes[0] : 1,
    maxes[1] > 0 ? maxes[1] : 1,
    maxes[2] > 0 ? maxes[2] : 1,
    maxes[3] > 0 ? maxes[3] : 1,
    maxes[4] > 0 ? maxes[4] : 1,
    maxes[5] > 0 ? maxes[5] : 1,
  ] as const;
  cached = raw.map(({ char, vector }) => ({
    char,
    vector: [
      vector[0] / safe[0],
      vector[1] / safe[1],
      vector[2] / safe[2],
      vector[3] / safe[3],
      vector[4] / safe[4],
      vector[5] / safe[5],
    ] as ShapeVec,
  }));
  cachedMaxes = safe;
  return { entries: cached, max: cachedMaxes };
}

/** Squared Euclidean distance in 6-space. Square-root skipped (monotonic). */
export function dist6(a: ShapeVec, b: ShapeVec): number {
  const d0 = a[0] - b[0];
  const d1 = a[1] - b[1];
  const d2 = a[2] - b[2];
  const d3 = a[3] - b[3];
  const d4 = a[4] - b[4];
  const d5 = a[5] - b[5];
  return d0 * d0 + d1 * d1 + d2 * d2 + d3 * d3 + d4 * d4 + d5 * d5;
}

/** Nearest-neighbour lookup. Brute-force over ~95 characters per call;
 *  for our grids that's under 5ms/frame in total on a modest laptop. */
export function pickChar(sample: ShapeVec, table: readonly ShapeEntry[]): string {
  let best = " ";
  let bestD = Infinity;
  for (const { char, vector } of table) {
    const d = dist6(vector, sample);
    if (d < bestD) {
      bestD = d;
      best = char;
    }
  }
  return best;
}

/** Global contrast enhancement (Harri's exponent-with-normalization). */
export function enhanceContrast(vec: ShapeVec, exponent: number): ShapeVec {
  if (exponent <= 1) return vec;
  const max = Math.max(vec[0], vec[1], vec[2], vec[3], vec[4], vec[5], 1e-6);
  return [
    Math.pow(vec[0] / max, exponent) * max,
    Math.pow(vec[1] / max, exponent) * max,
    Math.pow(vec[2] / max, exponent) * max,
    Math.pow(vec[3] / max, exponent) * max,
    Math.pow(vec[4] / max, exponent) * max,
    Math.pow(vec[5] / max, exponent) * max,
  ] as ShapeVec;
}
