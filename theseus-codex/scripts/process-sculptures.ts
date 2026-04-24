/**
 * Process raw STL museum scans into compact binary meshes that the Codex
 * ships with and renders as amber ASCII.
 *
 * Input:  binary STL files (high-poly photogrammetry — one of ours, the
 *         Augustus Prima Porta, is 503 MB / 10M triangles), loaded from:
 *           1) ./assets/sculptures/raw-stl/   (preferred, gitignored)
 *           2) ~/Downloads/                   (legacy fallback)
 * Output: a tiny `.mesh.bin` per sculpture (<100 KB, ~2500 triangles)
 *         that the runtime fetches, parses, and paints.
 *
 * Memory-efficiency note
 * ----------------------
 * An earlier version of this script stored triangles as JS objects.
 * That's ~100 bytes per triangle via object headers + arrays, so the
 * Augustus scan needed ~1 GB of JS heap just to hold the parsed mesh,
 * and Node OOM'd at 4 GB. This version stores triangles in a single
 * Float32Array (36 bytes per triangle — the theoretical minimum for 9
 * float32 vertices), and for files above a threshold it stride-subsamples
 * during the parse so we never allocate more than ~15 MB of mesh memory
 * regardless of input size.
 *
 * Pipeline per model
 * ------------------
 *   1. Parse binary STL into Float32Array. If the file has more than
 *      `PARSE_BUDGET` triangles, stride-skip during parse so we keep
 *      ~PARSE_BUDGET of them — deterministic uniform subsampling, which
 *      is safe because the vertex clustering in step 4 dominates.
 *   2. Bounding box.
 *   3. Optional axis swap (Y-up). Some scans are Z-up (CT / some
 *      photogrammetry tools); a standing figure's longest dimension is
 *      its height, so if the longest bbox axis isn't already Y we swap.
 *   4. Normalize: centre at origin, scale so longest axis maps to [-1, 1].
 *   5. Vertex-cluster decimate to the target triangle count.
 *   6. Write compact format:
 *        bytes 0-3 : magic "STA1"
 *        bytes 4-7 : triangle count (uint32 LE)
 *        body      : N triangles × 9 float32 (36 bytes each)
 *
 * Running
 * -------
 *   npx tsx --max-old-space-size=2048 scripts/process-sculptures.ts
 *
 * After running, commit the output `.mesh.bin` files under
 * public/sculptures/.
 */

import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  existsSync,
  statSync,
} from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

/** Max triangles to keep from the raw STL before clustering. Stride-
 *  subsampled during parse so even a 10M-triangle input fits in ~15 MB. */
const PARSE_BUDGET = 400_000;

type Vec3 = readonly [number, number, number];

/** Triangles live as a flat Float32Array — 9 floats per triangle (Ax,Ay,Az,Bx,By,Bz,Cx,Cy,Cz). */
type MeshVerts = Float32Array;

const RAW_STL_DIR = join(process.cwd(), "assets", "sculptures", "raw-stl");
const DOWNLOADS = join(homedir(), "Downloads");
interface ModelSpec {
  file: string;
  slug: string;
  targetTris: number;
  /**
   * Skip the automatic "swap longest axis → Y" reorientation.
   *
   * The default heuristic (longest dimension = up) is correct for
   * most single-figure STLs — a standing human is tallest in its
   * height axis. But it fails for compositions where a horizontal
   * element exceeds the figure's height: e.g. Sisyphus pushing a
   * boulder, where figure + boulder span ~2.4 along the horizontal
   * but the figure itself is only ~2.0 tall. Those meshes ship
   * pre-rotated so Y is already the vertical axis, and this flag
   * tells the pipeline to trust that rather than re-swapping.
   */
  skipAutoOrient?: boolean;
}

