/**
 * Shape-vector ASCII renderer — precomputes, for every printable ASCII
 * character, how much of its visible mass falls inside two "sampling
 * circles" arranged vertically inside the character cell (one in the upper
 * half, one in the lower half). This 2D shape vector lets us pick the
 * character that best matches the shape of the corresponding image region,
 * instead of just matching overall lightness — a technique adapted from
 * Alex Harri's "ASCII characters are not pixels" (alexharri.com/blog/ascii-rendering).
 *
 * Two-dimensional shape vectors (vs the 6D variant in the post) are good
 * enough for our 3D scenes because our geometry is mostly wireframe and
 * large silhouette shapes. 2D runs comfortably on CPU at 30fps for the
 * ~80×40 grids we need, without any GPU shaders.
 *
 * Pipeline:
 *   1. Precompute: rasterize each printable ASCII character into a small
 *      bitmap, compute its 2D shape vector (upper/lower mass).
 *   2. Normalize all shape vectors by each component's max (so they span
 *      the [0, 1]² space and every character is reachable).
 *   3. At render time, for each grid cell, sample its image region through
 *      the same two circles → 2D sampling vector.
 *   4. Look up the character whose shape vector is closest (Euclidean).
 *   5. Optional: contrast enhancement (raise vector to an exponent inside
 *      a per-vector normalization) to sharpen boundaries.
 *
 * Precomputation is amortized at module load; the renderer itself is a
 * tight inner loop suitable for 30fps on modern devices.
 */

/** The printable ASCII set we allow. Excludes chars that look the same in
 *  most monospace fonts (smart quotes, backslash — kept) and control chars. */
export const ASCII_CHARS =
  " !\"#$%&'()*+,-./0123456789:;<=>?@" +
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ" +
  "[\\]^_`" +
  "abcdefghijklmnopqrstuvwxyz" +
  "{|}~";

/** Pre-computed shape vector table. Each entry: { char, vector: [upper, lower] }. */
export type ShapeEntry = {
  readonly char: string;
  readonly vector: readonly [number, number];
};

/** Global cell aspect — width-to-height ratio of one character cell in the
 *  monospace font we target. Most monospace fonts are ~0.55 wide vs tall;
 *  we pick an integer-friendly ratio the sampler can work with. */
export const CELL_W = 6; // px
export const CELL_H = 12; // px

/** Radius of each sampling circle inside a cell. A little less than half the
 *  cell width so the two circles don't overlap horizontally much. */
const SAMPLE_R = 3;

/** Centre of the upper / lower sampling circles within a cell. */
const UPPER_CENTRE_Y = CELL_H * 0.3;
const LOWER_CENTRE_Y = CELL_H * 0.72;
const CENTRE_X = CELL_W * 0.5;

/** Density threshold below which a pixel counts as "ink" (0 = black,
 *  255 = white). We invert logic based on whether the renderer draws
 *  light-on-dark; see {@link computeShapeVector}. */
const INK_CUTOFF = 128;

/** Rasterize one character into a small offscreen canvas and compute its
 *  2D shape vector. Runs once per character at module load. */
function rasterizeAndComputeShape(
  ctx: CanvasRenderingContext2D,
  char: string,
  font: string,
): readonly [number, number] {
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, CELL_W, CELL_H);
  ctx.fillStyle = "#fff";
  ctx.font = font;
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  // Slightly below centre so descenders render correctly.
  ctx.fillText(char, CENTRE_X, CELL_H * 0.55);

  const img = ctx.getImageData(0, 0, CELL_W, CELL_H).data;

  // For each sampling circle, count how many pixels inside the circle are
  // "ink" (i.e. the character was drawn there). Normalize by total pixels.
  const sample = (centreY: number): number => {
    let hits = 0;
    let total = 0;
    // Tighter iteration: bounding box of the circle, then circle test.
    const x0 = Math.max(0, Math.floor(CENTRE_X - SAMPLE_R));
    const x1 = Math.min(CELL_W, Math.ceil(CENTRE_X + SAMPLE_R));
    const y0 = Math.max(0, Math.floor(centreY - SAMPLE_R));
    const y1 = Math.min(CELL_H, Math.ceil(centreY + SAMPLE_R));
    for (let y = y0; y < y1; y++) {
      const dy = y + 0.5 - centreY;
      for (let x = x0; x < x1; x++) {
        const dx = x + 0.5 - CENTRE_X;
        if (dx * dx + dy * dy > SAMPLE_R * SAMPLE_R) continue;
        total++;
        // Luminance approx from R channel (we drew white on black).
        const idx = (y * CELL_W + x) * 4;
        if (img[idx] >= INK_CUTOFF) hits++;
      }
    }
    return total > 0 ? hits / total : 0;
  };

  return [sample(UPPER_CENTRE_Y), sample(LOWER_CENTRE_Y)];
}

