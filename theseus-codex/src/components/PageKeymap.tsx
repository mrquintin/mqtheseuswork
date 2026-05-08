"use client";

import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { type HotkeyBinding, useHotkeys } from "@/lib/hotkeys";

/**
 * Page-scoped keymap registration.
 *
 * The authed layout wraps its tree in `KeymapProvider`. A page mounts a
 * `<PageKeymap bindings={…} label="Conclusion" />` to register its own
 * scoped hotkeys. The provider holds the most-recent registration; the
 * help overlay (`KeymapHelp`) reads it so the "?" view always shows
 * the active page's bindings, not a global superset.
 *
 * Only one page-level scope is active at a time — when a page mounts,
 * it replaces whatever scope the previous page had registered, and on
 * unmount it clears the slot. This matches user expectation: the
 * keymap follows the route.
 */

interface KeymapState {
  bindings: ReadonlyArray<HotkeyBinding>;
  label: string;
}

interface KeymapContextValue {
  state: KeymapState | null;
  setState: (next: KeymapState | null) => void;
}

const KeymapContext = createContext<KeymapContextValue | null>(null);

export function KeymapProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<KeymapState | null>(null);
  const value = useMemo(() => ({ state, setState }), [state]);
  return <KeymapContext.Provider value={value}>{children}</KeymapContext.Provider>;
}

export function useActivePageKeymap(): KeymapState | null {
  const ctx = useContext(KeymapContext);
  return ctx?.state ?? null;
}

function useRegisterKeymap(state: KeymapState) {
  const ctx = useContext(KeymapContext);
  const set = ctx?.setState;
  const setStateRef = useCallback(
    (next: KeymapState | null) => {
      if (set) set(next);
    },
    [set],
  );
  useEffect(() => {
    setStateRef(state);
    return () => setStateRef(null);
  }, [setStateRef, state]);
}

export interface PageKeymapProps {
  bindings: ReadonlyArray<HotkeyBinding>;
  /** Friendly label shown in the help overlay header. */
  label: string;
}

/**
 * Mount this near the top of any client page that wants scoped
 * hotkeys. Bindings should be a stable array (define outside render or
 * memoize) so the underlying listener doesn't churn.
 */
export default function PageKeymap({ bindings, label }: PageKeymapProps) {
  useHotkeys(bindings);
  useRegisterKeymap({ bindings, label });
  return null;
}
