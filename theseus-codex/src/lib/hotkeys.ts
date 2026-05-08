"use client";

import { useEffect, useRef } from "react";

/**
 * Tiny in-house hotkey hook. We deliberately did NOT pull in a third-
 * party library — the requirements are small (single-key + modifier
 * chord matching, ignore-while-typing, optional scoping) and the
 * authed shell is already heavy enough.
 *
 * Chord syntax (case-insensitive, components separated by `+`):
 *   "k"           — bare key
 *   "?"           — punctuation
 *   "mod+k"       — Cmd on macOS, Ctrl elsewhere
 *   "shift+/"     — explicit modifier
 *   "ctrl+k"      — Ctrl always
 *   "meta+k"      — Cmd/Win key always
 *
 * The hook fires on `keydown` at the window level. When the focused
 * element is editable (input/textarea/contenteditable) the handler is
 * skipped unless `allowInEditable` is set — so j/k inside a textarea
 * does not trigger navigation.
 */

export interface HotkeyOptions {
  /**
   * If true the hotkey fires even when an editable element is focused.
   * Used for the command palette (Cmd+K must work everywhere).
   */
  allowInEditable?: boolean;
  /**
   * If false the hotkey is registered but disabled. Useful for gated
   * commands ("publish" only fires for users who can publish).
   */
  enabled?: boolean;
  /**
   * If true, the handler calls preventDefault on the event before
   * running. Defaults to true.
   */
  preventDefault?: boolean;
}

export type HotkeyHandler = (event: KeyboardEvent) => void;

export interface HotkeyBinding {
  chord: string;
  description: string;
  handler: HotkeyHandler;
  options?: HotkeyOptions;
}

interface ParsedChord {
  key: string;
  meta: boolean;
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  /** Chord uses the cross-platform "mod" alias. */
  mod: boolean;
}

function parseChord(raw: string): ParsedChord {
  const parts = raw.toLowerCase().split("+").map((p) => p.trim()).filter(Boolean);
  let meta = false;
  let ctrl = false;
  let shift = false;
  let alt = false;
  let mod = false;
  let key = "";
  for (const part of parts) {
    if (part === "meta" || part === "cmd" || part === "command") meta = true;
    else if (part === "ctrl" || part === "control") ctrl = true;
    else if (part === "shift") shift = true;
    else if (part === "alt" || part === "option" || part === "opt") alt = true;
    else if (part === "mod") mod = true;
    else key = part;
  }
  return { key, meta, ctrl, shift, alt, mod };
}

function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return /mac|iphone|ipad|ipod/i.test(navigator.platform || navigator.userAgent || "");
}

function eventMatches(event: KeyboardEvent, chord: ParsedChord): boolean {
  const eventKey = event.key.toLowerCase();
  if (eventKey !== chord.key) return false;

  // Coerce missing flags to false — the DOM always provides booleans
  // but tests sometimes hand in synthetic events without every prop.
  const meta = !!event.metaKey;
  const ctrl = !!event.ctrlKey;
  const shift = !!event.shiftKey;
  const alt = !!event.altKey;

  if (chord.mod) {
    // mod = Cmd on Mac, Ctrl elsewhere. We accept either when comparing.
    const wantsMeta = isMac();
    if (wantsMeta && !meta) return false;
    if (!wantsMeta && !ctrl) return false;
  } else {
    if (chord.meta !== meta) return false;
    if (chord.ctrl !== ctrl) return false;
  }
  // For the ? / shifted-key case, if the user spells "shift+/" we
  // require shiftKey; if they spelled "?" we don't, since the browser
  // already gives us "?" with shift implicit.
  if (chord.shift && !shift) return false;
  if (chord.alt !== alt) return false;
  return true;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target) return false;
  // We duck-type on tagName / isContentEditable instead of checking
  // `instanceof Element` — Element doesn't exist in node test envs,
  // and the duck check is just as accurate against a real DOM.
  const candidate = target as { tagName?: string; isContentEditable?: boolean };
  const tag = candidate.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (candidate.isContentEditable) return true;
  return false;
}

/**
 * Register a single hotkey. The handler reference is held in a ref so
 * callers don't need to memoize it — re-renders won't churn the
 * `keydown` listener.
 */
export function useHotkey(
  chord: string,
  handler: HotkeyHandler,
  options: HotkeyOptions = {},
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const { allowInEditable = false, enabled = true, preventDefault = true } = options;

  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined") return;
    const parsed = parseChord(chord);
    function onKeyDown(event: KeyboardEvent) {
      if (!eventMatches(event, parsed)) return;
      if (!allowInEditable && isEditableTarget(event.target)) return;
      if (preventDefault) event.preventDefault();
      handlerRef.current(event);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [chord, enabled, allowInEditable, preventDefault]);
}

/**
 * Register many hotkeys at once. Each binding is independent — disabled
 * bindings are skipped without disturbing the rest.
 */
export function useHotkeys(bindings: ReadonlyArray<HotkeyBinding>): void {
  const ref = useRef(bindings);
  ref.current = bindings;

  useEffect(() => {
    if (typeof window === "undefined") return;
    function onKeyDown(event: KeyboardEvent) {
      for (const binding of ref.current) {
        const opts = binding.options ?? {};
        if (opts.enabled === false) continue;
        const parsed = parseChord(binding.chord);
        if (!eventMatches(event, parsed)) continue;
        if (!opts.allowInEditable && isEditableTarget(event.target)) continue;
        if (opts.preventDefault !== false) event.preventDefault();
        binding.handler(event);
        return;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}

/** Pretty-print a chord for the help overlay. */
export function formatChord(chord: string): string {
  const parsed = parseChord(chord);
  const mac = isMac();
  const parts: string[] = [];
  if (parsed.mod) parts.push(mac ? "⌘" : "Ctrl");
  if (parsed.meta) parts.push(mac ? "⌘" : "Win");
  if (parsed.ctrl) parts.push("Ctrl");
  if (parsed.alt) parts.push(mac ? "⌥" : "Alt");
  if (parsed.shift) parts.push(mac ? "⇧" : "Shift");
  parts.push(parsed.key.length === 1 ? parsed.key.toUpperCase() : parsed.key);
  return parts.join(mac ? "" : "+");
}

/**
 * Pure helpers exported for tests so we can verify chord parsing and
 * matching without touching the DOM.
 */
export const __test = { parseChord, eventMatches, isEditableTarget };
