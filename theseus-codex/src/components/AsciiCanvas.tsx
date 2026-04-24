"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type CSSProperties,
} from "react";

import {
  CELL_H,
  CELL_W,
  enhanceContrast,
  getShapeTable,
  pickChar,
  type ShapeEntry,
  type ShapeVec,
} from "@/lib/ascii/shapeVectors";

/**
 * `<AsciiCanvas />` — converts a source canvas (rendered via a `render`
 * callback) into live amber ASCII art every frame, using the full 6D
 * shape-vector approach from Alex Harri's post.
 *
 * Each grid cell is sampled by six circles arranged in a staggered 2×3
 * grid (upper-left/right, middle-left/right, lower-left/right). The six
 * resulting lightness values form a shape vector for that cell, which is
 * matched against a pre-computed table of every printable ASCII
 * character's own shape vector. Nearest match wins.
 *
 * Why 6D over 2D: the two-circle version can't distinguish `p` from `q`,
 * `-` from `_`, or `/` from `\` — they have identical upper/lower mass
 * profiles. The six-circle version captures left/right, diagonal, and
 * middle-region differences, so character picks follow contour lines
 * correctly instead of falling back on overall density.
 *
 * Performance: for our typical grids (~1500–3000 cells) this does
 * ~15–30k image samples + ~300k distance comparisons per frame, all on
 * CPU. ~10ms/frame on a modest laptop. No GPU shaders, no k-d tree —
 * the scale doesn't justify them here.
 *
 * Contrast enhancement (the exponent trick from the post) is available
 * via the `contrast` prop. 1.0 = off; 1.5–2.0 gives punchy edges without
 * introducing the staircase artifact the post warns about.
 */

export type AsciiCanvasProps = {
  /** Grid dimensions. ~50×20 is a good starting point. */
  cols: number;
  rows: number;
  /** Callback to draw the source scene every frame. */
  render: (ctx: CanvasRenderingContext2D, timeMs: number) => void;
  /** Foreground (amber) colour. Defaults to `var(--amber)`. */
  color?: string;
  /** Background colour. Defaults to transparent. */
  background?: string;
  /** Global contrast enhancement exponent (1 = off). */
  contrast?: number;
  /** Pause the animation loop (saves battery). */
  paused?: boolean;
  /**
   * Scale applied to the rendered cell size. Default 1.0.
   *
   * - Values < 1 make glyphs physically smaller, which means MORE glyphs
   *   fit into a given screen area — i.e. the sculpture has *finer
   *   detail* at the same on-screen footprint. Good for large backdrop
   *   renders where you want every facial feature legible.
   * - Values > 1 make glyphs chunkier (fewer, bigger characters). Good
   *   for decorative headers where readability at distance matters more
   *   than fine detail.
   *
   * The shape-vector lookup table is built once at CELL_W×CELL_H and does
   * not depend on this scale — the vectors are density ratios, which are
   * scale-invariant. We only scale the output sampling positions + font
   * size so the rendered glyphs line up with the scaled cells.
   */
  cellScale?: number;
  /** Accessibility label for screen readers. */
  ariaLabel?: string;
  className?: string;
  style?: CSSProperties;
};

// Offset pattern for sampling each individual circle — four-sample pattern
// per circle (centre + 3 jittered) approximates integrated brightness
// cheaply without iterating every pixel inside the circle.
const CIRCLE_CENTRES_PX: readonly (readonly [number, number])[] = [
  [CELL_W * 0.28, CELL_H * 0.22], // UL
  [CELL_W * 0.72, CELL_H * 0.22], // UR
  [CELL_W * 0.28, CELL_H * 0.52], // ML
  [CELL_W * 0.72, CELL_H * 0.48], // MR
  [CELL_W * 0.28, CELL_H * 0.8],  // LL
  [CELL_W * 0.72, CELL_H * 0.8],  // LR
] as const;

const JITTER: readonly (readonly [number, number])[] = [
  [0, 0],
  [-0.8, -0.6],
  [0.8, -0.6],
  [0, 1.0],
] as const;