const MODELS: ModelSpec[] = [
  {
    file: "british-museum-discobolus1-1.stl",
    slug: "discobolus",
    targetTris: 3000,
  },
  {
    file: "msr-discobolus.stl",
    slug: "discobolus-alt",
    targetTris: 2500,
  },
  {
    file: "versailles-the-dying-gladiator-1.stl",
    slug: "dying-gladiator",
    targetTris: 3000,
  },
  {
    file: "smk-kas65-augustus-prima-porta.stl",
    slug: "augustus",
    targetTris: 3000,
  },
  {
    file: "atlas-holding-earth.stl",
    slug: "atlas",
    targetTris: 3000,
  },
  {
    file: "spartan-helmet.stl",
    slug: "spartan-helmet",
    targetTris: 3000,
  },
  {
    file: "minotaur.stl",
    slug: "minotaur",
    targetTris: 3000,
  },
  {
    // Sisyphus ships from 3MF conversion with Y already set as the
    // vertical axis. Its longest dimension is actually Z (the
    // figure-plus-boulder composition's horizontal reach), so the
    // usual "longest = up" swap would rotate him onto his side.
    file: "sisyphus.stl",
    slug: "sisyphus",
    targetTris: 3000,
    skipAutoOrient: true,
  },
];

const OUT_DIR = join(process.cwd(), "public", "sculptures");

// ─────────────────────────────────────────────────────────────────────

function resolveInputPath(filename: string): string | null {
  const candidates = [join(RAW_STL_DIR, filename), join(DOWNLOADS, filename)];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return null;
}

/** Read triangle count from a binary STL without loading triangles. */
function readTriangleCount(buf: Buffer): number {
  if (buf.length < 84) throw new Error("STL too small to be valid");
  return buf.readUInt32LE(80);
}

/**
 * Parse a binary STL into a Float32Array of vertices. If the file has
 * more than `budget` triangles we stride-subsample uniformly during the
 * parse — no allocation proportional to the source mesh size.
 */
function parseBinarySTLToArray(buf: Buffer, budget: number): MeshVerts {
  const total = readTriangleCount(buf);
  const expected = 84 + total * 50;
  if (buf.length < expected) {
    throw new Error(
      `STL claims ${total} triangles (${expected} bytes) but buffer is ` +
        `${buf.length} bytes — likely an ASCII STL, not binary.`,
    );
  }

  const stride = total > budget ? Math.ceil(total / budget) : 1;
  // Upper bound on kept triangles. We'll trim at the end.
  const maxKeep = Math.ceil(total / stride);
  const verts = new Float32Array(maxKeep * 9);

  let writeFloats = 0;
  let kept = 0;
  // Each triangle is 50 bytes: 12 normal + 36 verts + 2 attr.
  for (let i = 0; i < total; i++) {
    if (i % stride !== 0) continue;
    const base = 84 + i * 50 + 12; // skip normal
    // Read 9 float32s.
    for (let j = 0; j < 9; j++) {
      verts[writeFloats++] = buf.readFloatLE(base + j * 4);
    }
    kept++;
  }

  // Trim if we overshot budget (stride rounding).
  return verts.subarray(0, kept * 9);
}

/** Drop degenerate triangles (two vertices coincide). Operates in-place
 *  on a scratch array and returns a tightly-packed view. */
function dropDegenerates(verts: MeshVerts): MeshVerts {
  const out = new Float32Array(verts.length);
  let w = 0;
  const n = verts.length / 9;
  for (let i = 0; i < n; i++) {
    const o = i * 9;
    const ax = verts[o]!;
    const ay = verts[o + 1]!;
    const az = verts[o + 2]!;
    const bx = verts[o + 3]!;
    const by = verts[o + 4]!;
    const bz = verts[o + 5]!;
    const cx = verts[o + 6]!;
    const cy = verts[o + 7]!;
    const cz = verts[o + 8]!;
    if (
      (ax === bx && ay === by && az === bz) ||
      (bx === cx && by === cy && bz === cz) ||
      (ax === cx && ay === cy && az === cz)
    ) {
      continue;
    }
    out[w++] = ax;
    out[w++] = ay;
    out[w++] = az;
    out[w++] = bx;
    out[w++] = by;
    out[w++] = bz;
    out[w++] = cx;
    out[w++] = cy;
    out[w++] = cz;
  }
  return out.subarray(0, w);
}

interface BBox {
  min: Vec3;
  max: Vec3;
  centre: Vec3;
  size: Vec3;
  longestAxis: "x" | "y" | "z";
  longestSize: number;
}

