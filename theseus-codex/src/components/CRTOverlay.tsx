"use client";

import { useEffect, useRef } from "react";

/**
 * Sitewide ambient treatment.
 *
 * Replaces an earlier overlay that painted literal CRT scan-lines across
 * every page — that read as a cosmetic gimmick ("fake monitor"), not as
 * the amber-phosphor feel we actually want. The new treatment is two
 * things, much more restrained:
 *
 *   1. A soft radial vignette. Centre is fully transparent; the corners
 *      fade to ~28% black. Evokes the edge-darkening of an old monitor
 *      without drawing attention to itself. No stripes.
 *   2. A very slow, faint animated amber-noise layer. Single 256×256
 *      pre-rendered tile is wallpapered across the viewport and drifts
 *      a few pixels per second. Blended at ~4% opacity with `overlay`
 *      so it only warms the mid-tones; black stays black, amber stays
 *      amber. The effect is atmospheric — like watching the UI through
 *      heated air or through a glass of amber liquid.
 *
 * Both layers are pointer-events: none and aria-hidden. They auto-disable
 * under `prefers-reduced-motion: reduce` (the animated noise is the only
 * motion; we also drop the noise entirely at that media query because
 * some users find animated grain distracting even without actual motion).
 *
 * The earlier scan-line + vignette overlay had each effect as a fixed
 * `<div>`. We keep that shape here (two absolute-positioned divs) so the
 * component is still stateless and cheap to mount / unmount.
 */
export default function CRTOverlay() {
  const noiseRef = useRef<HTMLDivElement | null>(null);

  // Build the noise tile once at mount via an offscreen canvas. Using a
  // repeating bg-image sourced from a data URL keeps the overlay a single
  // layer that the compositor can happily GPU-accelerate.
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (!noiseRef.current) return;

    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      // Drop the noise layer entirely in reduced-motion mode — it's
      // atmospheric polish, not essential.
      noiseRef.current.style.display = "none";
      return;
    }

    const SIZE = 256;
    const off = document.createElement("canvas");
    off.width = SIZE;
    off.height = SIZE;
    const ctx = off.getContext("2d");
    if (!ctx) return;

    // Fill with warm amber noise — not pure-random gray speckle. Each
    // pixel gets a small warm offset around #000 so the resulting grain,
    // when composited with the page, reads amber-by-association rather
    // than as an explicit texture you can "see".
    const img = ctx.createImageData(SIZE, SIZE);
    for (let i = 0; i < img.data.length; i += 4) {
      const n = Math.random();
      // bias toward darkness; only a small fraction of pixels get bright.
      const brightness = n * n * n * 180; // cube → long-tailed distribution
      img.data[i] = brightness; // R
      img.data[i + 1] = brightness * 0.7; // G (warmer)
      img.data[i + 2] = brightness * 0.35; // B (warmest tail)
      img.data[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);

    const dataUrl = off.toDataURL("image/png");
    noiseRef.current.style.backgroundImage = `url(${dataUrl})`;
    noiseRef.current.style.backgroundRepeat = "repeat";
  }, []);

  return (
    <>
      {/* Vignette — slightly softer than before. Centre 60% of the screen
          is fully clear; only the outer rim fades toward black. */}
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 9998,
          background:
            "radial-gradient(ellipse at center, transparent 62%, rgba(0, 0, 0, 0.32) 100%)",
        }}
      />
      {/* Amber noise field — very faint, slow-drifting animation. Tiles a
          pre-rendered 256×256 noise canvas and slides its position over
          time via CSS keyframe `crt-noise-drift`. Kept separate from the
          vignette so it can be independently tuned or hidden. */}
      <div
        ref={noiseRef}
        aria-hidden="true"
        className="crt-noise"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 9999,
          opacity: 0.035,
          mixBlendMode: "screen",
        }}
      />
    </>
  );
}
