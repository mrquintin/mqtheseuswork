"use client";

/**
 * Cross-link block for a method page, plus the reader-state trail.
 *
 * Methodology Explorer v2 (Round 17 prompt 07 refinement): a first-version
 * explorer ships the data; v2 makes it legible. Two concerns live here
 * because the scope only opens one new component file, and both are about
 * "how methods relate to each other and to the reader":
 *
 *  1. `MethodCrossLinks` (default) — the four one-click relationships the
 *     prompt asks for: methods this one composes, methods that depend on
 *     this one, open questions tied to the method, and principles its
 *     evidence has produced. It is rendered from props the server page
 *     already resolved, so the links are in the first paint and a reader
 *     without JavaScript can follow every one of them. The only
 *     client-side behaviour is recording the visit for the trail.
 *
 *  2. `ReaderTrail` (named export) — a subtle "you've looked at" trail
 *     backed by `localStorage`. No cookie is set on a request, no pixel
 *     is loaded; the trail is a pure progressive enhancement that renders
 *     nothing until the client has hydrated and read local state. Without
 *     JavaScript it simply never appears — it degrades, it does not fail.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

const TRAIL_KEY = "theseus:methodology:trail";
const TRAIL_CAP = 8;

type TrailEntry = { name: string; at: number };

function readTrail(): TrailEntry[] {
  try {
    const raw = window.localStorage.getItem(TRAIL_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (e): e is TrailEntry =>
        Boolean(e) &&
        typeof (e as TrailEntry).name === "string" &&
        typeof (e as TrailEntry).at === "number",
    );
  } catch {
    // localStorage unavailable, disabled, or corrupt — the trail is a
    // progressive enhancement, so a read failure just means no trail.
    return [];
  }
}

function recordVisit(method: string): void {
  try {
    const next = [
      { name: method, at: Date.now() },
      ...readTrail().filter((e) => e.name !== method),
    ].slice(0, TRAIL_CAP);
    window.localStorage.setItem(TRAIL_KEY, JSON.stringify(next));
  } catch {
    // Writing the trail is best-effort; never let it surface to the reader.
  }
}

const groupLabelStyle: React.CSSProperties = {
  fontSize: "0.6rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--public-muted, #888)",
  margin: "0 0 0.5rem",
};

const chipStyle: React.CSSProperties = {
  display: "inline-block",
  fontSize: "0.72rem",
  padding: "0.25rem 0.55rem",
  border: "1px solid var(--public-rule, #ddd)",
  borderRadius: 2,
  textDecoration: "none",
  color: "inherit",
};

function CrossLinkGroup({
  label,
  empty,
  children,
}: {
  label: string;
  empty: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className="public-card"
      style={{ padding: "0.85rem 1rem", minWidth: 0 }}
    >
      <h3 className="mono" style={groupLabelStyle}>
        {label}
      </h3>
      {empty ? (
        <p
          className="public-muted"
          style={{ margin: 0, fontSize: "0.82rem", fontStyle: "italic" }}
        >
          None recorded.
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexWrap: "wrap",
            gap: "0.4rem",
          }}
        >
          {children}
        </ul>
      )}
    </div>
  );
}

export type MethodCrossLinksProps = {
  /** The method whose page this block sits on. */
  method: string;
  /** Methods this one is built from — this method composes them. */
  composes: string[];
  /** Methods that build on this one. */
  dependedOnBy: string[];
  /** Open questions for which this method is a recorded candidate. */
  openQuestions: { id: string; summary: string }[];
  /** Principles whose evidence cluster includes this method's conclusions. */
  principles: { id: string; text: string }[];
};

/**
 * The four cross-link groups. Server-rendered from props, so every link
 * is reachable in one click with JavaScript disabled; the only client
 * behaviour is recording the visit into the reader trail.
 */
export default function MethodCrossLinks({
  method,
  composes,
  dependedOnBy,
  openQuestions,
  principles,
}: MethodCrossLinksProps) {
  useEffect(() => {
    recordVisit(method);
  }, [method]);

  return (
    <section
      className="public-section"
      aria-labelledby="method-cross-links-title"
    >
      <h2 id="method-cross-links-title">How this method connects</h2>
      <p className="public-muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
        One click to the methods around this one, the questions it is a
        candidate to answer, and the principles its evidence has produced.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "0.75rem",
        }}
      >
        <CrossLinkGroup label="Composes" empty={composes.length === 0}>
          {composes.map((name) => (
            <li key={name}>
              <Link
                href={`/methodology/${encodeURIComponent(name)}`}
                className="mono"
                style={chipStyle}
              >
                {name}
              </Link>
            </li>
          ))}
        </CrossLinkGroup>

        <CrossLinkGroup
          label="Depended on by"
          empty={dependedOnBy.length === 0}
        >
          {dependedOnBy.map((name) => (
            <li key={name}>
              <Link
                href={`/methodology/${encodeURIComponent(name)}`}
                className="mono"
                style={chipStyle}
              >
                {name}
              </Link>
            </li>
          ))}
        </CrossLinkGroup>

        <CrossLinkGroup
          label="Open questions"
          empty={openQuestions.length === 0}
        >
          {openQuestions.map((q) => (
            <li key={q.id} style={{ width: "100%" }}>
              <Link
                href="/methodology/open-questions"
                style={{
                  ...chipStyle,
                  display: "block",
                  fontSize: "0.82rem",
                  lineHeight: 1.4,
                }}
              >
                {q.summary}
              </Link>
            </li>
          ))}
        </CrossLinkGroup>

        <CrossLinkGroup
          label="Principles produced"
          empty={principles.length === 0}
        >
          {principles.map((p) => (
            <li key={p.id} style={{ width: "100%" }}>
              <Link
                href="/methodology/principles"
                style={{
                  ...chipStyle,
                  display: "block",
                  fontSize: "0.82rem",
                  lineHeight: 1.4,
                }}
              >
                {p.text}
              </Link>
            </li>
          ))}
        </CrossLinkGroup>
      </div>
    </section>
  );
}

/**
 * "You've looked at" trail. Renders nothing on the server and on the
 * first client render (state starts empty), so there is no hydration
 * mismatch and a no-JavaScript reader simply never sees it. After mount
 * it reads `localStorage` and shows the methods the reader has visited,
 * most-recent first, excluding the page they are currently on.
 */
export function ReaderTrail({ current }: { current?: string }) {
  const [names, setNames] = useState<string[]>([]);

  useEffect(() => {
    setNames(
      readTrail()
        .map((e) => e.name)
        .filter((n) => n && n !== current),
    );
  }, [current]);

  if (names.length === 0) return null;

  return (
    <nav
      aria-label="Methods you have looked at"
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "baseline",
        gap: "0.5rem",
        margin: "0.75rem 0 0",
        fontSize: "0.72rem",
      }}
    >
      <span
        className="mono public-muted"
        style={{
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          fontSize: "0.6rem",
        }}
      >
        You&apos;ve looked at
      </span>
      {names.map((name) => (
        <Link
          key={name}
          href={`/methodology/${encodeURIComponent(name)}`}
          className="mono"
          style={{
            padding: "0.15rem 0.45rem",
            border: "1px solid var(--public-rule, #ddd)",
            borderRadius: 2,
            textDecoration: "none",
            color: "var(--public-muted, #888)",
          }}
        >
          {name}
        </Link>
      ))}
    </nav>
  );
}