function boundingBox(verts: MeshVerts): BBox {
  let minX = Infinity;
  let minY = Infinity;
  let minZ = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let maxZ = -Infinity;
  const n = verts.length;
  // Iterate per vertex (3 floats).
  for (let i = 0; i < n; i += 3) {
    const x = verts[i]!;
    const y = verts[i + 1]!;
    const z = verts[i + 2]!;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (z < minZ) minZ = z;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
    if (z > maxZ) maxZ = z;
  }
  const sx = maxX - minX;
  const sy = maxY - minY;
  const sz = maxZ - minZ;
  const longestSize = Math.max(sx, sy, sz);
  const longestAxis: "x" | "y" | "z" =
    longestSize === sx ? "x" : longestSize === sy ? "y" : "z";
  return {
    min: [minX, minY, minZ] as const,
    max: [maxX, maxY, maxZ] as const,
    centre: [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2] as const,
    size: [sx, sy, sz] as const,
    longestAxis,
    longestSize,
  };
}

/** In-place axis swap so longest dimension = Y (up). */
function orientYUpInPlace(verts: MeshVerts, bbox: BBox): void {
  if (bbox.longestAxis === "y") return;
  const n = verts.length;
  if (bbox.longestAxis === "z") {
    // (x, y, z) → (x, z, y). Swap components 1 and 2.
    for (let i = 0; i < n; i += 3) {
      const y = verts[i + 1]!;
      verts[i + 1] = verts[i + 2]!;
      verts[i + 2] = y;
    }
  } else {
    // (x, y, z) → (y, x, z). Swap components 0 and 1.
    for (let i = 0; i < n; i += 3) {
      const x = verts[i]!;
      verts[i] = verts[i + 1]!;
      verts[i + 1] = x;
    }
  }
}

/** In-place centre + normalize so longest dimension = 2 (i.e. [-1, 1]). */
function normalizeInPlace(verts: MeshVerts, bbox: BBox): void {
  const [cx, cy, cz] = bbox.centre;
  const s = 2 / bbox.longestSize;
  const n = verts.length;
  for (let i = 0; i < n; i += 3) {
    verts[i] = (verts[i]! - cx) * s;
    verts[i + 1] = (verts[i + 1]! - cy) * s;
    verts[i + 2] = (verts[i + 2]! - cz) * s;
  }
}

/**
 * Vertex-cluster decimation on a uniform grid. Every vertex in the same
 * cell collapses to the cell's centroid; triangles whose three vertices
 * share any pair of cells are dropped. Deterministic, O(triangles),
 * silhouette-preserving.
 *
 * Input verts must already be normalized to [-1, 1].
 */
function decimateByClustering(
  verts: MeshVerts,
  gridResolution: number,
): MeshVerts {
  const cellSize = 2 / gridResolution;
  const keyOf = (x: number, y: number, z: number): string => {
    const ix = Math.floor((x + 1) / cellSize);
    const iy = Math.floor((y + 1) / cellSize);
    const iz = Math.floor((z + 1) / cellSize);
    return `${ix}|${iy}|${iz}`;
  };

  // Accumulate centroids per cell in a single pass.
  type CellEntry = { sx: number; sy: number; sz: number; n: number };
  const cells = new Map<string, CellEntry>();
  const vertCount = verts.length / 3;
  for (let i = 0; i < vertCount; i++) {
    const o = i * 3;
    const x = verts[o]!;
    const y = verts[o + 1]!;
    const z = verts[o + 2]!;
    const k = keyOf(x, y, z);
    const e = cells.get(k);
    if (e) {
      e.sx += x;
      e.sy += y;
      e.sz += z;
      e.n++;
    } else {
      cells.set(k, { sx: x, sy: y, sz: z, n: 1 });
    }
  }

  // Centroid per cell (computed once, reused).
  const centroid = new Map<string, Vec3>();
  for (const [k, e] of cells) {
    centroid.set(k, [e.sx / e.n, e.sy / e.n, e.sz / e.n] as const);
  }

  // Walk triangles, emit centroid-based versions, skipping degenerates +
  // duplicates.
  const triCount = verts.length / 9;
  const maxOut = triCount * 9;
  const out = new Float32Array(maxOut);
  const seen = new Set<string>();
  let w = 0;
  for (let i = 0; i < triCount; i++) {
    const o = i * 9;
    const ka = keyOf(verts[o]!, verts[o + 1]!, verts[o + 2]!);
    const kb = keyOf(verts[o + 3]!, verts[o + 4]!, verts[o + 5]!);
    const kc = keyOf(verts[o + 6]!, verts[o + 7]!, verts[o + 8]!);
    if (ka === kb || kb === kc || ka === kc) continue;
    const sig = [ka, kb, kc].sort().join("#");
    if (seen.has(sig)) continue;
    seen.add(sig);
    const a = centroid.get(ka)!;
    const b = centroid.get(kb)!;
    const c = centroid.get(kc)!;
    out[w++] = a[0];
    out[w++] = a[1];
    out[w++] = a[2];
    out[w++] = b[0];
    out[w++] = b[1];
    out[w++] = b[2];
    out[w++] = c[0];
    out[w++] = c[1];
    out[w++] = c[2];
  }
  return out.subarray(0, w);
}

