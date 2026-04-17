"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

/**
 * `<NavTransition />` — plays a brief amber "fly-through" flash between
 * route changes, giving top-nav clicks a theatrical, architectural feel
 * without requiring actual portal-to-portal 3D transitions.
 *
 * How it works: we watch `usePathname()` across renders; whenever the
 * path changes, we flip `phase` through `flash` then `settle` over
 * ~550ms. The visual is a translucent amber pane that comes in fast,
 * peaks, and fades out — plus a subtle zoom applied to the page body via
 * a sibling CSS rule.
 *
 * This only fires AFTER navigation (because Next.js App Router uses
 * RSC streaming, the path changes when the new page's server payload
 * arrives). Users perceive: click a nav link → fraction-of-a-second
 * amber pulse → new page appears. The effect is small, cheap, and
 * reads as "moving through architecture" rather than a simple page
 * load.
 *
 * Respects prefers-reduced-motion: goes straight to the settle phase
 * without the flash.
 */
export default function NavTransition() {
  const pathname = usePathname();
  const lastPathRef = useRef<string>(pathname);
  const [phase, setPhase] = useState<"idle" | "flash" | "settle">("idle");
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (pathname === lastPathRef.current) return;
    lastPathRef.current = pathname;

    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduced) {
      setPhase("settle");
      if (timerRef.current != null) clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setPhase("idle"), 140);
      return;
    }

    setPhase("flash");
    if (timerRef.current != null) clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      setPhase("settle");
      timerRef.current = window.setTimeout(
        () => setPhase("idle"),
        380,
      );
    }, 160);
    return () => {
      if (timerRef.current != null) clearTimeout(timerRef.current);
    };
  }, [pathname]);

  // Two stacked divs: an amber flash pane (opacity-driven) and a
  // near-imperceptible outward glow that holds a beat longer.
  const flashOpacity =
    phase === "flash" ? 0.55 : phase === "settle" ? 0.22 : 0;

  return (
    <>
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 8500,
          background:
            "radial-gradient(ellipse at center, var(--amber) 0%, rgba(233, 163, 56, 0.25) 45%, transparent 75%)",
          opacity: flashOpacity,
          transition:
            phase === "flash"
              ? "opacity 160ms ease-out"
              : "opacity 380ms ease-in",
          mixBlendMode: "screen",
        }}
      />
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 8499,
          backgroundColor: "var(--stone)",
          opacity:
            phase === "flash" ? 0.15 : phase === "settle" ? 0.05 : 0,
          transition: "opacity 280ms ease",
        }}
      />
    </>
  );
}
