"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useHotkey } from "@/lib/hotkeys";

const CommandPalette = dynamic(() => import("./CommandPalette"), {
  ssr: false,
});
const KeymapHelp = dynamic(() => import("./KeymapHelp"), {
  ssr: false,
});

/**
 * Mounts the command palette + the "?" help overlay + the global
 * "g <letter>" jump map. The chord-style "g d" navigation is handled
 * here (not in lib/hotkeys) because it's a tiny state machine — when
 * the founder presses `g`, we listen for the next key for ~1.2s and
 * route accordingly.
 */
const GLOBAL_JUMPS: Record<string, string> = {
  d: "/dashboard",
  k: "/knowledge",
  e: "/explorer",
  a: "/codex-ask",
  c: "/founder-currents",
  f: "/forecasts/portfolio",
  o: "/ops",
  s: "/social",
};

export default function KeyboardChrome() {
  const router = useRouter();
  const goPrefixActiveAt = useRef<number | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  useHotkey(
    "mod+k",
    () => setPaletteOpen((value) => !value),
    { allowInEditable: true },
  );

  useHotkey("?", () => setHelpOpen((value) => !value));
  useHotkey("shift+/", () => setHelpOpen((value) => !value));

  // When `g` is pressed (outside an editable element), open a 1.2s
  // window during which the next letter resolves into a navigation.
  useHotkey("g", () => {
    goPrefixActiveAt.current = Date.now();
  });

  const handleSecondLetter = useCallback(
    (letter: string) => {
      const at = goPrefixActiveAt.current;
      if (at === null) return false;
      if (Date.now() - at > 1200) {
        goPrefixActiveAt.current = null;
        return false;
      }
      const dest = GLOBAL_JUMPS[letter];
      if (!dest) return false;
      goPrefixActiveAt.current = null;
      router.push(dest);
      return true;
    },
    [router],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as Element | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (target instanceof HTMLElement && target.isContentEditable) return;
      const key = event.key.toLowerCase();
      if (key === "g") return; // handled by useHotkey above
      if (handleSecondLetter(key)) {
        event.preventDefault();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleSecondLetter]);

  return (
    <>
      {paletteOpen ? (
        <CommandPalette
          startOpen
          registerHotkey={false}
          onClosed={() => setPaletteOpen(false)}
        />
      ) : null}
      {helpOpen ? (
        <KeymapHelp
          startOpen
          registerHotkey={false}
          onClosed={() => setHelpOpen(false)}
        />
      ) : null}
    </>
  );
}
