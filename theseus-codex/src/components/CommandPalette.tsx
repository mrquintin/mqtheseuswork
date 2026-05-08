"use client";

import {
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import { useHotkey } from "@/lib/hotkeys";

/**
 * Keyboard-only command palette. Cmd+K (Ctrl+K outside macOS) opens it
 * from anywhere in the authed shell. The palette is a single search
 * input plus a filtered list of commands — deliberately no heavy
 * combobox framework, just a controlled `<input>` and arrow-key state
 * over a static array. The whole thing is well under 10KB minified.
 *
 * Command sources:
 *   - static "navigate to page X" entries
 *   - static "execute query" entries (saved jumps the founder runs daily)
 *   - dynamic "jump to conclusion <id|slug>" — when the query is at
 *     least 6 chars and looks id-like we offer to navigate directly
 *   - dynamic attention-queue actions fetched once on open
 *
 * The palette lives above all chrome (z-index 1000) and traps focus
 * while open. Esc / outside-click / Enter on a command all close it.
 */

export interface PaletteCommand {
  id: string;
  /** Headline text shown in the result list. */
  label: string;
  /** Sub-line — usually shows the destination path or hint. */
  hint?: string;
  /** Section grouping in the dropdown. */
  section: "Navigate" | "Conclusions" | "Attention" | "Queries";
  /** Hidden keyword set used by the matcher in addition to label/hint. */
  keywords?: string;
  /** What to do when the command is invoked. */
  run: () => void | Promise<void>;
}

interface AttentionItemSlim {
  queue: string;
  itemId: string;
  link: string;
  preview: string;
  severity: "low" | "medium" | "high";
}

const NAV_TARGETS: ReadonlyArray<{ label: string; href: string; keywords?: string }> = [
  { label: "Dashboard", href: "/dashboard", keywords: "forum home" },
  { label: "Knowledge", href: "/knowledge", keywords: "library conclusions" },
  { label: "Explorer", href: "/explorer", keywords: "semantic map embeddings" },
  { label: "Ask", href: "/ask", keywords: "oracle query" },
  { label: "Currents", href: "/founder-currents", keywords: "feed x twitter" },
  { label: "Forecasts", href: "/forecasts/portfolio", keywords: "kalshi polymarket" },
  { label: "Social", href: "/social" },
  { label: "Ops", href: "/ops", keywords: "decay contradictions" },
  { label: "Upload", href: "/upload" },
  { label: "Account", href: "/account" },
];

const QUERY_PRESETS: ReadonlyArray<{ label: string; href: string; keywords?: string }> = [
  {
    label: "Recent firm conclusions",
    href: "/knowledge?tab=conclusions&tier=firm",
    keywords: "tier firm",
  },
  {
    label: "Active contradictions",
    href: "/ops?panel=contradictions",
    keywords: "ops review",
  },
  {
    label: "Drift events",
    href: "/ops?panel=decay",
    keywords: "decay rotted",
  },
  {
    label: "Pending peer reviews",
    href: "/peer-review",
    keywords: "queue swarm",
  },
];

function looksLikeId(query: string): boolean {
  const q = query.trim();
  if (q.length < 6) return false;
  // Either looks like a UUID/slug fragment (no spaces, alphanumerics +
  // dashes/underscores) OR was prefixed with `c:` to force the jump.
  if (q.startsWith("c:") || q.startsWith("/c/")) return true;
  return /^[a-z0-9_-]+$/i.test(q);
}

function score(query: string, command: PaletteCommand): number {
  if (!query) return 1;
  const q = query.toLowerCase();
  const haystack = `${command.label} ${command.hint ?? ""} ${command.keywords ?? ""}`.toLowerCase();
  if (haystack.includes(q)) {
    // Prefix match on the label gets a big boost.
    if (command.label.toLowerCase().startsWith(q)) return 10;
    return 5;
  }
  // Sub-sequence match (typing "drft" finds "drift events").
  let i = 0;
  for (const ch of haystack) {
    if (ch === q[i]) i += 1;
    if (i === q.length) return 1;
  }
  return 0;
}

const SECTION_ORDER: PaletteCommand["section"][] = [
  "Navigate",
  "Conclusions",
  "Attention",
  "Queries",
];

export interface CommandPaletteProps {
  /**
   * Optional extra commands contributed by the current page. Used so a
   * page can wire its own "advance review" or "edit conclusion" verb
   * into the palette without having to reach into this component.
   */
  extraCommands?: ReadonlyArray<PaletteCommand>;
}

export default function CommandPalette({ extraCommands = [] }: CommandPaletteProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [attention, setAttention] = useState<AttentionItemSlim[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setHighlight(0);
    if (previouslyFocused.current) {
      try {
        previouslyFocused.current.focus();
      } catch {
        // ignore
      }
    }
  }, []);

  const openPalette = useCallback(() => {
    if (typeof document !== "undefined") {
      previouslyFocused.current = document.activeElement as HTMLElement | null;
    }
    setOpen(true);
  }, []);

  // Cmd/Ctrl+K toggles the palette. allowInEditable so it works while
  // the founder is typing in any input on the page.
  useHotkey(
    "mod+k",
    () => {
      if (open) close();
      else openPalette();
    },
    { allowInEditable: true },
  );

  // Focus the search input on open and fetch the attention queue once.
  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/founder/attention", { cache: "no-store" });
        if (!res.ok || cancelled) return;
        const json = (await res.json()) as { items?: AttentionItemSlim[] };
        if (!cancelled && Array.isArray(json.items)) {
          setAttention(json.items.slice(0, 8));
        }
      } catch {
        // Palette must keep working offline; swallow.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Esc / outside click close the palette.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    }
    function onMouseDown(event: MouseEvent) {
      const dialog = dialogRef.current;
      if (!dialog) return;
      if (!dialog.contains(event.target as Node)) close();
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [open, close]);

  const navigate = useCallback(
    (href: string) => {
      router.push(href);
      close();
    },
    [router, close],
  );

  // Snooze an attention item by N days. Default 1 day; the palette is
  // intentionally not a slider — it's a one-shot "kick this down the
  // road" verb. The full snooze UI still lives on the dashboard row.
  const snoozeAttention = useCallback(
    async (item: AttentionItemSlim, days = 1) => {
      const until = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
      try {
        await fetch("/api/founder/attention", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            queue: item.queue,
            itemId: item.itemId,
            action: "snooze",
            snoozedUntil: until.toISOString(),
            reason: "snoozed via command palette",
          }),
        });
      } catch {
        // ignore — telemetry-grade error reporting belongs elsewhere
      }
      router.refresh();
      close();
    },
    [router, close],
  );

  const advanceAttention = useCallback(() => {
    const next = attention[0];
    if (!next) {
      navigate("/dashboard");
      return;
    }
    navigate(next.link);
  }, [attention, navigate]);

  const commands: PaletteCommand[] = useMemo(() => {
    const out: PaletteCommand[] = [];
    for (const target of NAV_TARGETS) {
      out.push({
        id: `nav:${target.href}`,
        section: "Navigate",
        label: `Go to ${target.label}`,
        hint: target.href,
        keywords: target.keywords,
        run: () => navigate(target.href),
      });
    }

    out.push({
      id: "attention:advance",
      section: "Attention",
      label: "Advance to next attention item",
      hint: attention[0]?.preview.slice(0, 80) ?? "Open the dashboard queue",
      keywords: "next inbox queue",
      run: advanceAttention,
    });
    for (const item of attention) {
      out.push({
        id: `attention:open:${item.queue}:${item.itemId}`,
        section: "Attention",
        label: `Open: ${item.preview.slice(0, 80)}`,
        hint: `${item.severity} · ${item.queue}`,
        keywords: item.queue,
        run: () => navigate(item.link),
      });
      out.push({
        id: `attention:snooze:${item.queue}:${item.itemId}`,
        section: "Attention",
        label: `Snooze 1 day: ${item.preview.slice(0, 60)}`,
        hint: `${item.queue}`,
        keywords: "later defer",
        run: () => snoozeAttention(item, 1),
      });
    }

    if (looksLikeId(query)) {
      const cleaned = query.trim().replace(/^c:/, "").replace(/^\/c\//, "");
      out.push({
        id: `conclusions:jump:${cleaned}`,
        section: "Conclusions",
        label: `Jump to conclusion ${cleaned}`,
        hint: `/conclusions/${cleaned}`,
        run: () => navigate(`/conclusions/${cleaned}`),
      });
    }

    for (const preset of QUERY_PRESETS) {
      out.push({
        id: `query:${preset.href}`,
        section: "Queries",
        label: preset.label,
        hint: preset.href,
        keywords: preset.keywords,
        run: () => navigate(preset.href),
      });
    }

    for (const command of extraCommands) {
      out.push(command);
    }
    return out;
  }, [attention, query, advanceAttention, navigate, snoozeAttention, extraCommands]);

  const filtered = useMemo(() => {
    const ranked = commands
      .map((command) => ({ command, weight: score(query, command) }))
      .filter((entry) => entry.weight > 0);
    ranked.sort((a, b) => {
      if (b.weight !== a.weight) return b.weight - a.weight;
      const sa = SECTION_ORDER.indexOf(a.command.section);
      const sb = SECTION_ORDER.indexOf(b.command.section);
      if (sa !== sb) return sa - sb;
      return a.command.label.localeCompare(b.command.label);
    });
    return ranked.map((entry) => entry.command).slice(0, 40);
  }, [commands, query]);

  // Keep the highlight inside the visible result count.
  useEffect(() => {
    if (highlight >= filtered.length) {
      setHighlight(filtered.length === 0 ? 0 : filtered.length - 1);
    }
  }, [highlight, filtered.length]);

  const onInputKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLInputElement>) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHighlight((h) => (filtered.length === 0 ? 0 : (h + 1) % filtered.length));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setHighlight((h) =>
          filtered.length === 0 ? 0 : (h - 1 + filtered.length) % filtered.length,
        );
      } else if (event.key === "Enter") {
        event.preventDefault();
        const target = filtered[highlight];
        if (target) void target.run();
      }
    },
    [filtered, highlight],
  );

  if (!open) return null;

  return (
    <div
      role="presentation"
      aria-hidden={false}
      style={overlayStyle}
      data-testid="command-palette-overlay"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        data-testid="command-palette"
        style={dialogStyle}
      >
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded
          aria-controls="command-palette-listbox"
          aria-autocomplete="list"
          aria-activedescendant={
            filtered[highlight] ? `palette-option-${filtered[highlight].id}` : undefined
          }
          spellCheck={false}
          autoComplete="off"
          placeholder="Type a command, page, or conclusion id…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setHighlight(0);
          }}
          onKeyDown={onInputKeyDown}
          style={inputStyle}
        />
        <ul
          id="command-palette-listbox"
          role="listbox"
          aria-label="Available commands"
          style={listStyle}
        >
          {filtered.length === 0 ? (
            <li
              style={{
                padding: "0.85rem 1rem",
                color: "var(--parchment-dim)",
                fontSize: "0.85rem",
              }}
            >
              No commands match. Try a page name (Dashboard, Explorer) or a
              conclusion id.
            </li>
          ) : (
            filtered.map((command, index) => {
              const active = index === highlight;
              return (
                <li
                  key={command.id}
                  id={`palette-option-${command.id}`}
                  role="option"
                  aria-selected={active}
                  data-section={command.section}
                  data-active={active ? "true" : undefined}
                  onMouseEnter={() => setHighlight(index)}
                  onMouseDown={(event) => {
                    // Run on mousedown so the input doesn't lose focus
                    // before we read the activeDescendant.
                    event.preventDefault();
                    void command.run();
                  }}
                  style={{
                    ...optionStyle,
                    background: active ? "rgba(212, 160, 23, 0.16)" : "transparent",
                    borderLeftColor: active ? "var(--gold)" : "transparent",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
                    <span>{command.label}</span>
                    <span
                      className="mono"
                      style={{
                        color: "var(--parchment-dim)",
                        fontSize: "0.6rem",
                        letterSpacing: "0.18em",
                        textTransform: "uppercase",
                      }}
                    >
                      {command.section}
                    </span>
                  </div>
                  {command.hint ? (
                    <div
                      className="mono"
                      style={{
                        color: "var(--parchment-dim)",
                        fontSize: "0.7rem",
                        marginTop: "0.2rem",
                      }}
                    >
                      {command.hint}
                    </div>
                  ) : null}
                </li>
              );
            })
          )}
        </ul>
        <footer style={footerStyle}>
          <span>↑↓ select · ↵ run · esc close</span>
          <span>cmd/ctrl+k to toggle</span>
        </footer>
      </div>
    </div>
  );
}

const overlayStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "center",
  paddingTop: "12vh",
  background: "rgba(0, 0, 0, 0.55)",
  backdropFilter: "blur(2px)",
};

const dialogStyle: CSSProperties = {
  width: "min(640px, 92vw)",
  background: "var(--stone, #15110b)",
  border: "1px solid var(--gold-dim, #6b5119)",
  borderRadius: 4,
  boxShadow: "0 24px 60px rgba(0,0,0,0.55)",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const inputStyle: CSSProperties = {
  appearance: "none",
  background: "transparent",
  border: "none",
  borderBottom: "1px solid var(--gold-dim, #6b5119)",
  color: "var(--parchment, #e8d9b6)",
  font: "1rem 'EB Garamond', serif",
  outline: "none",
  padding: "1rem 1.1rem",
};

const listStyle: CSSProperties = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  maxHeight: "60vh",
  overflowY: "auto",
};

const optionStyle: CSSProperties = {
  borderLeft: "3px solid transparent",
  cursor: "pointer",
  fontFamily: "'EB Garamond', serif",
  fontSize: "0.95rem",
  padding: "0.7rem 1rem",
  color: "var(--parchment, #e8d9b6)",
};

const footerStyle: CSSProperties = {
  alignItems: "center",
  borderTop: "1px solid var(--border, #2a2218)",
  color: "var(--parchment-dim, #9d8c66)",
  display: "flex",
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: "0.6rem",
  justifyContent: "space-between",
  letterSpacing: "0.12em",
  padding: "0.45rem 1rem",
  textTransform: "uppercase",
};

export const __test = { score, looksLikeId };
