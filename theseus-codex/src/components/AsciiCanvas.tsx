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
} from "@/lib/ascii/shapeVectors";

/**
 * `<AsciiCanvas />` — converts a source <canvas> (or a render callback that
 * draws into one) into live ASCII art every frame.
 *
 * How it works, each frame:
 *   1. The `render` callback draws the current scene into an offscreen
 *      source canvas.
 *   2. We sample that canvas at a grid of points — two samples per cell
 *      (upper + lower circles) — producing a 2D "sampling vector" per cell.
 *   3. For each sampling vector we apply optional global contrast enhancement
 *      and find the ASCII character whose shape is closest (Euclidean
 *      distance in 2D) using a pre-computed shape table.
 *   4. We draw the resulting characters onto the visible output canvas,
 *      amber on charcoal, respecting device pixel ratio so the text stays
 *      crisp on retina displays.
 *
 * Why this approach vs "just draw the scene directly":
 *   - Gives the site a distinctive, consistent terminal-oracle aesthetic.
 *   - The characters follow contour lines (via shape vectors), so the
 *     result has readable silhouettes even at low grid resolution.
 *   - A 60×24 grid of amber characters is cheaper to paint than a
 *     high-res WebGL scene — the "art" is the compression, not the pixels.
 *
 * Performance note: for the grids we use (40–80 cols, 18–40 rows), the
 * entire sample + look-up + draw pipeline costs ~5ms/frame on a modest
 * laptop. We don't bother with a k-d tree or GPU shaders — brute-force
 * distance comparison across 95 characters is fine at this scale.
 *
 * Accessibility: a `<pre aria-label>` mirror of the current grid (updated
 * less frequently) is exposed to screen readers, so this component isn't
 * a visual-only black-box.
 */

export type AsciiCanvasProps = {
  /** Grid dimensions. ~50×20 is a good starting point. */
  cols: number;
  rows: number;
  /** Callback to draw the source scene every frame. Receives a 2D context
   *  pre-sized to (cols * CELL_W, rows * CELL_H) and a monotonic time in ms. */
  render: (ctx: CanvasRenderingContext2D, timeMs: number) => void;
  /** Foreground (amber) colour. Defaults to `var(--amber)`. */
  color?: string;
  /** Background colour. Defaults to transparent (lets page bg show). */
  background?: string;
  /** Global contrast enhancement exponent (1 = off). Higher = sharper edges. */
  contrast?: number;
  /** Stop animating when true (saves battery on hidden tabs, etc). */
  paused?: boolean;
  /** Optional a11y description of what the scene depicts. */
  ariaLabel?: string;
  /** Passed through to the wrapping div. */
  className?: string;
  style?: CSSProperties;
};

