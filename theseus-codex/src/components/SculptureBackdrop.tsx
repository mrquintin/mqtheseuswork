"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
// Import SculptureAscii directly — not via the *Client.tsx dynamic wrapper.
// Nested `dynamic({ ssr: false })` calls (SculptureBackdropClient →
// SculptureBackdrop → SculptureAsciiClient → SculptureAscii) emit a
// `BAILOUT_TO_CLIENT_SIDE_RENDERING` at two levels in Next 14+, which in
// our deployment was leaving the sculpture permanently stuck on the
// "Summoning marble…" fallback (never hydrating the real canvas). The
// wrapper layer wasn't buying us anything — every browser-API touch
// point in SculptureAscii is already inside `useEffect`, so it's
// SSR-safe when imported directly from a "use client" component.
import SculptureAscii from "./SculptureAscii";
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

// Reasonable default grid so SculptureAscii mounts immediately on
// first render, long before ResizeObserver reports real dimensions.
// These numbers correspond to a ~700×550 px container at
// cellScale=0.65 (CELL_W=6, CELL_H=12) — close to what a typical
// 1440×900 desktop produces for a half-page backdrop, so the very
// first paint already looks right; RO just refines it if the real
// container is bigger or smaller.
const DEFAULT_DIMS = { cols: 90, rows: 60 } as const;

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
  // Derived cols / rows from the measured container size. We START
  // with the safe default above so SculptureAscii renders on FIRST
  // mount — previously we gated rendering on `dims !== null`, which
  // meant a sculpture with a container that briefly measured 0×0
  // (absolute-positioned inside a just-laying-out parent) would
  // never mount its inner canvas at all. The measurement loop below
  // still runs; it just REFINES dims instead of being the gate.
  const [dims, setDims] = useState<{ cols: number; rows: number }>(
    DEFAULT_DIMS,
  );

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

    const MIN_COLS = 40;
    const MIN_ROWS = 30;

    const computeDims = () => {
      const rect = el.getBoundingClientRect();
      const cellWpx = CELL_W * cellScale;
      const cellHpx = CELL_H * cellScale;
      // Always set SOME dims — previously we early-returned on tiny
      // measurements, which meant on pages where the absolute
      // container briefly had width:0/height:0 during initial
      // paint, `dims` stayed null and the canvas never mounted.
      // Clamp the derived size to a sane minimum instead, so even
      // a mis-laid-out parent still produces a visible sculpture.
      const cols =
        rect.width > 0
          ? Math.max(MIN_COLS, Math.floor(rect.width / cellWpx))
          : DEFAULT_DIMS.cols;
      const rows =
        rect.height > 0
          ? Math.max(MIN_ROWS, Math.floor(rect.height / cellHpx))
          : DEFAULT_DIMS.rows;
      setDims((prev) => {
        // Skip no-op state updates to avoid resetting the canvas +
        // shape-table on jitter.
        if (
          Math.abs(prev.cols - cols) < 3 &&
          Math.abs(prev.rows - rows) < 3
        ) {
          return prev;
        }
        return { cols, rows };
      });
    };

    computeDims();
    const ro = new ResizeObserver(computeDims);
    ro.observe(el);
    // Belt-and-suspenders: on some browsers/layouts RO doesn't fire
    // again after the initial observe if nothing resizes. Run a few
    // RAF-driven re-measures during the first ~250ms of the mount
    // lifecycle to catch the real size once the parent's layout
    // settles. Harmless if RO already reported correct dims —
    // setDims() dedupes.
    let rafId: number | null = null;
    const rafDeadline = performance.now() + 250;
    const tick = () => {
      computeDims();
      if (performance.now() < rafDeadline) {
        rafId = requestAnimationFrame(tick);
      }
    };
    rafId = requestAnimationFrame(tick);

    return () => {
      ro.disconnect();
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
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
      {/*
        SculptureAscii renders UNCONDITIONALLY — dims has a safe
        default (DEFAULT_DIMS) from mount 0, and the observer only
        refines it. Previously this was `dims ? … : null`, which
        left backdrops permanently empty on any page where the
        initial measurement came back 0×0 before CSS layout settled
        (the root cause of the "sculptures don't render" reports).
      */}
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
    </div>
  );
}
