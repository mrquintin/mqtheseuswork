"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import CommandPalette, { type PaletteCommand } from "@/components/CommandPalette";
import PageKeymap from "@/components/PageKeymap";
import type { HotkeyBinding } from "@/lib/hotkeys";

/**
 * Founder triage queue — interactive layer.
 *
 * The server component (`page.tsx`) fetches the conviction-sorted draft
 * + needs-re-review rows and hydrates the conclusions under each
 * candidate; this client component carries the keyboard navigation the
 * triage workflow needs:
 *
 *   - `j` / `k` (or `↓` / `↑`) move the selection through the queue;
 *     `Enter` or `o` opens the selected candidate's detail page where
 *     accept-with-edit / reject-with-reason / merge-with-existing live.
 *   - `e` jumps straight to the first underlying conclusion of the
 *     selected candidate — and every conclusion is also a one-click
 *     link rendered inline on the row, so the evidence is always one
 *     click away.
 *   - `p` opens the triage command palette (the Round 17 prompt 36
 *     `CommandPalette`, fed page-scoped commands): fuzzy-jump to any
 *     candidate or its evidence without leaving the keyboard.
 *
 * The bindings are also registered with `PageKeymap` so they show up
 * in the global "?" help overlay.
 */

export type QueueConclusion = {
  id: string;
  text: string;
  confidenceTier: string;
};

export type QueueRow = {
  id: string;
  text: string;
  convictionScore: number;
  domainBreadth: number;
  status: string;
  driftReason: string | null;
  domains: string[];
  clusterConclusionIds: string[];
  citedConclusionIds: string[];
  conclusions: QueueConclusion[];
};

