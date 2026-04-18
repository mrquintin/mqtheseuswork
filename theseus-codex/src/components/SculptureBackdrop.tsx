"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import SculptureAscii from "./SculptureAsciiClient";
import { CELL_H, CELL_W } from "@/lib/ascii/shapeVectors";

/**
 * A sculpture rendered as a huge, dim backdrop — covering roughly half
 * the page and fading toward the content edge.
 *
 * Sizing (the non-obvious part)
 * -----------------------------
 * An earlier version of this component passed fixed `cols={96}` +
 * `rows={64}` with `cellScale={0.58}`. That produces an ASCII canvas
 * whose *physical* pixel size is `cols × CELL_W × cellScale ≈ 334 px`
 * — but the container CSS is `min(55vw, 780px) ≈ 770 px`. So the canvas
 * ended up a small chunk of ASCII floating inside a large empty box:
 * statue visible on paper, effectively invisible on screen.
 *
 * This version MEASURES its own container with a `ResizeObserver` and
 * picks `cols` / `rows` so `cols × CELL_W × cellScale` matches the
 * container width (same for height). The canvas therefore fills its box,
 * and `cellScale` then controls *detail density* the way you'd expect:
 *   - smaller `cellScale` → more, smaller glyphs → finer silhouette
 *   - larger `cellScale`  → fewer, chunkier glyphs → blockier silhouette
 *
 * Opacity + legibility
 * --------------------
 * We render in full amber at 0.65 opacity plus a linear-gradient mask
 * that fades toward the content side of the viewport. Previous attempts
 * used `--amber-deep` at higher opacity — that read as "burnt toast"
 * against the dark page because the deep amber is a brown, not a dim
 * amber. Using full amber + CSS opacity keeps the colour honest.
 *
 * Hidden on narrow viewports. Breakpoint 768 px so it shows on anything
 * bigger than a phone / half-width split screen.
 */

export type SculptureBackdropProps = {
  src: string;
  /** Which edge of the page the sculpture anchors to. */
  side?: "right" | "left";
  /** Width as a fraction of viewport, capped by `maxWidthPx`. */
  widthVW?: number;
  /** Cap the width so on huge monitors the statue doesn't dominate. */
  maxWidthPx?: number;
  /** Rotation speed in revolutions-per-second. */
  yawSpeed?: number;
  /** Tilt in radians; negative values look down onto the figure. */
  pitch?: number;
  /** 0..1 — post-mask opacity. Default 0.65. */
  opacity?: number;
  /** Glyph density. 0.5–0.8 is the sweet spot for detail; 1.0 = chunky. Default 0.7. */
  cellScale?: number;
  /** Extra CSS for the wrapper. */
  style?: CSSProperties;
};

export default function SculptureBackdrop({
  src,
  side = "right",
  widthVW = 55,
  maxWidthPx = 820,
  yawSpeed = 0.012,
  pitch = -0.08,
  // 0.72 amber + mask + CRT vignette stacks gives a final rendered
  // intensity of roughly 40–50% at the silhouette's bright edges —
  // visibly present without competing with UI text. Earlier version was
  // 0.45, which combined with the CRT vignette dragged the sculpture
  // down to ~25% — close to invisible against the stone-black page.
  opacity = 0.72,
  // 0.65 feels like the sweet spot for legible detail: roughly 1.1 MB of
  // potential sample work per frame on a typical 1400×800 backdrop,
  // which the shape picker handles at 60fps on modest hardware.
  cellScale = 0.65,
  style,
}: SculptureBackdropProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isNarrow, setIsNarrow] = useState(false);
  // Derived cols / rows from the measured container size.
  const [dims, setDims] = useState<{ cols: number; rows: number } | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 768px)");
    const update = () => setIsNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  // Measure the container on mount + on any resize, and derive cols/rows
  // so the rendered canvas fills it. ResizeObserver re-fires on layout
  // changes (viewport resize, font loading, etc.), which keeps the
  // sculpture locked to the container even when the page reflows.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const el = containerRef.current;
    if (!el) return;

    const computeDims = () => {
      const rect = el.getBoundingClientRect();
      // Guard against zero/tiny measurements (first paint before CSS
      // applies): we'd divide by near-zero and pass absurd grid sizes
      // to SculptureAscii.
      if (rect.width < 200 || rect.height < 200) return;
      const cellWpx = CELL_W * cellScale;
      const cellHpx = CELL_H * cellScale;
      const cols = Math.max(40, Math.floor(rect.width / cellWpx));
      const rows = Math.max(30, Math.floor(rect.height / cellHpx));
      setDims((prev) => {
        // Avoid pointless state updates when the rect jitters by a few pixels
        // (which retriggers the canvas + shape-table re-init).
        if (prev && Math.abs(prev.cols - cols) < 3 && Math.abs(prev.rows - rows) < 3) {
          return prev;
        }
        return { cols, rows };
      });
    };

    computeDims();
    const ro = new ResizeObserver(computeDims);
    ro.observe(el);
    return () => ro.disconnect();
  }, [cellScale]);

  if (isNarrow) return null;

  const fadeDir = side === "right" ? "to left" : "to right";

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      data-sculpture-backdrop="true"
      data-sculpture-src={src}
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        [side]: 0,
        width: `min(${widthVW}vw, ${maxWidthPx}px)`,
        pointerEvents: "none",
        zIndex: 0,
        overflow: "hidden",
        opacity,
        maskImage: `linear-gradient(${fadeDir}, rgba(0,0,0,1) 0%, rgba(0,0,0,0.88) 45%, rgba(0,0,0,0.35) 80%, rgba(0,0,0,0) 100%)`,
        WebkitMaskImage: `linear-gradient(${fadeDir}, rgba(0,0,0,1) 0%, rgba(0,0,0,0.88) 45%, rgba(0,0,0,0.35) 80%, rgba(0,0,0,0) 100%)`,
        display: "flex",
        alignItems: "center",
        justifyContent: side === "right" ? "flex-end" : "flex-start",
        ...style,
      }}
    >
      {dims ? (
        <SculptureAscii
          src={src}
          cols={dims.cols}
          rows={dims.rows}
          cellScale={cellScale}
          yawSpeed={yawSpeed}
          pitch={pitch}
          scale={0.9}
          color="var(--amber)"
        />
      ) : null}
    </div>
  );
}
