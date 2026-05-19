import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import {
  listPublicDocs,
  PUBLIC_DOCS_SAFETY_NOTE,
  PUBLIC_DOCS_SYSTEM_MAP,
} from "@/content/publicDocs";

export const metadata: Metadata = {
  title: "Documentation",
  description:
    "Public documentation for Theseus Codex: how the firm turns recorded material into claims, principles, algorithms, and reviewed public output.",
  openGraph: {
    title: "Theseus Codex documentation",
    description:
      "Algorithms, interfaces, methodology, and operator workflow — described for outside readers.",
    type: "website",
  },
};

export default async function DocsIndexPage() {
  const founder = await getFounder();
  const docs = listPublicDocs();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container" style={mainStyle}>
        <section className="public-section" style={{ paddingTop: "2rem" }}>
          <p className="mono" style={kickerStyle}>
            Theseus Codex · Documentation
          </p>
          <h1 className="public-title" style={{ marginTop: "0.5rem" }}>
            How the system works
          </h1>
          <p className="public-lede" style={{ maxWidth: "70ch" }}>
            These pages describe Theseus Codex at the level of methodology,
            algorithms, interfaces, and operator workflow. They paraphrase
            the firm&rsquo;s internal guides for outside readers, sanitized
            of private corpus material, internal credentials, and unreleased
            work. For the methods themselves and the calibration record, the
            companion routes are{" "}
            <Link href="/methodology" style={inlineLinkStyle}>
              /methodology
            </Link>{" "}
            and{" "}
            <Link href="/principles" style={inlineLinkStyle}>
              /principles
            </Link>
            .
          </p>
          <p className="public-muted" style={noteStyle} role="note">
            {PUBLIC_DOCS_SAFETY_NOTE}
          </p>
        </section>

        <section
          className="public-section"
          aria-labelledby="docs-system-map-title"
        >
          <p className="mono" style={layerTagStyle}>
            The path material takes
          </p>
          <h2 id="docs-system-map-title" style={sectionHeadingStyle}>
            Source → claims → principles → algorithms → public surfaces
          </h2>
          <p className="public-muted" style={{ marginTop: "0.4rem", maxWidth: "70ch" }}>
            Every public artifact on this site reduces to one of the stages
            below. The vocabulary is worth pinning down before reading the
            individual guides: an evidence claim is an atomic sentence with
            provenance, a principle is the durable reusable rule, and an
            algorithm is the repeatable reasoning function that applies
            principles to inputs.
          </p>
          <ol style={stageListStyle}>
            {PUBLIC_DOCS_SYSTEM_MAP.map((step, index) => (
              <li key={step.stage} style={stageItemStyle}>
                <span className="mono" style={stageIndexStyle}>
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <div style={stageTitleStyle}>{step.stage}</div>
                  <p style={stageBodyStyle}>{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section
          className="public-section"
          aria-labelledby="docs-index-title"
        >
          <p className="mono" style={layerTagStyle}>
            The seven guides
          </p>
          <h2 id="docs-index-title" style={sectionHeadingStyle}>
            Documentation index
          </h2>
          <ul style={docListStyle}>
            {docs.map((doc) => (
              <li key={doc.slug} style={docItemStyle}>
                <Link
                  href={`/docs/${doc.slug}`}
                  className="public-card"
                  style={docLinkStyle}
                >
                  <div
                    className="mono"
                    style={{
                      fontSize: "0.6rem",
                      letterSpacing: "0.22em",
                      textTransform: "uppercase",
                      color: "var(--public-muted, #888)",
                      marginBottom: "0.45rem",
                    }}
                  >
                    {String(doc.order).padStart(2, "0")} · {doc.sourceGuide}
                  </div>
                  <div style={docTitleStyle}>{doc.title}</div>
                  <div style={docSubtitleStyle}>{doc.subtitle}</div>
                  <p style={docSummaryStyle}>{doc.summary}</p>
                  <div
                    className="mono"
                    style={{
                      color: "var(--amber, #d4a017)",
                      fontSize: "0.62rem",
                      letterSpacing: "0.22em",
                      marginTop: "0.9rem",
                      textTransform: "uppercase",
                    }}
                  >
                    Read →
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section
          className="public-section"
          aria-labelledby="docs-boundaries-title"
        >
          <h2 id="docs-boundaries-title" style={sectionHeadingStyle}>
            What these docs do not contain
          </h2>
          <p className="public-muted" style={{ maxWidth: "70ch" }}>
            The guides describe the platform&rsquo;s public-facing methodology and
            architecture. They deliberately omit the firm&rsquo;s private
            corpus rows, uploaded source material, internal release URLs,
            machine credentials, environment configuration, unreleased
            research memos, and any organization-specific content. The
            firm&rsquo;s reviewed conclusions and reasoning live at{" "}
            <Link href="/methodology" style={inlineLinkStyle}>
              /methodology
            </Link>{" "}
            and{" "}
            <Link href="/principles" style={inlineLinkStyle}>
              /principles
            </Link>
            ; the operator surfaces they describe are accessible only to
            authorized roles inside the firm.
          </p>
        </section>
      </main>
    </>
  );
}

const mainStyle: CSSProperties = {
  maxWidth: "960px",
  paddingBottom: "5rem",
};

const kickerStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontSize: "0.62rem",
  letterSpacing: "0.3em",
  margin: 0,
  textTransform: "uppercase",
};

const layerTagStyle: CSSProperties = {
  fontSize: "0.62rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--amber, #d4a017)",
  margin: "0 0 0.25rem",
};

const sectionHeadingStyle: CSSProperties = {
  color: "var(--amber)",
  fontSize: "clamp(1.15rem, 2.6vw, 1.55rem)",
  lineHeight: 1.25,
  margin: 0,
};

const inlineLinkStyle: CSSProperties = {
  color: "var(--amber)",
  textDecoration: "underline",
  textDecorationThickness: "0.07em",
  textUnderlineOffset: "0.18em",
};

const noteStyle: CSSProperties = {
  borderLeft: "2px solid var(--amber-deep, var(--amber-dim))",
  fontSize: "0.88rem",
  lineHeight: 1.55,
  margin: "1.5rem 0 0",
  maxWidth: "70ch",
  padding: "0.3rem 0 0.3rem 0.9rem",
};

const stageListStyle: CSSProperties = {
  display: "grid",
  gap: "0.85rem",
  listStyle: "none",
  margin: "1rem 0 0",
  padding: 0,
};

const stageItemStyle: CSSProperties = {
  alignItems: "flex-start",
  background: "rgba(232, 225, 211, 0.035)",
  border: "1px solid rgba(232, 225, 211, 0.12)",
  borderRadius: "5px",
  display: "grid",
  gap: "0.9rem",
  gridTemplateColumns: "auto 1fr",
  padding: "0.85rem 1rem",
};

const stageIndexStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontSize: "0.7rem",
  letterSpacing: "0.18em",
  paddingTop: "0.15rem",
};

const stageTitleStyle: CSSProperties = {
  color: "var(--amber)",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.98rem",
  letterSpacing: "0.04em",
  marginBottom: "0.25rem",
};

const stageBodyStyle: CSSProperties = {
  color: "var(--parchment)",
  fontSize: "0.95rem",
  lineHeight: 1.55,
  margin: 0,
  maxWidth: "70ch",
};

const docListStyle: CSSProperties = {
  display: "grid",
  gap: "0.9rem",
  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
  listStyle: "none",
  margin: "1rem 0 0",
  padding: 0,
};

const docItemStyle: CSSProperties = {
  display: "block",
};

const docLinkStyle: CSSProperties = {
  color: "inherit",
  display: "flex",
  flexDirection: "column",
  height: "100%",
  padding: "1.1rem 1.2rem",
  textDecoration: "none",
};

const docTitleStyle: CSSProperties = {
  color: "var(--amber)",
  fontFamily: "'Cinzel', serif",
  fontSize: "1.05rem",
  letterSpacing: "0.03em",
  marginBottom: "0.25rem",
};

const docSubtitleStyle: CSSProperties = {
  color: "var(--parchment)",
  fontFamily: "'EB Garamond', serif",
  fontSize: "0.96rem",
  fontStyle: "italic",
  lineHeight: 1.4,
  marginBottom: "0.6rem",
};

const docSummaryStyle: CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.92rem",
  lineHeight: 1.55,
  margin: 0,
};
