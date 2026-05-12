import type { ReactNode } from "react";

/**
 * Always-visible on-page explanation banner. Every Codex page renders one of
 * these at the top so a first-time visitor knows what they're looking at
 * and how to use it.
 *
 * Round 20 tones the default variant down: smaller heading, less letter
 * spacing, normal (non-italic) body, and a single left rule for grouping
 * rather than a filled card. The "subtle" variant stays a near-flat
 * label-only banner.
 *
 * Optional `sigil` slot: a decorative ornament rendered next to the page
 * title. In practice this receives an `<AsciiSigil />` from the AutoPageHelp
 * client wrapper, but it's typed as a plain ReactNode here so PageHelp
 * itself stays a dumb, server-safe component (no `next/dynamic`, no
 * client-only dependencies).
 */
export default function PageHelp({
  title,
  purpose,
  howTo,
  learnMoreHref,
  sigil,
  variant = "default",
}: {
  title: string;
  purpose: string;
  howTo?: string;
  learnMoreHref?: string;
  sigil?: ReactNode;
  variant?: "default" | "subtle";
}) {
  const isSubtle = variant === "subtle";
  return (
    <header
      aria-label={`About this page: ${title}`}
      style={{
        margin: "0 auto 1.25rem",
        maxWidth: "1200px",
        padding: isSubtle ? "0.6rem 1rem" : "0.85rem 1.1rem",
        background: isSubtle ? "transparent" : "var(--stone-light)",
        borderLeft: `2px solid var(--amber${isSubtle ? "-dim" : ""})`,
        borderRadius: 2,
        display: "flex",
        gap: "0.85rem",
        alignItems: "flex-start",
      }}
    >
      {sigil ? (
        <div
          style={{
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            paddingTop: "0.1rem",
          }}
          aria-hidden="true"
        >
          {sigil}
        </div>
      ) : null}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: "0.75rem",
            flexWrap: "wrap",
          }}
        >
          <h1
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: isSubtle ? "0.95rem" : "1.15rem",
              fontWeight: 500,
              letterSpacing: "0.05em",
              color: "var(--amber)",
              margin: 0,
            }}
          >
            {title}
          </h1>
          {learnMoreHref ? (
            <a
              href={learnMoreHref}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                fontFamily: "'Inter', sans-serif",
                fontSize: "0.62rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--parchment-dim)",
                textDecoration: "none",
                borderBottom: "1px dotted var(--parchment-dim)",
              }}
            >
              User guide →
            </a>
          ) : null}
        </div>
        <p
          style={{
            fontFamily: "'EB Garamond', Georgia, serif",
            fontSize: isSubtle ? "0.9rem" : "0.98rem",
            fontStyle: "normal",
            lineHeight: 1.5,
            color: "var(--parchment)",
            margin: "0.3rem 0 0",
            maxWidth: "64ch",
          }}
        >
          {purpose}
        </p>
        {howTo ? (
          <p
            style={{
              fontFamily: "'EB Garamond', Georgia, serif",
              fontSize: "0.86rem",
              fontStyle: "normal",
              lineHeight: 1.5,
              color: "var(--parchment-dim)",
              margin: "0.25rem 0 0",
              maxWidth: "64ch",
            }}
          >
            {howTo}
          </p>
        ) : null}
      </div>
    </header>
  );
}