export default function QueueClient({ rows }: { rows: QueueRow[] }) {
  const router = useRouter();
  const [selected, setSelected] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Refs so the (stable) hotkey handlers always read current state
  // without rebuilding the bindings array — that keeps PageKeymap from
  // re-registering its scope on every keystroke.
  const selectedRef = useRef(0);
  selectedRef.current = selected;
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const rowEls = useRef<Array<HTMLLIElement | null>>([]);

  const clampedSelected = rows.length === 0 ? 0 : Math.min(selected, rows.length - 1);

  const move = useCallback((delta: number) => {
    setSelected((current) => {
      const n = rowsRef.current.length;
      if (n === 0) return 0;
      const base = Math.min(current, n - 1);
      return (base + delta + n) % n;
    });
  }, []);

  const openRow = useCallback(
    (index: number) => {
      const row = rowsRef.current[index];
      if (row) router.push(`/principles/${row.id}/triage`);
    },
    [router],
  );

  const openEvidence = useCallback(
    (index: number) => {
      const row = rowsRef.current[index];
      if (!row) return;
      const first = row.conclusions[0];
      // First underlying conclusion if it is present in this org's
      // Codex; otherwise fall back to the detail page, which renders
      // the full cluster (and flags any retracted members).
      router.push(
        first ? `/conclusions/${first.id}` : `/principles/${row.id}/triage`,
      );
    },
    [router],
  );

  // Keep the selected row in view as the founder arrows through.
  useEffect(() => {
    const el = rowEls.current[clampedSelected];
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [clampedSelected]);

  const bindings: ReadonlyArray<HotkeyBinding> = useMemo(
    () => [
      { chord: "j", description: "Next candidate", handler: () => move(1) },
      { chord: "k", description: "Previous candidate", handler: () => move(-1) },
      { chord: "arrowdown", description: "Next candidate", handler: () => move(1) },
      { chord: "arrowup", description: "Previous candidate", handler: () => move(-1) },
      {
        chord: "enter",
        description: "Open selected candidate",
        handler: () => openRow(selectedRef.current),
      },
      {
        chord: "o",
        description: "Open selected candidate",
        handler: () => openRow(selectedRef.current),
      },
      {
        chord: "e",
        description: "Open the selected candidate's evidence",
        handler: () => openEvidence(selectedRef.current),
      },
      {
        chord: "p",
        description: "Open the triage command palette",
        handler: () => setPaletteOpen((open) => !open),
      },
    ],
    [move, openRow, openEvidence],
  );

  // Memoize the PageKeymap element so it does not re-render (and so
  // does not re-register its scope on the KeymapProvider) every time
  // the founder moves the selection with j/k.
  const keymapEl = useMemo(
    () => <PageKeymap bindings={bindings} label="Principle triage queue" />,
    [bindings],
  );

  // Page-scoped commands contributed to the command palette: fuzzy-jump
  // to any candidate or straight to its underlying conclusions.
  const paletteCommands: ReadonlyArray<PaletteCommand> = useMemo(() => {
    const out: PaletteCommand[] = [];
    if (rows.length > 0) {
      out.push({
        id: "principle-queue:open-top",
        section: "Review",
        label: "Open highest-conviction candidate",
        hint: rows[0].text.slice(0, 80),
        keywords: "principle triage top next",
        run: () => router.push(`/principles/${rows[0].id}/triage`),
      });
    }
    rows.forEach((row, index) => {
      out.push({
        id: `principle-queue:open:${row.id}`,
        section: "Review",
        label: `Triage #${index + 1}: ${row.text.slice(0, 72)}`,
        hint: `conviction ${row.convictionScore.toFixed(2)} · ${row.status}`,
        keywords: `principle ${row.domains.join(" ")} ${row.status}`,
        run: () => router.push(`/principles/${row.id}/triage`),
      });
      out.push({
        id: `principle-queue:evidence:${row.id}`,
        section: "Review",
        label: `Evidence for #${index + 1}: ${row.text.slice(0, 64)}`,
        hint: `${row.clusterConclusionIds.length} underlying conclusion(s)`,
        keywords: "principle evidence conclusions cluster",
        run: () => {
          const first = row.conclusions[0];
          router.push(
            first ? `/conclusions/${first.id}` : `/principles/${row.id}/triage`,
          );
        },
      });
    });
    return out;
  }, [rows, router]);

  // R-018: a polite aria-live region — currently announces selection
  // moves so a screen-reader user hears "Selected #4: <title>" as they
  // press j/k. When a future pass adds in-row resolve, the same region
  // carries the "Resolved: <title>" announcement and rows collapse-
  // animate over 150 ms (see `.queue-row-collapsing` in globals.css).
  const announcement = useMemo(() => {
    const row = rowsRef.current[clampedSelected];
    if (!row) return "Queue is empty.";
    const idx = clampedSelected + 1;
    const head = row.text.length > 60 ? `${row.text.slice(0, 60)}…` : row.text;
    return `Selected #${idx}: ${head}`;
  }, [clampedSelected]);

  return (
    <>
      {keymapEl}
      {paletteOpen ? (
        <CommandPalette
          startOpen
          registerHotkey={false}
          extraCommands={paletteCommands}
          onClosed={() => setPaletteOpen(false)}
        />
      ) : null}

      <div
        aria-live="polite"
        data-testid="queue-aria-live"
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0 0 0 0)",
          whiteSpace: "nowrap",
          border: 0,
        }}
      >
        {announcement}
      </div>

      <p className="mono" style={hintStyle}>
        <kbd style={kbdStyle}>j</kbd>/<kbd style={kbdStyle}>k</kbd> move ·{" "}
        <kbd style={kbdStyle}>↵</kbd> open · <kbd style={kbdStyle}>e</kbd>{" "}
        evidence · <kbd style={kbdStyle}>p</kbd> command palette
      </p>

      <ul style={listStyle}>
        {rows.map((row, index) => {
          const active = index === clampedSelected;
          const cited = new Set(row.citedConclusionIds);
          return (
            <li
              key={row.id}
              ref={(el) => {
                rowEls.current[index] = el;
              }}
              className="portal-card"
              data-active={active ? "true" : undefined}
              onMouseEnter={() => setSelected(index)}
              style={{
                padding: "1.1rem 1.3rem",
                borderLeft: active
                  ? "3px solid var(--gold)"
                  : "3px solid transparent",
                background: active ? "rgba(212, 160, 23, 0.08)" : undefined,
              }}
            >
              <div style={rowHeadStyle}>
                <Link href={`/principles/${row.id}/triage`} style={titleLinkStyle}>
                  {row.text}
                </Link>
                <span
                  className="mono"
                  title="Conviction score (conservative; rewards cross-domain breadth)"
                  style={convictionStyle}
                >
                  {row.convictionScore.toFixed(2)}
                </span>
              </div>

              <div className="mono" style={metaStyle}>
                <span>cluster · {row.clusterConclusionIds.length}</span>
                <span>domains · {row.domainBreadth}</span>
                <span>status · {row.status}</span>
                {row.driftReason ? (
                  <span style={{ color: "var(--ember, #c0392b)" }}>
                    drift · {row.driftReason}
                  </span>
                ) : null}
              </div>

              {row.domains.length > 0 ? (
                <div style={domainRowStyle}>
                  {row.domains.map((d) => (
                    <span key={d} className="mono" style={domainChipStyle}>
                      {d}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="mono" style={noDomainStyle}>
                  No domain declared · cannot publish
                </p>
              )}

              {/* One-click evidence: every underlying conclusion is a
                  direct link, rendered inline on the row. */}
              <div style={evidenceWrapStyle}>
                <span className="mono" style={evidenceLabelStyle}>
                  underlying conclusions
                </span>
                <div style={evidenceListStyle}>
                  {row.conclusions.length === 0 ? (
                    <span className="mono" style={evidenceEmptyStyle}>
                      none resolvable in this Codex — see the detail page
                    </span>
                  ) : (
                    row.conclusions.map((c) => (
                      <Link
                        key={c.id}
                        href={`/conclusions/${c.id}`}
                        className="mono"
                        title={c.text}
                        style={{
                          ...evidenceLinkStyle,
                          borderColor: cited.has(c.id)
                            ? "var(--amber)"
                            : "var(--border)",
                        }}
                      >
                        {cited.has(c.id) ? "★ " : ""}
                        {c.text.length > 64
                          ? `${c.text.slice(0, 64)}…`
                          : c.text}
                      </Link>
                    ))
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

const hintStyle: CSSProperties = {
  fontSize: "0.6rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  color: "var(--parchment-dim)",
  marginBottom: "0.9rem",
  display: "flex",
  gap: "0.5rem",
  flexWrap: "wrap",
};

const kbdStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 3,
  padding: "0.05rem 0.35rem",
  fontSize: "0.6rem",
  color: "var(--amber)",
};

const listStyle: CSSProperties = {
  listStyle: "none",
  padding: 0,
  margin: 0,
  display: "flex",
  flexDirection: "column",
  gap: "0.85rem",
};

const rowHeadStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  gap: "1rem",
};

const titleLinkStyle: CSSProperties = {
  color: "var(--gold)",
  textDecoration: "none",
  fontSize: "1rem",
  fontFamily: "'EB Garamond', serif",
  flex: 1,
};

const convictionStyle: CSSProperties = {
  fontSize: "0.75rem",
  color: "var(--amber)",
  letterSpacing: "0.1em",
};

const metaStyle: CSSProperties = {
  marginTop: "0.5rem",
  fontSize: "0.65rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "var(--parchment-dim)",
  display: "flex",
  flexWrap: "wrap",
  gap: "0.75rem",
};

const domainRowStyle: CSSProperties = {
  marginTop: "0.5rem",
  display: "flex",
  flexWrap: "wrap",
  gap: "0.4rem",
};

const domainChipStyle: CSSProperties = {
  fontSize: "0.6rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  padding: "0.2rem 0.6rem",
  border: "1px solid var(--border)",
  color: "var(--parchment-dim)",
};

const noDomainStyle: CSSProperties = {
  marginTop: "0.5rem",
  fontSize: "0.6rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "var(--ember, #c0392b)",
};

const evidenceWrapStyle: CSSProperties = {
  marginTop: "0.7rem",
  paddingTop: "0.6rem",
  borderTop: "1px solid var(--border)",
};

const evidenceLabelStyle: CSSProperties = {
  fontSize: "0.55rem",
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "var(--parchment-dim)",
};

const evidenceListStyle: CSSProperties = {
  marginTop: "0.4rem",
  display: "flex",
  flexWrap: "wrap",
  gap: "0.4rem",
};

const evidenceLinkStyle: CSSProperties = {
  fontSize: "0.62rem",
  padding: "0.25rem 0.55rem",
  border: "1px solid var(--border)",
  color: "var(--parchment-dim)",
  textDecoration: "none",
};

const evidenceEmptyStyle: CSSProperties = {
  fontSize: "0.62rem",
  color: "var(--ember, #c0392b)",
};