/**
 * Resolve a CSS color string to a concrete `rgb(…)` / `rgba(…)` value that
 * the Canvas 2D `fillStyle` setter will accept.
 *
 * WHY: Canvas `fillStyle` does NOT resolve CSS custom properties. Assigning
 * `ctx.fillStyle = "var(--amber)"` is silently rejected by the browser —
 * fillStyle retains its previous value (which on a fresh canvas is the
 * default `#000000` black). The net effect: every ASCII glyph in the whole
 * codex was being drawn in pure black over a dark page and reading as
 * invisible. This helper makes all amber-coloured components actually
 * amber.
 *
 * HOW: create an off-DOM element (via the output canvas's parent), set its
 * `color` to the requested value, append briefly, read `getComputedStyle`,
 * remove. This works for `var(--x)`, named colours, hex, hsl, rgb, and
 * anything else the browser natively understands.
 */
function resolveCssColor(value: string, anchor: Element | null): string {
  if (!value || value === "transparent") return value;
  if (typeof window === "undefined" || typeof document === "undefined") {
    return value;
  }
  // Fast path: the value is already a concrete color, no resolution needed.
  // (Avoids a DOM round-trip on every re-render for the common case where
  // the caller passed a hex/rgb/rgba/hsl string directly.)
  if (
    /^#[0-9a-f]{3,8}$/i.test(value) ||
    value.startsWith("rgb(") ||
    value.startsWith("rgba(") ||
    value.startsWith("hsl(") ||
    value.startsWith("hsla(")
  ) {
    return value;
  }
  try {
    const probe = document.createElement("span");
    probe.style.color = value;
    probe.style.display = "none";
    // Anchor inside the tree that hosts the canvas so the right scope's
    // custom properties (e.g. data-theme="dark" overrides) resolve.
    (anchor?.parentElement ?? document.body).appendChild(probe);
    const resolved = getComputedStyle(probe).color;
    probe.remove();
    return resolved || value;
  } catch {
    return value;
  }
}

/**
 * Pull the numeric R, G, B components out of a resolved color string.
 *
 * Accepts the formats `resolveCssColor` can return: `rgb(…)`, `rgba(…)`,
 * `#RRGGBB`, and 3-char `#RGB`. Returns a sensible amber fallback when
 * given anything unexpected so the depth-colour path never produces a
 * black or transparent glyph.
 */
function parseRgb(color: string): [number, number, number] {
  const rgb = color.match(
    /rgba?\(\s*(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)/i,
  );
  if (rgb) {
    return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  }
  const hex = color.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const h = hex[1]!;
    if (h.length === 3) {
      return [
        parseInt(h[0]! + h[0]!, 16),
        parseInt(h[1]! + h[1]!, 16),
        parseInt(h[2]! + h[2]!, 16),
      ];
    }
    return [
      parseInt(h.slice(0, 2), 16),
      parseInt(h.slice(2, 4), 16),
      parseInt(h.slice(4, 6), 16),
    ];
  }
  return [233, 163, 56];
}

/**
 * Build a lookup table of quantised fill-style strings for the depth-
 * colour path.
 *
 * Why a LUT instead of computing a per-cell colour: setting `fillStyle`
 * to a new string makes Canvas re-parse + re-resolve the colour each
 * time, which adds up at ~2,000 cells/frame × 60fps. Quantising depth
 * to a handful of bands keeps the assignment count to whatever the
 * number of bands is (we pick 16, well below any visible banding
 * threshold at the glyph scales we render at).
 *
 * `minBrightness` is the floor for the dimmest band. See the
 * `DEPTH_MIN_BRIGHTNESS` constant below for the rationale behind the
 * specific value — the gist is that too low a floor reads as "the
 * figure is transparent", too high a floor flattens the depth cue.
 *
 * `gamma` bends the linear depth→brightness mapping toward the bright
 * end. With `gamma < 1`, mid-depth cells land noticeably closer to
 * the max than to the min — i.e. "most of the figure reads as solid
 * amber, only the deepest recesses pull back to the floor". That
 * matches what a viewer expects from a 3D lit object: the front half
 * is fully illuminated, the back quarter is visibly shaded, the
 * middle is mostly still lit. `gamma = 1` is plain linear.
 */