/** Build the shape-vector table. This runs once, lazily, the first time
 *  any ASCII rendering is requested, and caches the result on module.
 *  SSR-safe: returns an empty array during SSR (no `document`), and the
 *  first client-side render triggers the actual build. */
let cached: readonly ShapeEntry[] | null = null;
let cachedMaxes: readonly [number, number] = [1, 1];

export function getShapeTable(): {
  entries: readonly ShapeEntry[];
  max: readonly [number, number];
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

  // Use the same font the renderer will use. Browser font-loading is async,
  // so callers should wait until `document.fonts.ready` before building the
  // table if they care about exact character shapes.
  const font = `${Math.floor(CELL_H * 0.85)}px "IBM Plex Mono", monospace`;

  const raw: ShapeEntry[] = [];
  let maxU = 0;
  let maxL = 0;
  for (const char of ASCII_CHARS) {
    const v = rasterizeAndComputeShape(ctx, char, font);
    if (v[0] > maxU) maxU = v[0];
    if (v[1] > maxL) maxL = v[1];
    raw.push({ char, vector: v });
  }
  // Normalize so component maxes are both 1.0. If a component is genuinely
  // zero across the whole alphabet, avoid dividing by zero by treating the
  // max as 1 (the component simply never contributes).
  const safeMaxU = maxU > 0 ? maxU : 1;
  const safeMaxL = maxL > 0 ? maxL : 1;
  cached = raw.map(({ char, vector }) => ({
    char,
    vector: [vector[0] / safeMaxU, vector[1] / safeMaxL] as const,
  }));
  cachedMaxes = [safeMaxU, safeMaxL] as const;
  return { entries: cached, max: cachedMaxes };
}

/** Euclidean-squared distance between two 2-vectors. Square-root is skipped
 *  because monotonic transforms don't affect nearest-neighbour lookups. */
export function dist2(a: readonly [number, number], b: readonly [number, number]): number {
  const du = a[0] - b[0];
  const dl = a[1] - b[1];
  return du * du + dl * dl;
}

/** Find the best-matching ASCII character for a sampling vector via
 *  brute-force nearest-neighbour search. For our grid sizes (≤ ~5000 cells)
 *  and ~95 characters, this is ~500K distance computations per frame —
 *  comfortable on CPU. A k-d tree would be faster for grids 5×+ larger. */
export function pickChar(
  samplingVector: readonly [number, number],
  table: readonly ShapeEntry[],
): string {
  let best = " ";
  let bestD = Infinity;
  for (const { char, vector } of table) {
    const d = dist2(vector, samplingVector);
    if (d < bestD) {
      bestD = d;
      best = char;
    }
  }
  return best;
}

/** Apply the global contrast enhancement described in the blog: normalize
 *  vector by its own max component, raise to a power, then denormalize.
 *  Strengthens the shape of the vector (pulls small components toward 0)
 *  without shrinking its overall magnitude. */
export function enhanceContrast(
  vector: readonly [number, number],
  exponent: number,
): [number, number] {
  if (exponent <= 1) return [vector[0], vector[1]];
  const max = Math.max(vector[0], vector[1], 1e-6);
  const n0 = vector[0] / max;
  const n1 = vector[1] / max;
  return [Math.pow(n0, exponent) * max, Math.pow(n1, exponent) * max];
}
