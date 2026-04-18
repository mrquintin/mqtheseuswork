"use client";

import { useEffect, useState, type CSSProperties } from "react";
import SculptureAscii from "./SculptureAsciiClient";

/**
 * A sculpture rendered as a huge, dim backdrop — covering roughly half
 * the page and fading toward the content edge. The idea: the statue is
 * a *presence* in the room, not a widget. At large size and low opacity
 * it reads as atmosphere; you notice it immediately but it never fights
 * the UI for attention.
 *
 * Mechanics:
 *   - Absolutely positioned inside a `position: relative` parent, so it
 *     scrolls with the page section that hosts it.
 *   - Rendered at ~90×60 glyphs with `cellScale = 0.58` so there are
 *     thousands of small characters describing the silhouette — every
 *     facial feature, muscular line, and drapery fold becomes legible
 *     instead of being averaged into a blob.
 *   - CSS mask fades the sculpture toward the content side, so text
 *     remains readable where it overlaps. Opacity handles overall
 *     dimness; amber colour stays at full saturation so contrast is
 *     controlled by the mask, not by amber-deep tinting (which can read
 *     as "burnt toast" against a dark page).
 *   - Hidden on narrow viewports (< 900px) — on small screens the page
 *     content needs the whole width, and a large statue fights the UI.
 *
 * Each page on the Codex gets a different sculpture in a different
 * orientation, so navigating feels like walking through a gallery where
 * each room has its own patron.
 */

export type SculptureBackdropProps = {
  src: string;
  /** Which edge of the page the sculpture anchors to. */
  side?: "right" | "left";
  /** Width as a fraction of viewport, capped. */
  widthVW?: number;
  /** ASCII grid dimensions. Bigger = slower but finer. */
  cols?: number;
  rows?: number;
  /** Rotation speed in revolutions-per-second. Slow by default (stately). */
  yawSpeed?: number;
  /** Tilt in radians; negative values look down onto the figure. */
  pitch?: number;
  /** Effective opacity after mask + css opacity. Default 0.45. */
  opacity?: number;
  /** Override the glyph scale. Default 0.58 = ~3.5mm glyphs at typical DPI. */
  cellScale?: number;
  /** Extra CSS for the wrapper (rarely needed). */
  style?: CSSProperties;
};

export default function SculptureBackdrop({
  src,
  side = "right",
  widthVW = 55,
  cols = 96,
  rows = 64,
  yawSpeed = 0.012,
  pitch = -0.08,
  opacity = 0.45,
  cellScale = 0.58,
  style,
}: SculptureBackdropProps) {
  // Hide on narrow screens entirely — at phone widths a half-page statue
  // just overlaps the form. Media-query via state so it works inside
  // Next.js's dynamic-imported client component tree.
  const [isNarrow, setIsNarrow] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 900px)");
    const update = () => setIsNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  if (isNarrow) return null;

  const fadeDir = side === "right" ? "to left" : "to right";

  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        [side]: 0,
        width: `min(${widthVW}vw, 780px)`,
        pointerEvents: "none",
        zIndex: 0,
        overflow: "hidden",
        opacity,
        // Fade toward the content edge — 100% solid at the outer edge,
        // transparent where content text lives. The gradient is
        // deliberately long (full height) so the bottom of the statue
        // doesn't cut off abruptly.
        maskImage: `linear-gradient(${fadeDir}, rgba(0,0,0,1) 0%, rgba(0,0,0,0.85) 35%, rgba(0,0,0,0.35) 75%, rgba(0,0,0,0) 100%)`,
        WebkitMaskImage: `linear-gradient(${fadeDir}, rgba(0,0,0,1) 0%, rgba(0,0,0,0.85) 35%, rgba(0,0,0,0.35) 75%, rgba(0,0,0,0) 100%)`,
        display: "flex",
        alignItems: "center",
        justifyContent: side === "right" ? "flex-end" : "flex-start",
        ...style,
      }}
    >
      <SculptureAscii
        src={src}
        cols={cols}
        rows={rows}
        cellScale={cellScale}
        yawSpeed={yawSpeed}
        pitch={pitch}
        scale={0.82}
        color="var(--amber)"
      />
    </div>
  );
}