function buildDepthLUT(
  rgb: readonly [number, number, number],
  bands: number,
  minBrightness: number,
  gamma: number,
): string[] {
  const lut: string[] = [];
  const span = 1 - minBrightness;
  for (let b = 0; b < bands; b++) {
    const t = bands <= 1 ? 1 : b / (bands - 1);
    const brightness = minBrightness + Math.pow(t, gamma) * span;
    const r = Math.round(rgb[0] * brightness);
    const g = Math.round(rgb[1] * brightness);
    const bl = Math.round(rgb[2] * brightness);
    lut.push(`rgb(${r}, ${g}, ${bl})`);
  }
  return lut;
}

/** Number of depth brightness bands. 16 is indistinguishable from a
 *  continuous gradient at our glyph sizes and keeps the per-frame
 *  fillStyle assignment count low. */
const DEPTH_BANDS = 16;
/**
 * Floor for the dimmest depth band, expressed as a fraction of the
 * resolved amber colour.
 *
 * History of tuning on this value:
 *
 *   0.35  — Original. Strong 2.86× near:far contrast; produced a
 *           "transparent" look because the dimmed back glyphs lost
 *           contrast against the dark page and read as absent.
 *   0.70  — Over-corrected. Solid everywhere but the depth gradient
 *           was too subtle; the figure read as flat.
 *   0.55  — Current. A 1.82× contrast ratio — dim cells are clearly
 *           duller than bright cells, but still solid amber, not
 *           ghostly. Combined with `DEPTH_GAMMA = 0.50` which pushes
 *           mid-depth cells up toward the bright end, the resulting
 *           figure has a solid lit body with visibly shadowed
 *           recesses — 3D object under directional light, rather
 *           than silhouette cutout.
 */
const DEPTH_MIN_BRIGHTNESS = 0.55;
/**
 * Exponent applied to the normalised depth before mapping onto the
 * `[minBrightness, 1]` range. Values < 1 pull mid-depth cells UP
 * toward the bright end (more of the figure reads as solid); values
 * > 1 pull them down (more of the figure reads as shadowed).
 *
 * 0.50 is the companion to `DEPTH_MIN_BRIGHTNESS = 0.55`: a 0.5-depth
 * cell lands at brightness 0.87, keeping most of the figure's surface
 * in the bright third of the range while letting the back cells dive
 * to the 0.55 floor. The sharper gamma (vs the previous 0.55) more
 * than compensates for the lowered min when it comes to "does the
 * body of the figure still look solid?" — the answer is yes, because
 * only genuinely deep-in-the-figure cells ever see the floor.
 */
const DEPTH_GAMMA = 0.5;

