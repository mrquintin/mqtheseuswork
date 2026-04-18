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
  const renderRef = useRef(render);
  renderRef.current = render;

  const width = cols * CELL_W;
  const height = rows * CELL_H;

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
      if (background !== "transparent") {
        outCtx.fillStyle = background;
        outCtx.fillRect(0, 0, width, height);
      } else {
        outCtx.clearRect(0, 0, width, height);
      }
      outCtx.fillStyle = color;
      outCtx.font = `${Math.floor(CELL_H * 0.85)}px "IBM Plex Mono", monospace`;
      outCtx.textBaseline = "middle";
      outCtx.textAlign = "center";

      // Sampling loop. Hot path — allocate nothing inside.
      const vec: [number, number, number, number, number, number] = [
        0, 0, 0, 0, 0, 0,
      ];
      for (let row = 0; row < rows; row++) {
        const y0 = row * CELL_H;
        for (let col = 0; col < cols; col++) {
          const x0 = col * CELL_W;

          for (let c = 0; c < 6; c++) {
            const [cx, cy] = CIRCLE_CENTRES_PX[c];
            let acc = 0;
            for (const [ox, oy] of JITTER) {
              const sx = Math.min(
                width - 1,
                Math.max(0, Math.floor(x0 + cx + ox)),
              );
              const sy = Math.min(
                height - 1,
                Math.max(0, Math.floor(y0 + cy + oy)),
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
          const ch = pickChar(enhanced, table);

          if (ch !== " ") {
            outCtx.fillText(ch, x0 + CELL_W / 2, y0 + CELL_H / 2);
          }
        }
      }

      outCtx.restore();
    },
    [background, color, contrast, cols, rows, width, height],
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
