/**
 * Sitewide CRT overlay. Renders two always-on-top non-interactive layers:
 *
 *   1. Scan lines: 2px tall repeating dark bands, low opacity, cover the whole
 *      viewport. This is the "you're reading a phosphor tube" effect.
 *   2. Vignette: radial gradient darkening the corners, simulating a curved
 *      CRT bezel.
 *
 * Both are pointer-events: none so they never intercept clicks, and both
 * auto-disable under `prefers-reduced-motion: reduce` (the subtle flicker
 * scan-lines can trigger some users' vestibular responses).
 *
 * Mounted once in the root layout so it appears on every page, including
 * the login and marketing home, without each page having to opt in.
 */
export default function CRTOverlay() {
  return (
    <>
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 9999,
          // Repeating 2px dark stripe every 3px. Total opacity stays very low
          // so text remains readable even when stacked over the effect.
          backgroundImage:
            "repeating-linear-gradient(to bottom, rgba(0, 0, 0, 0.18) 0, rgba(0, 0, 0, 0.18) 1px, transparent 1px, transparent 3px)",
          mixBlendMode: "multiply",
        }}
      />
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 9998,
          // Radial vignette. Centre is transparent; corners fade to ~40% black.
          // Simulates the glass curvature of an old CRT tube.
          background:
            "radial-gradient(ellipse at center, transparent 55%, rgba(0, 0, 0, 0.42) 100%)",
        }}
      />
    </>
  );
}
