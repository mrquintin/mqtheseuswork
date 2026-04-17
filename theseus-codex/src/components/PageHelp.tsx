/**
 * Always-visible on-page explanation banner. Every Codex page uses one of
 * these at the top so a first-time visitor can tell what they're looking at
 * and what actions the page supports.
 *
 * Copy convention:
 *   title   — the page name (e.g. "Conclusions", "Publication queue")
 *   purpose — ONE sentence answering "what does this page show?"
 *   howTo   — ONE sentence answering "when would I come here?" OR the
 *             primary action I can take here. Optional but strongly encouraged.
 *   learnMoreHref — optional anchor into the user guide PDF / relevant doc.
 *
 * Keep copy short and plain-language. Experienced users scan past these; new
 * users rely on them as the first thing they read. They're always visible
 * (no collapse) because the usability win of visibility dwarfs the pixels
 * lost.
 */
export default function PageHelp({
  title,
  purpose,
  howTo,
  learnMoreHref,
  variant = "default",
}: {
  title: string;
  purpose: string;
  howTo?: string;
  learnMoreHref?: string;
  /** `subtle` = thinner, lower contrast (for tab sub-pages). */
  variant?: "default" | "subtle";
}) {
  const isSubtle = variant === "subtle";
  return (
    <header
      aria-label={`About this page: ${title}`}
      style={{
        margin: "0 auto 1.5rem",
        maxWidth: "1200px",
        padding: isSubtle ? "0.75rem 1.25rem" : "1.25rem 1.5rem",
        background: isSubtle ? "transparent" : "var(--stone-light)",
        borderLeft: `3px solid var(--gold${isSubtle ? "-dim" : ""})`,
        borderRadius: 2,
      }}
    >
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
            color: "var(--gold)",
            margin: 0,
          }}
        >
          {title}
        </h1>
        {learnMoreHref ? (
          // Plain anchor (not Next.js `Link`) because the target is a PDF
          // in /public/ — Link would prefetch it as if it were a page and
          // swallow the `target="_blank"` semantics we want.
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
          lineHeight: 1.6,
          color: "var(--parchment)",
          margin: "0.5rem 0 0",
        }}
      >
        {purpose}
      </p>
      {howTo ? (
        <p
          style={{
            fontFamily: "'EB Garamond', Georgia, serif",
            fontSize: "0.9rem",
            lineHeight: 1.6,
            color: "var(--parchment-dim)",
            margin: "0.35rem 0 0",
          }}
        >
          {howTo}
        </p>
      ) : null}
    </header>
  );
}