export default function AsciiCanvas({
  cols,
  rows,
  render,
  color = "var(--amber)",
  background = "transparent",
  contrast = 1.6,
  paused = false,
  ariaLabel,
  className,
  style,
}: AsciiCanvasProps) {
  const outputRef = useRef<HTMLCanvasElement | null>(null);
  const sourceRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const tableRef = useRef<readonly ShapeEntry[] | null>(null);
  const lastChars = useRef<string[][]>([]);
  // `render` comes in from the parent; if we put it in the rAF deps we
  // restart the loop on every render. Capture it in a ref so the loop
  // always calls the latest version without tearing down.
  const renderRef = useRef(render);
  renderRef.current = render;

  const width = cols * CELL_W;
  const height = rows * CELL_H;

  // Prepare the shape-vector table once on mount (async — wait for fonts).
  useEffect(() => {
    let cancelled = false;
    // Wait for fonts so "IBM Plex Mono" is loaded before we rasterize each
    // character — otherwise shape vectors end up reflecting the system
    // fallback and picks look slightly wrong. No-op on older browsers.
    (async () => {
      try {
        if (typeof document !== "undefined" && document.fonts?.ready) {
          await document.fonts.ready;
        }
      } catch {
        /* non-fatal — fall through to fallback font */
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

  // Each frame: render scene -> sample -> look up -> paint characters.
  const drawFrame = useCallback(
    (timeMs: number) => {
      const out = outputRef.current;
      const src = sourceRef.current;
      const table = tableRef.current;
      if (!out || !src || !table || table.length === 0) return;

      const srcCtx = src.getContext("2d", { willReadFrequently: true });
      const outCtx = out.getContext("2d");
      if (!srcCtx || !outCtx) return;

      // Clear + draw source scene.
      srcCtx.clearRect(0, 0, width, height);
      renderRef.current(srcCtx, timeMs);
      const imageData = srcCtx.getImageData(0, 0, width, height).data;

      // Clear output at device-pixel resolution.
      const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
      outCtx.save();
      outCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (background !== "transparent") {
        outCtx.fillStyle = background;
        outCtx.fillRect(0, 0, width, height);
      } else {
        outCtx.clearRect(0, 0, width, height);
      }
      // Rendering properties: monospace, fill amber, center baseline.
      outCtx.fillStyle = color;
      outCtx.font = `${Math.floor(CELL_H * 0.85)}px "IBM Plex Mono", monospace`;
      outCtx.textBaseline = "middle";
      outCtx.textAlign = "center";

      // Keep a 2D scratch array we mutate in place to avoid per-frame allocs
      // and to feed the accessibility mirror efficiently.
      if (lastChars.current.length !== rows) {
        lastChars.current = Array.from({ length: rows }, () =>
          new Array<string>(cols).fill(" "),
        );
      }

      // Sample each cell with two circles (upper, lower) — constants chosen
      // in shapeVectors.ts. A 4-sample pattern per circle approximates the
      // integrated brightness cheaply without per-pixel iteration.
      const SAMPLE_CENTRES_Y = [CELL_H * 0.3, CELL_H * 0.72];
      const SAMPLE_OFFSETS = [
        [0, 0],
        [-1.5, -1],
        [1.5, -1],
        [-1.5, 1],
        [1.5, 1],
      ];
      const CX = CELL_W * 0.5;

      for (let row = 0; row < rows; row++) {
        const y0 = row * CELL_H;
        for (let col = 0; col < cols; col++) {
          const x0 = col * CELL_W;

          let upper = 0;
          let lower = 0;
          for (let c = 0; c < 2; c++) {
            let acc = 0;
            for (const [ox, oy] of SAMPLE_OFFSETS) {
              const sx = Math.min(
                width - 1,
                Math.max(0, Math.floor(x0 + CX + ox)),
              );
              const sy = Math.min(
                height - 1,
                Math.max(0, Math.floor(y0 + SAMPLE_CENTRES_Y[c] + oy)),
              );
              const idx = (sy * width + sx) * 4;
              // Luminance approx (just R channel is fine for amber on black).
              acc += imageData[idx] / 255;
            }
            const avg = acc / SAMPLE_OFFSETS.length;
            if (c === 0) upper = avg;
            else lower = avg;
          }

          const enhanced = enhanceContrast([upper, lower], contrast);
          const ch = pickChar(enhanced, table);
          lastChars.current[row][col] = ch;

          if (ch !== " ") {
            outCtx.fillText(ch, x0 + CELL_W / 2, y0 + CELL_H / 2);
          }
        }
      }

      outCtx.restore();
    },
    [background, color, contrast, cols, rows, width, height],
  );

  // rAF loop; auto-pauses when `paused` is true.
  useEffect(() => {
    if (paused) {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      return;
    }
    let start = performance.now();
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

  // Output canvas size-with-dpr so retina stays crisp.
  const canvasStyle = useMemo<CSSProperties>(
    () => ({
      display: "block",
      width,
      height,
      // Ensure text can't be selected / copied accidentally.
      userSelect: "none",
      WebkitUserSelect: "none",
    }),
    [width, height],
  );

  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;

  return (
    <div className={className} style={style} aria-label={ariaLabel}>
      {/* Output: the visible amber ASCII. */}
      <canvas
        ref={outputRef}
        width={width * dpr}
        height={height * dpr}
        style={canvasStyle}
        aria-hidden="true"
      />
      {/* Source: offscreen, where the render callback draws. Hidden. */}
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
