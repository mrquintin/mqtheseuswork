"use client";

import {
  type CSSProperties,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { type HotkeyBinding, formatChord, useHotkey } from "@/lib/hotkeys";
import { useActivePageKeymap } from "./PageKeymap";

/**
 * "?" overlay that lists the keymap currently active. The host page
 * passes its scoped bindings in via the `pageBindings` prop; the
 * overlay merges them with the global shell bindings (Cmd+K, ?) so the
 * founder always sees the full set in one place.
 *
 * On first visit (per-browser) the component nudges with a small
 * "press ? for shortcuts" hint that the founder can dismiss. The
 * dismissal is persisted in localStorage so the hint never returns
 * for that browser.
 */

const HINT_STORAGE_KEY = "theseus.keymap.hint.dismissed.v1";

const GLOBAL_BINDINGS: ReadonlyArray<{ chord: string; description: string }> = [
  { chord: "mod+k", description: "Open command palette" },
  { chord: "?", description: "Show this shortcut overlay" },
  { chord: "g d", description: "Jump to Dashboard (g then d)" },
  { chord: "g k", description: "Jump to Knowledge" },
  { chord: "g e", description: "Jump to Explorer" },
];

export interface KeymapHelpProps {
  /** Page-scoped bindings. */
  pageBindings?: ReadonlyArray<HotkeyBinding>;
  /** Friendly label for the page section ("Conclusion", "Explorer"). */
  pageLabel?: string;
}

export default function KeymapHelp({
  pageBindings: pageBindingsProp,
  pageLabel: pageLabelProp,
}: KeymapHelpProps) {
  const active = useActivePageKeymap();
  const pageBindings = pageBindingsProp ?? active?.bindings ?? [];
  const pageLabel = pageLabelProp ?? active?.label;
  const [open, setOpen] = useState(false);
  const [hintDismissed, setHintDismissed] = useState(true);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Read the localStorage flag on mount. Wrapped so SSR doesn't blow up.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const dismissed = window.localStorage.getItem(HINT_STORAGE_KEY) === "1";
      setHintDismissed(dismissed);
    } catch {
      setHintDismissed(true);
    }
  }, []);

  const dismissHint = useCallback(() => {
    setHintDismissed(true);
    try {
      window.localStorage.setItem(HINT_STORAGE_KEY, "1");
    } catch {
      // ignore
    }
  }, []);

  const close = useCallback(() => setOpen(false), []);

  const toggle = useCallback(() => {
    setOpen((value) => !value);
    dismissHint();
  }, [dismissHint]);

  // The "?" key on most US layouts requires shift. We register both
  // forms so callers don't have to think about it.
  useHotkey("?", toggle);
  useHotkey("shift+/", toggle);

  // Esc closes the overlay.
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    }
    function onMouseDown(event: MouseEvent) {
      const node = dialogRef.current;
      if (!node) return;
      if (!node.contains(event.target as Node)) close();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [open, close]);

  return (
    <>
      {!hintDismissed && !open ? (
        <div role="status" aria-live="polite" style={hintStyle}>
          <span>
            Press <kbd style={kbdStyle}>?</kbd> for shortcuts
          </span>
          <button
            type="button"
            onClick={dismissHint}
            aria-label="Dismiss shortcut hint"
            style={hintDismissStyle}
          >
            ×
          </button>
        </div>
      ) : null}

      {open ? (
        <div role="presentation" style={overlayStyle} data-testid="keymap-help-overlay">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            style={dialogStyle}
          >
            <header style={headerStyle}>
              <h2 style={titleStyle}>Keyboard shortcuts</h2>
              <button
                type="button"
                onClick={close}
                aria-label="Close shortcuts overlay"
                style={closeStyle}
              >
                esc
              </button>
            </header>

            <Section title="Global">
              {GLOBAL_BINDINGS.map((binding) => (
                <Row
                  key={binding.chord}
                  chord={binding.chord}
                  description={binding.description}
                />
              ))}
            </Section>

            {pageBindings.length > 0 ? (
              <Section title={pageLabel ? `Page · ${pageLabel}` : "Page"}>
                {pageBindings.map((binding) => (
                  <Row
                    key={binding.chord}
                    chord={binding.chord}
                    description={binding.description}
                  />
                ))}
              </Section>
            ) : null}

            <footer style={footerStyle}>
              Hotkeys are scoped per page; the same letter can mean different
              things on Conclusion, Explorer, and Dashboard. j/k inside a
              textarea always types — never navigates.
            </footer>
          </div>
        </div>
      ) : null}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ padding: "0.75rem 1.25rem 0" }}>
      <h3 style={sectionTitleStyle}>{title}</h3>
      <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.4rem 1rem", margin: 0 }}>
        {children}
      </dl>
    </section>
  );
}

