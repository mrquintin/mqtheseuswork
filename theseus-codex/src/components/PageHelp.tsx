import type { ReactNode } from "react";

/**
 * Always-visible on-page explanation banner. Every Codex page renders one of
 * these at the top so a first-time visitor knows what they're looking at
 * and how to use it.
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
        margin: "0 auto 1.5rem",
        maxWidth: "1200px",
        padding: isSubtle ? "0.75rem 1.25rem" : "1.1rem 1.5rem",
        background: isSubtle ? "transparent" : "var(--stone-light)",
        borderLeft: `3px solid var(--amber${isSubtle ? "-dim" : ""})`,
        borderRadius: 2,
        display: "flex",
        gap: "1rem",
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
              fontSize: isSubtle ? "1rem" : "1.35rem",
              letterSpacing: "0.1em",
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
                fontSize: "0.65rem",
                letterSpacing: "0.1em",
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
            fontSize: isSubtle ? "0.95rem" : "1.05rem",
            lineHeight: 1.55,
            color: "var(--parchment)",
            margin: "0.4rem 0 0",
          }}
        >
          {purpose}
        </p>
        {howTo ? (
          <p
            style={{
              fontFamily: "'EB Garamond', Georgia, serif",
              fontSize: "0.9rem",
              lineHeight: 1.55,
              color: "var(--parchment-dim)",
              margin: "0.3rem 0 0",
            }}
          >
            {howTo}
          </p>
        ) : null}
      </div>
    </header>
  );
}
