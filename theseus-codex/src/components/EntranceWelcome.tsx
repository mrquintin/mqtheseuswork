"use client";

import { useEffect, useState } from "react";

/**
 * The arrival half of the entrance animation (minimalist rewrite).
 *
 * Context
 * -------
 * When the user submits the login form, the Gate component plays a
 * short exit (~720 ms): form + wordmark + labyrinth fade out while a
 * thin amber hairline sweeps across the viewport's horizon. Navigation
 * happens mid-sweep. This component picks up on the other side.
 *
 * Visual contract
 * ---------------
 * - Reads the `codex:just-entered` sessionStorage flag set by the Gate.
 * - If present, mirrors the hairline on arrival: a thin amber line at
 *   the vertical midline materialises briefly, fades, and the page
 *   content fades up from a small `translateY` below (via the
 *   `.codex-arrival` class).
 * - No Latin banner, no blur, no brightness jump, no scale — quiet and
 *   precise. Total duration ~650 ms.
 * - Respects `prefers-reduced-motion: reduce` (no-op).
 *
 * Prior revision
 * --------------
 * An earlier version rendered a floating Latin welcome tag
 * ("Introibo · You have crossed the threshold") at the top of the
 * viewport and ran a `blur(2px) brightness(1.6)` scale-up on the page
 * content. The content stutter from the blur-to-sharp transition was
 * visually noisy and competed with the dashboard's own fade-in. Both
 * are removed in favour of a single `translateY + opacity` ease.
 */
export default function EntranceWelcome({
  children,
}: {
  children: React.ReactNode;
}) {
  const [justEntered, setJustEntered] = useState(false);
  const [showHairline, setShowHairline] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let entered = false;
    try {
      entered = window.sessionStorage.getItem("codex:just-entered") === "1";
      if (entered) {
        window.sessionStorage.removeItem("codex:just-entered");
      }
    } catch {
      // Storage can be disabled (privacy mode). Fall through without
      // animating — the page still works.
      return;
    }
    if (!entered) return;

    const reduced =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reduced) return;

    setJustEntered(true);
    setShowHairline(true);

    // Remove the arrival class after the animation so subsequent state
    // updates don't inherit the fade/translate transforms.
    const t1 = window.setTimeout(() => setJustEntered(false), 700);
    // Unmount the hairline once its animation has had time to run.
    const t2 = window.setTimeout(() => setShowHairline(false), 750);

    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, []);

  return (
    <div className={justEntered ? "codex-arrival" : undefined}>
      {showHairline ? (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            inset: 0,
            display: "grid",
            placeItems: "center",
            pointerEvents: "none",
            zIndex: 100,
          }}
        >
          <div className="codex-arrival-hairline" />
        </div>
      ) : null}
      {children}
    </div>
  );
}