function Row({ chord, description }: { chord: string; description: string }) {
  return (
    <>
      <dt style={{ display: "flex", justifyContent: "flex-end" }}>
        <kbd style={kbdStyle}>{formatChord(chord)}</kbd>
      </dt>
      <dd style={{ margin: 0, color: "var(--parchment, #e8d9b6)", fontSize: "0.9rem" }}>
        {description}
      </dd>
    </>
  );
}

const overlayStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 999,
  background: "rgba(0,0,0,0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "1rem",
};

const dialogStyle: CSSProperties = {
  background: "var(--stone, #15110b)",
  border: "1px solid var(--gold-dim, #6b5119)",
  borderRadius: 4,
  boxShadow: "0 20px 50px rgba(0,0,0,0.55)",
  width: "min(560px, 92vw)",
  maxHeight: "80vh",
  overflow: "auto",
  paddingBottom: "1rem",
};

const headerStyle: CSSProperties = {
  alignItems: "center",
  display: "flex",
  justifyContent: "space-between",
  padding: "0.85rem 1.25rem",
  borderBottom: "1px solid var(--border, #2a2218)",
};

const titleStyle: CSSProperties = {
  color: "var(--amber, #d49d2a)",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.95rem",
  letterSpacing: "0.18em",
  margin: 0,
  textTransform: "uppercase",
};

const closeStyle: CSSProperties = {
  background: "transparent",
  border: "1px solid var(--gold-dim, #6b5119)",
  color: "var(--parchment-dim, #9d8c66)",
  cursor: "pointer",
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: "0.7rem",
  letterSpacing: "0.12em",
  padding: "0.25rem 0.55rem",
  textTransform: "uppercase",
};

const sectionTitleStyle: CSSProperties = {
  color: "var(--gold, #c8941d)",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.65rem",
  letterSpacing: "0.22em",
  margin: "0 0 0.45rem",
  textTransform: "uppercase",
};

const kbdStyle: CSSProperties = {
  background: "rgba(212,160,23,0.08)",
  border: "1px solid var(--gold-dim, #6b5119)",
  borderRadius: 3,
  color: "var(--gold, #c8941d)",
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: "0.72rem",
  letterSpacing: "0.06em",
  minWidth: "2.4rem",
  padding: "0.15rem 0.4rem",
  textAlign: "center" as const,
};

const footerStyle: CSSProperties = {
  color: "var(--parchment-dim, #9d8c66)",
  fontSize: "0.78rem",
  margin: "0.85rem 1.25rem 0",
};

const hintStyle: CSSProperties = {
  alignItems: "center",
  background: "rgba(20,16,10,0.95)",
  border: "1px solid var(--gold-dim, #6b5119)",
  borderRadius: 3,
  bottom: "1rem",
  color: "var(--parchment, #e8d9b6)",
  display: "inline-flex",
  fontSize: "0.78rem",
  gap: "0.5rem",
  padding: "0.45rem 0.7rem",
  position: "fixed",
  right: "1rem",
  zIndex: 200,
};

const hintDismissStyle: CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--parchment-dim, #9d8c66)",
  cursor: "pointer",
  fontSize: "1rem",
  lineHeight: 1,
  padding: "0 0.2rem",
};
