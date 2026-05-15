import Link from "next/link";

import {
  CONCLUSIONS_EMPTY_COPY,
  type HomeConclusionCard,
} from "@/lib/publicSurface";

const editorialTitleFont = "'EB Garamond', 'Iowan Old Style', Georgia, serif";

function formatPublishedAtShort(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(date);
}

/**
 * Conclusions rail — reviewed firm conclusions on the public homepage.
 *
 * Server component. Renders the latest surfaceable conclusions
 * (PublishedConclusion rows with kind = 'CONCLUSION'). Each card
 * carries title, publishedAt, and a short subtitle pulled from the
 * evidence summary or rationale. Card links to the conclusion detail
 * page (`/c/[slug]`).
 */
export default function ConclusionsRail({
  conclusions,
}: {
  conclusions: HomeConclusionCard[];
}) {
  return (
    <section
      aria-labelledby="home-conclusions-title"
      data-testid="homepage-conclusions-rail"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <h2
        id="home-conclusions-title"
        style={{
          color: "var(--parchment)",
          fontFamily: editorialTitleFont,
          fontSize: "clamp(1.22rem, 2vw, 1.48rem)",
          fontWeight: 500,
          letterSpacing: 0,
          lineHeight: 1.18,
          margin: "0 0 0.85rem",
        }}
      >
        Conclusions
      </h2>

      {conclusions.length === 0 ? (
        <p
          data-testid="homepage-conclusions-empty"
          style={{
            background: "rgba(232, 225, 211, 0.035)",
            border: "1px solid rgba(232, 225, 211, 0.12)",
            color: "var(--parchment-dim)",
            fontSize: "0.95rem",
            lineHeight: 1.55,
            margin: 0,
            padding: "1rem",
          }}
        >
          {CONCLUSIONS_EMPTY_COPY}
        </p>
      ) : (
        <ul
          style={{
            display: "grid",
            gap: "0.85rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            listStyle: "none",
            margin: 0,
            padding: 0,
          }}
        >
          {conclusions.map((conclusion) => (
            <li key={conclusion.id} style={{ margin: 0 }}>
              <Link
                data-testid="homepage-conclusion-card"
                href={conclusion.href}
                style={{
                  border: "1px solid rgba(205, 151, 67, 0.22)",
                  color: "inherit",
                  display: "block",
                  height: "100%",
                  padding: "0.95rem",
                  textDecoration: "none",
                }}
              >
                <span
                  className="mono"
                  style={{
                    color: "var(--parchment-dim)",
                    display: "block",
                    fontSize: "0.58rem",
                    letterSpacing: "0.16em",
                    marginBottom: "0.4rem",
                    textTransform: "uppercase",
                  }}
                >
                  {formatPublishedAtShort(conclusion.publishedAt)} · v
                  {conclusion.version}
                </span>
                <strong
                  style={{
                    color: "var(--amber)",
                    display: "block",
                    fontFamily: editorialTitleFont,
                    fontSize: "1.12rem",
                    fontWeight: 500,
                    letterSpacing: 0,
                    lineHeight: 1.28,
                  }}
                >
                  {conclusion.title}
                </strong>
                {conclusion.subtitle ? (
                  <span
                    style={{
                      color: "var(--parchment-dim)",
                      display: "block",
                      fontSize: "0.92rem",
                      lineHeight: 1.45,
                      marginTop: "0.5rem",
                    }}
                  >
                    {conclusion.subtitle}
                  </span>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
