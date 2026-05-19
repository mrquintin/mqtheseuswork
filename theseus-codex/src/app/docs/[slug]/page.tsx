import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import {
  getPublicDoc,
  listPublicDocs,
  PUBLIC_DOCS_SAFETY_NOTE,
} from "@/content/publicDocs";

type RouteParams = { slug: string };

export function generateStaticParams(): RouteParams[] {
  return listPublicDocs().map((doc) => ({ slug: doc.slug }));
}

export async function generateMetadata(props: {
  params: Promise<RouteParams>;
}): Promise<Metadata> {
  const params = await props.params;
  const doc = getPublicDoc(params.slug);
  if (!doc) {
    return {
      title: "Documentation not found",
      robots: { index: false, follow: false },
    };
  }
  return {
    title: `${doc.title} — Documentation`,
    description: doc.summary,
    openGraph: {
      title: `${doc.title} — Theseus Codex documentation`,
      description: doc.summary,
      type: "article",
    },
  };
}

export default async function DocDetailPage(props: {
  params: Promise<RouteParams>;
}) {
  const params = await props.params;
  const doc = getPublicDoc(params.slug);
  if (!doc) notFound();

  const founder = await getFounder();
  const allDocs = listPublicDocs();
  const prev = allDocs.find((d) => d.order === doc.order - 1);
  const next = allDocs.find((d) => d.order === doc.order + 1);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container" style={mainStyle}>
        <nav aria-label="Breadcrumb" style={breadcrumbStyle} className="mono">
          <Link href="/docs" style={breadcrumbLinkStyle}>
            ← All documentation
          </Link>
        </nav>

        <header style={{ marginTop: "1.4rem" }}>
          <p className="mono" style={kickerStyle}>
            {doc.sourceGuide}
          </p>
          <h1 className="public-title" style={{ marginTop: "0.4rem" }}>
            {doc.title}
          </h1>
          <p style={subtitleStyle}>{doc.subtitle}</p>
          <dl style={metaListStyle}>
            <div style={metaRowStyle}>
              <dt className="mono" style={metaDtStyle}>
                For
              </dt>
              <dd style={metaDdStyle}>{doc.audience}</dd>
            </div>
            <div style={metaRowStyle}>
              <dt className="mono" style={metaDtStyle}>
                Summary
              </dt>
              <dd style={metaDdStyle}>{doc.summary}</dd>
            </div>
          </dl>
        </header>

        <p
          className="public-muted"
          role="note"
          style={noteStyle}
        >
          {PUBLIC_DOCS_SAFETY_NOTE}
        </p>

        {doc.sections.map((section) => (
          <section
            key={section.heading}
            className="public-section"
            aria-label={section.heading}
            style={sectionStyle}
          >
            <h2 style={sectionHeadingStyle}>{section.heading}</h2>
            {section.paragraphs.map((paragraph, index) => (
              <p key={index} style={paragraphStyle}>
                {paragraph}
              </p>
            ))}
            {section.bullets && section.bullets.length > 0 ? (
              <ul style={bulletListStyle}>
                {section.bullets.map((bullet) => (
                  <li key={bullet} style={bulletItemStyle}>
                    {bullet}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ))}

        {doc.relatedRoutes.length > 0 ? (
          <section
            className="public-section"
            aria-labelledby={`${doc.slug}-related-title`}
            style={sectionStyle}
          >
            <h2
              id={`${doc.slug}-related-title`}
              style={sectionHeadingStyle}
            >
              Related public routes
            </h2>
            <ul style={relatedListStyle}>
              {doc.relatedRoutes.map((route) => (
                <li key={route.href}>
                  <Link
                    href={route.href}
                    className="public-card"
                    style={relatedLinkStyle}
                  >
                    <div
                      className="mono"
                      style={{
                        color: "var(--amber-dim)",
                        fontSize: "0.6rem",
                        letterSpacing: "0.22em",
                        marginBottom: "0.4rem",
                        textTransform: "uppercase",
                      }}
                    >
                      {route.href}
                    </div>
                    <div style={relatedLabelStyle}>{route.label}</div>
                    <p style={relatedBodyStyle}>{route.description}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <nav
          aria-label="Documentation pagination"
          style={paginationStyle}
        >
          {prev ? (
            <Link href={`/docs/${prev.slug}`} style={paginationLinkStyle}>
              <span className="mono" style={paginationKickerStyle}>
                ← Previous
              </span>
              <span style={paginationLabelStyle}>{prev.title}</span>
            </Link>
          ) : (
            <span />
          )}
          {next ? (
            <Link
              href={`/docs/${next.slug}`}
              style={{ ...paginationLinkStyle, textAlign: "right" }}
            >
              <span className="mono" style={paginationKickerStyle}>
                Next →
              </span>
              <span style={paginationLabelStyle}>{next.title}</span>
            </Link>
          ) : (
            <span />
          )}
        </nav>
      </main>
    </>
  );
}

const mainStyle: CSSProperties = {
  maxWidth: "780px",
  paddingBottom: "5rem",
};

const breadcrumbStyle: CSSProperties = {
  borderBottom: "1px solid var(--stroke, var(--border))",
  paddingBottom: "0.7rem",
  paddingTop: "1.2rem",
};

const breadcrumbLinkStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontSize: "0.62rem",
  letterSpacing: "0.22em",
  textDecoration: "none",
  textTransform: "uppercase",
};

const kickerStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontSize: "0.62rem",
  letterSpacing: "0.3em",
  margin: 0,
  textTransform: "uppercase",
};

const subtitleStyle: CSSProperties = {
  color: "var(--parchment)",
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.1rem",
  fontStyle: "italic",
  lineHeight: 1.4,
  margin: "0.5rem 0 0",
  maxWidth: "70ch",
};

const metaListStyle: CSSProperties = {
  display: "grid",
  gap: "0.6rem",
  margin: "1.4rem 0 0",
};

const metaRowStyle: CSSProperties = {
  display: "grid",
  gap: "0.4rem",
  gridTemplateColumns: "minmax(60px, 110px) 1fr",
};

const metaDtStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontSize: "0.6rem",
  letterSpacing: "0.22em",
  margin: 0,
  paddingTop: "0.18rem",
  textTransform: "uppercase",
};

const metaDdStyle: CSSProperties = {
  color: "var(--parchment)",
  fontSize: "0.95rem",
  lineHeight: 1.55,
  margin: 0,
  maxWidth: "60ch",
};

const noteStyle: CSSProperties = {
  borderLeft: "2px solid var(--amber-deep, var(--amber-dim))",
  fontSize: "0.85rem",
  lineHeight: 1.55,
  margin: "1.6rem 0 0",
  maxWidth: "70ch",
  padding: "0.3rem 0 0.3rem 0.9rem",
};

const sectionStyle: CSSProperties = {
  borderTop: "1px solid var(--stroke, var(--border))",
  margin: "2rem 0 0",
  paddingTop: "1.5rem",
};

const sectionHeadingStyle: CSSProperties = {
  color: "var(--amber)",
  fontSize: "clamp(1.1rem, 2.4vw, 1.4rem)",
  lineHeight: 1.25,
  margin: 0,
};

const paragraphStyle: CSSProperties = {
  color: "var(--parchment)",
  fontSize: "1rem",
  lineHeight: 1.65,
  margin: "0.85rem 0 0",
  maxWidth: "70ch",
};

const bulletListStyle: CSSProperties = {
  display: "grid",
  gap: "0.5rem",
  margin: "1rem 0 0",
  paddingLeft: "1.1rem",
};

const bulletItemStyle: CSSProperties = {
  color: "var(--parchment)",
  fontSize: "0.97rem",
  lineHeight: 1.55,
  maxWidth: "68ch",
};

const relatedListStyle: CSSProperties = {
  display: "grid",
  gap: "0.7rem",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  listStyle: "none",
  margin: "1rem 0 0",
  padding: 0,
};

const relatedLinkStyle: CSSProperties = {
  color: "inherit",
  display: "block",
  padding: "0.85rem 1rem",
  textDecoration: "none",
};

const relatedLabelStyle: CSSProperties = {
  color: "var(--amber)",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.95rem",
  letterSpacing: "0.03em",
  marginBottom: "0.4rem",
};

const relatedBodyStyle: CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.88rem",
  lineHeight: 1.5,
  margin: 0,
};

const paginationStyle: CSSProperties = {
  borderTop: "1px solid var(--stroke, var(--border))",
  display: "grid",
  gap: "1rem",
  gridTemplateColumns: "1fr 1fr",
  margin: "2.5rem 0 0",
  paddingTop: "1.5rem",
};

const paginationLinkStyle: CSSProperties = {
  color: "inherit",
  display: "block",
  textDecoration: "none",
};

const paginationKickerStyle: CSSProperties = {
  color: "var(--amber-dim)",
  display: "block",
  fontSize: "0.62rem",
  letterSpacing: "0.22em",
  marginBottom: "0.3rem",
  textTransform: "uppercase",
};

const paginationLabelStyle: CSSProperties = {
  color: "var(--amber)",
  display: "block",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.95rem",
  letterSpacing: "0.03em",
};