/** Binary-search grid resolution until we land in [0.6*target, 1.3*target]. */
function decimateToTarget(verts: MeshVerts, target: number): MeshVerts {
  let lo = 16;
  let hi = 512;
  let best: MeshVerts = verts;
  for (let iter = 0; iter < 10; iter++) {
    const mid = Math.floor((lo + hi) / 2);
    const res = decimateByClustering(verts, mid);
    const count = res.length / 9;
    if (count >= target * 0.6 && count <= target * 1.3) {
      return res;
    }
    if (count < target) {
      lo = mid + 1;
      best = res;
    } else {
      hi = mid - 1;
      best = res;
    }
    if (lo > hi) break;
  }
  return best;
}

function writeMeshFile(slug: string, verts: MeshVerts): void {
  const triCount = verts.length / 9;
  const header = Buffer.alloc(8);
  header.write("STA1", 0, "ascii");
  header.writeUInt32LE(triCount, 4);
  const body = Buffer.from(verts.buffer, verts.byteOffset, verts.byteLength);
  writeFileSync(join(OUT_DIR, `${slug}.mesh.bin`), Buffer.concat([header, body]));
}

function human(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function processOne(m: (typeof MODELS)[number]): void {
  const inPath = resolveInputPath(m.file);
  if (!inPath) {
    console.log(
      `  ⚠  skip  ${m.slug}  (not found at ${join(
        RAW_STL_DIR,
        m.file,
      )} or ${join(DOWNLOADS, m.file)})`,
    );
    return;
  }
  const inSize = statSync(inPath).size;
  console.log(
    `  ▸  ${m.slug.padEnd(16)}  ${m.file}  (${human(inSize)})`,
  );
  console.log(`      source        ${inPath}`);

  const buf = readFileSync(inPath);
  const total = readTriangleCount(buf);
  const stride = total > PARSE_BUDGET ? Math.ceil(total / PARSE_BUDGET) : 1;
  console.log(
    `      STL claims    ${total.toLocaleString()} triangles  ${
      stride > 1 ? `(subsampling 1 in ${stride} during parse)` : ""
    }`,
  );

  let verts = parseBinarySTLToArray(buf, PARSE_BUDGET);
  verts = dropDegenerates(verts);
  const parsedTris = verts.length / 9;
  console.log(`      parsed        ${parsedTris.toLocaleString()} triangles`);

  const bbox = boundingBox(verts);
  if (!m.skipAutoOrient) {
    orientYUpInPlace(verts, bbox);
  }
  const bboxY = boundingBox(verts);
  normalizeInPlace(verts, bboxY);
  const orientNote = m.skipAutoOrient
    ? "pre-oriented — auto-swap skipped"
    : `longest axis now Y`;
  console.log(
    `      normalized    bbox ${bbox.size
      .map((s) => s.toFixed(1))
      .join(" × ")}  (${orientNote})`,
  );

  const decimated = decimateToTarget(verts, m.targetTris);
  const decTris = decimated.length / 9;
  console.log(
    `      decimated     ${decTris.toLocaleString()} triangles (target ${m.targetTris})`,
  );

  writeMeshFile(m.slug, decimated);
  const outSize = statSync(join(OUT_DIR, `${m.slug}.mesh.bin`)).size;
  console.log(`      wrote         ${human(outSize)}  →  ${m.slug}.mesh.bin`);
}

function main(): void {
  if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });
  console.log(`\nSculpture processing\n────────────────────\n`);
  console.log(`  raw STL dir: ${RAW_STL_DIR}`);
  console.log(`  fallback dir: ${DOWNLOADS}\n`);
  for (const m of MODELS) processOne(m);
  console.log(`\nDone. Meshes written to ${OUT_DIR}\n`);
}

main();
