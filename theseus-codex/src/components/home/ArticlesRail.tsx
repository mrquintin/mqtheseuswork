import Link from "next/link";

import {
  ARTICLES_EMPTY_COPY,
  type HomeArticleCard,
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
 * Articles rail — long-form essays/memos on the public homepage.
 *
 * Server component. Renders the latest published articles. Each card
 * carries title, subtitle, publishedAt, author display name (via
 * `founderDisplayName`, which filters out the "Founder Alpha" seeded
 * placeholder), and a reading-time estimate. Card links to the
 * article detail page (`/c/[slug]` or `/post/[slug]`).
 */
export default function ArticlesRail({
  articles,
}: {
  articles: HomeArticleCard[];
}) {
  return (
    <section
      aria-labelledby="home-articles-title"
      data-testid="homepage-articles-rail"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <h2
        id="home-articles-title"
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
        Articles
      </h2>

      {articles.length === 0 ? (
        <p
          data-testid="homepage-articles-empty"
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
          {ARTICLES_EMPTY_COPY}
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
          {articles.map((article) => (
            <li key={article.id} style={{ margin: 0 }}>
              <Link
                data-testid="homepage-article-card"
                data-source={article.source}
                href={article.href}
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
                  data-testid="homepage-article-meta"
                  style={{
                    color: "var(--parchment-dim)",
                    display: "block",
                    fontSize: "0.58rem",
                    letterSpacing: "0.16em",
                    marginBottom: "0.4rem",
                    textTransform: "uppercase",
                  }}
                >
                  {formatPublishedAtShort(article.publishedAt)} ·{" "}
                  {article.authorDisplayName} · {article.readingTimeMin} min
                  read
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
                  {article.title}
                </strong>
                {article.subtitle ? (
                  <span
                    style={{
                      color: "var(--parchment-dim)",
                      display: "block",
                      fontSize: "0.92rem",
                      lineHeight: 1.45,
                      marginTop: "0.5rem",
                    }}
                  >
                    {article.subtitle}
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
