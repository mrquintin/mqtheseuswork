"use client";

import { useEffect, useState } from "react";

/**
 * The arrival half of the entrance animation.
 *
 * Context
 * -------
 * When a user submits the login form on the Gate, three overlapping
 * animations run for ~1.3s (see `.gate-ignite` / `.gate-shockwave` /
 * `.gate-rays-burst` in globals.css) while the client still holds the
 * Gate page — at the peak of the shockwave Next.js navigates to
 * /dashboard. This component is what picks up on the other side: it
 * detects that we just arrived via the gate (via a sessionStorage flag
 * the Gate sets), plays the fade-in / materialise / Latin-glimmer tail
 * of the animation, and then clears the flag so subsequent page loads
 * (reload, back-nav, etc.) don't replay it.
 *
 * Visual contract
 * ---------------
 * - Adds `.codex-arrival` to the main authed-page wrapper via a wrapper
 *   div (duration 0.85s, fade + scale up + de-blur).
 * - Renders a brief Latin greeting at the top of the viewport:
 *     VENIT DOMINUS HORTORUM — *the lord of the gardens has come* —
 *   animated via `.codex-welcome-tag` (2.4s, fades in, holds, fades out).
 * - Respects `prefers-reduced-motion: reduce` by skipping everything.
 *
 * Why this lives in a client wrapper around the authed layout's children
 * ---------------------------------------------------------------------
 * The flag (`codex:just-entered` in sessionStorage) is only readable
 * client-side. We render the wrapper on every authed page mount but the
 * wrapper is cheap (a div + a short-lived tag) when the flag is absent.
 */
export default function EntranceWelcome({
  children,
}: {
  children: React.ReactNode;
}) {
  const [justEntered, setJustEntered] = useState(false);
  const [showTag, setShowTag] = useState(false);

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
    setShowTag(true);

    // Remove the arrival class after the animation so subsequent state
    // updates don't inherit the fade/scale transforms.
    const t1 = window.setTimeout(() => setJustEntered(false), 900);
    // Unmount the Latin tag once its animation has had time to run.
    const t2 = window.setTimeout(() => setShowTag(false), 2500);

    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, []);

  return (
    <div className={justEntered ? "codex-arrival" : undefined}>
      {showTag ? (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            top: "5.5rem",
            left: 0,
            right: 0,
            textAlign: "center",
            pointerEvents: "none",
            zIndex: 100,
          }}
        >
          <div
            className="codex-welcome-tag mono"
            style={{
              display: "inline-block",
              fontSize: "0.68rem",
              letterSpacing: "0.3em",
              textTransform: "uppercase",
              color: "var(--amber)",
              textShadow: "0 0 18px var(--amber), 0 0 4px var(--amber)",
              padding: "0.4rem 1.1rem",
              border: "1px solid var(--amber-deep)",
              background:
                "linear-gradient(180deg, rgba(20,14,6,0.7) 0%, rgba(20,14,6,0.4) 100%)",
              backdropFilter: "blur(2px)",
              WebkitBackdropFilter: "blur(2px)",
            }}
          >
            ✦ Introibo · You have crossed the threshold ✦
          </div>
        </div>
      ) : null}
      {children}
    </div>
  );
}