export default function AsciiCanvas({
  cols,
  rows,
  render,
  color = "var(--amber)",
  background = "transparent",
  contrast = 1.6,
  paused = false,
  cellScale = 1.0,
  ariaLabel,
  className,
  style,
}: AsciiCanvasProps) {
  const outputRef = useRef<HTMLCanvasElement | null>(null);
  const sourceRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const tableRef = useRef<readonly ShapeEntry[] | null>(null);
  const renderRef = useRef(render);
  renderRef.current = render;

  // Resolved colours — concrete `rgb(...)` strings usable by Canvas.
  // Updated on mount + whenever the `color` / `background` props change.
  // We fall back to a hard-coded amber so we never render a truly black
  // scene even if the probe somehow fails (e.g. detached DOM).
  const fillRef = useRef<string>("rgb(233, 163, 56)");
  const bgRef = useRef<string>("transparent");

  // Output cell size — scaled copies of the canonical CELL_W / CELL_H.
  // See the `cellScale` prop docstring for why we scale at render time
  // rather than rebuilding the shape-vector table.
  const cw = CELL_W * cellScale;
  const ch = CELL_H * cellScale;
  // Canvas pixel buffers MUST be integer-sized. If `width`/`height` are
  // fractional (which happens whenever `cellScale` is not 1.0), the
  // pixel-index math below (`idx = (sy * width + sx) * 4`) drifts
  // horizontally by `frac * sy` bytes per row against the real ImageData
  // buffer, which is always integer-sized. Over 400+ rows that's 200+
  // pixels of drift — the sampling ends up in the wrong column on every
  // row below the top, every sample comes back zero, `pickChar` returns
  // " " for every cell, and the canvas renders blank. `Math.round` so
  // output dimensions exactly match the integer canvas buffer.
  const width = Math.round(cols * cw);
  const height = Math.round(rows * ch);

  // Build the shape-vector table once on mount, after fonts load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (typeof document !== "undefined" && document.fonts?.ready) {
          await document.fonts.ready;
        }
      } catch {
        /* non-fatal */
      }
      if (!cancelled) {
        const { entries } = getShapeTable();
        tableRef.current = entries;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Resolve the CSS colour props to concrete rgb() strings whenever they
  // change. Also runs once on mount. We hook this to `outputRef.current`
  // as the DOM anchor so the resolution picks up any ancestor-scoped
  // custom-property overrides (e.g. a section with its own `--amber`).
  useEffect(() => {
    fillRef.current = resolveCssColor(color, outputRef.current);
    bgRef.current =
      background === "transparent"
        ? "transparent"
        : resolveCssColor(background, outputRef.current);
  }, [color, background]);

  // Re-resolve on theme changes. `data-theme` on <html> flips between
  // dark and light; each scope has its own `--amber` value, so without
  // this, toggling theme would leave the ASCII frozen at the previous
  // amber.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const obs = new MutationObserver(() => {
      fillRef.current = resolveCssColor(color, outputRef.current);
      bgRef.current =
        background === "transparent"
          ? "transparent"
          : resolveCssColor(background, outputRef.current);
    });
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });
    return () => obs.disconnect();
  }, [color, background]);

  const drawFrame = useCallback(
    (timeMs: number) => {
      const out = outputRef.current;
      const src = sourceRef.current;
      const table = tableRef.current;
      if (!out || !src || !table || table.length === 0) return;

      const srcCtx = src.getContext("2d", { willReadFrequently: true });
      const outCtx = out.getContext("2d");
      if (!srcCtx || !outCtx) return;

      // Draw scene into source canvas.
      srcCtx.clearRect(0, 0, width, height);
      renderRef.current(srcCtx, timeMs);
      const imageData = srcCtx.getImageData(0, 0, width, height).data;

      const dpr =
        typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
      outCtx.save();
      outCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Use the resolved colour refs, NOT the raw props. Passing
      // `var(--amber)` directly to `fillStyle` would be silently rejected
      // by the browser and leave the glyphs drawn in default-black —
      // which is exactly the bug we're fixing here.
      const resolvedBg = bgRef.current;
      if (resolvedBg !== "transparent") {
        outCtx.fillStyle = resolvedBg;
        outCtx.fillRect(0, 0, width, height);
      } else {
        outCtx.clearRect(0, 0, width, height);
      }
      outCtx.fillStyle = fillRef.current;
      // Font sized to the SCALED cell height so glyphs fit their scaled
      // slots. This is what actually makes `cellScale < 1` produce fine
      // detail — the output is a grid of many smaller characters.
      outCtx.font = `${Math.max(4, Math.floor(ch * 0.85))}px "IBM Plex Mono", monospace`;
      outCtx.textBaseline = "middle";
      outCtx.textAlign = "center";

      // ── DEPTH-COLOURED GLYPHS ────────────────────────────────────
      // Callers (e.g. SculptureAscii) can pack a per-pixel depth signal
      // into the G channel of the source canvas: R stays at 255 so the
      // shape-vector sampler reads alpha-as-brightness unchanged, G
      // encodes normalised depth (0 = far, 255 = near), B stays at 0.
      // Per cell we read the G at its centre, convert to a brightness
      // band index, and fillText with the LUT entry for that band —
      // so near surfaces render at full amber and far surfaces fade
      // into a dimmer amber. Figures gain visible depth-as-colour on
      // top of the density-based depth the picker already provides.
      //
      // When no depth signal is present (callers that still use the
      // legacy single-colour fill), G is effectively zero across the
      // image, every cell lands in the darkest band, and everything
      // would render unreadably dim. Detect that case with a
      // once-per-frame G-channel peak check and fall back to the
      // flat-colour path when the signal is missing.
      const rgb = parseRgb(fillRef.current);
      let depthLUT: string[] | null = null;
      let depthPeak = 0;
      // Sampling every 64 bytes (every 16th pixel) is plenty to detect
      // "is the G channel carrying anything?" without walking the full
      // ImageData buffer on each frame.
      for (let p = 1; p < imageData.length; p += 64) {
        const g = imageData[p]!;
        if (g > depthPeak) depthPeak = g;
      }
      const hasDepthSignal = depthPeak >= 12; // ≥ ~5 % of full scale
      if (hasDepthSignal) {
        depthLUT = buildDepthLUT(
          rgb,
          DEPTH_BANDS,
          DEPTH_MIN_BRIGHTNESS,
          DEPTH_GAMMA,
        );
      }
      let lastBand = -1;

      // Sampling loop. Hot path — allocate nothing inside.
      const vec: [number, number, number, number, number, number] = [
        0, 0, 0, 0, 0, 0,
      ];
      for (let row = 0; row < rows; row++) {
        const y0 = row * ch;
        for (let col = 0; col < cols; col++) {
          const x0 = col * cw;

          for (let c = 0; c < 6; c++) {
            // `CIRCLE_CENTRES_PX` is expressed against the canonical
            // CELL_W / CELL_H; scale to the scaled cell so the sample
            // positions land in the right fraction of the current cell.
            const cx = CIRCLE_CENTRES_PX[c][0] * cellScale;
            const cy = CIRCLE_CENTRES_PX[c][1] * cellScale;
            let acc = 0;
            for (const [ox, oy] of JITTER) {
              const sx = Math.min(
                width - 1,
                Math.max(0, Math.floor(x0 + cx + ox * cellScale)),
              );
              const sy = Math.min(
                height - 1,
                Math.max(0, Math.floor(y0 + cy + oy * cellScale)),
              );
              const idx = (sy * width + sx) * 4;
              acc += imageData[idx] / 255;
            }
            vec[c] = acc / JITTER.length;
          }

          const enhanced: ShapeVec = enhanceContrast(
            vec as ShapeVec,
            contrast,
          );
          const picked = pickChar(enhanced, table);

          if (picked !== " ") {
            if (depthLUT) {
              // Sample G at the cell centre for depth. Clamp the index
              // and only set fillStyle when it actually changes — most
              // neighbouring cells share a band, so this keeps the
              // fillStyle assignment count well below the cell count.
              const cxPx = Math.min(
                width - 1,
                Math.max(0, Math.floor(x0 + cw / 2)),
              );
              const cyPx = Math.min(
                height - 1,
                Math.max(0, Math.floor(y0 + ch / 2)),
              );
              const gByte = imageData[(cyPx * width + cxPx) * 4 + 1]!;
              let band = Math.floor((gByte / 256) * DEPTH_BANDS);
              if (band < 0) band = 0;
              else if (band > DEPTH_BANDS - 1) band = DEPTH_BANDS - 1;
              if (band !== lastBand) {
                outCtx.fillStyle = depthLUT[band]!;
                lastBand = band;
              }
            }
            outCtx.fillText(picked, x0 + cw / 2, y0 + ch / 2);
          }
        }
      }

      outCtx.restore();
    },
    // `color` and `background` are intentionally absent — their resolved
    // values are read from `fillRef` / `bgRef` at draw time. Including
    // them here would rebuild the callback every theme change (and
    // interrupt the animation frame loop needlessly).
    [contrast, cols, rows, width, height, cw, ch, cellScale],
  );

  useEffect(() => {
    if (paused) {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      drawFrame(now - start);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [drawFrame, paused]);

  const canvasStyle = useMemo<CSSProperties>(
    () => ({
      display: "block",
      width,
      height,
      userSelect: "none",
      WebkitUserSelect: "none",
    }),
    [width, height],
  );

  const dpr =
    typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;

  return (
    <div className={className} style={style} aria-label={ariaLabel}>
      <canvas
        ref={outputRef}
        width={width * dpr}
        height={height * dpr}
        style={canvasStyle}
        aria-hidden="true"
      />
      <canvas
        ref={sourceRef}
        width={width}
        height={height}
        style={{ display: "none" }}
        aria-hidden="true"
      />
    </div>
  );
}
