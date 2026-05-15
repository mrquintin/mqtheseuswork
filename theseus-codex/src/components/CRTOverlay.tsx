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
 * The earlier version also generated a full-viewport animated noise
 * texture on mount and composited it with `mix-blend-mode: screen`.
 * That looked atmospheric, but it forced a persistent compositor layer
 * over every page and made button clicks feel heavier on laptop GPUs.
 * This component is now server-rendered, static, and JS-free.
 */
export default function CRTOverlay() {
  return (
    <div
      aria-hidden="true"
      className="crt-vignette"
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 9998,
        background:
          "radial-gradient(ellipse at center, transparent 68%, rgba(0, 0, 0, 0.24) 100%)",
      }}
    />
  );
}
