"use client";

import { useEffect, useState } from "react";

/**
 * Amber ↔︎ parchment theme toggle.
 *
 * Button reads the current `data-theme` off `<html>` on mount (set by
 * the bootstrap script in layout.tsx before first paint), flips between
 * "dark" and "light" on click, and persists the choice to
 * `localStorage["theme"]`. Subsequent page loads read the stored value
 * first, then the OS-level `prefers-color-scheme` as a fallback.
 *
 * Visually: a small square button with a sun glyph (shown when the
 * current theme is DARK — click to switch to light) or a crescent-
 * moon glyph (shown when the current theme is LIGHT — click to switch
 * to dark). SVG-based so the toggle icon picks up the current theme
 * palette automatically via `currentColor`.
 *
 * Ancillary: listens to `storage` events so if the user has the site
 * open in two tabs and toggles one, the other updates too.
 */

type Theme = "dark" | "light";

function readInitialTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  const attr = document.documentElement.getAttribute("data-theme");
  return attr === "light" ? "light" : "dark";
}

export default function ThemeToggle({
  size = 32,
  className,
  title,
}: {
  size?: number;
  className?: string;
  title?: string;
}) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTheme(readInitialTheme());
    setMounted(true);

    // Cross-tab sync: respond to other tabs flipping the theme.
    const onStorage = (e: StorageEvent) => {
      if (e.key !== "theme") return;
      if (e.newValue === "light" || e.newValue === "dark") {
        applyTheme(e.newValue);
        setTheme(e.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const applyTheme = (t: Theme) => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-theme", t);
    try {
      localStorage.setItem("theme", t);
    } catch {
      /* storage may be disabled (incognito, CSP) — fall through. */
    }
  };

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  };

  // Render a neutral placeholder on the server / pre-hydration so
  // the toggle doesn't flash the "wrong" icon on first paint.
  const displayTheme = mounted ? theme : "dark";

  const label =
    displayTheme === "dark"
      ? "Switch to light mode"
      : "Switch to dark mode";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={title ?? label}
      className={className}
      style={{
        width: size,
        height: size,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 0,
        background: "transparent",
        color: "var(--amber)",
        border: "1px solid var(--amber-dim)",
        borderRadius: 4,
        cursor: "pointer",
        transition: "background 0.15s ease, color 0.15s ease",
      }}
    >
      {displayTheme === "dark" ? <SunGlyph /> : <MoonGlyph />}
    </button>
  );
}

/**
 * 16×16 sun glyph — shown while dark mode is active, inviting a flip
 * to light. Minimal stroke lines so it reads at 12–18px, no fill so
 * the button's border color shows through the gaps.
 */
function SunGlyph() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2" />
      <path d="M12 20v2" />
      <path d="m4.93 4.93 1.41 1.41" />
      <path d="m17.66 17.66 1.41 1.41" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <path d="m4.93 19.07 1.41-1.41" />
      <path d="m17.66 6.34 1.41-1.41" />
    </svg>
  );
}

/**
 * 16×16 crescent-moon glyph — shown while light mode is active.
 */
function MoonGlyph() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}
