import Link from "next/link";

import DualPulseSection from "@/app/(home)/DualPulseSection";
import TransparencyFooter from "@/app/(home)/TransparencyFooter";
import PublicHeader from "@/components/PublicHeader";
import {
  getTheseusContactEmail,
  theseusIdentity,
} from "@/content/theseusIdentity";
import { getFounder } from "@/lib/auth";
import {
  listPublishedArticles,
  type PublishedConclusion,
} from "@/lib/conclusionsRead";
import { listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";

export const dynamic = "force-dynamic";
export const revalidate = 60;

async function latestCurrents(): Promise<PublicOpinion[]> {
  try {
    const response = await listCurrents({ limit: 3 });
    return Array.isArray(response.items) ? response.items.slice(0, 3) : [];
  } catch (error) {
    console.error("homepage_currents_preview_failed", error);
    return [];
  }
}

async function latestArticles(): Promise<PublishedConclusion[]> {
  try {
    return await listPublishedArticles(4);
  } catch (error) {
    console.error("homepage_publications_preview_failed", error);
    return [];
  }
}

export default async function PublicHomePage() {
  const [founder, currents, articles] = await Promise.all([
    getFounder(),
    latestCurrents(),
    latestArticles(),
  ]);
  const email = getTheseusContactEmail();
  const hasPublicOutput = currents.length > 0 || articles.length > 0;

  return (
    <main
      style={{
        minHeight: "100vh",
        position: "relative",
      }}
    >
      <PublicHeader authed={Boolean(founder)} />

      <div
        style={{
          margin: "0 auto",
          maxWidth: "1120px",
          padding: "3.75rem 2rem 6rem",
          position: "relative",
          zIndex: 1,
        }}
      >
        <IdentityStrip />

        {!hasPublicOutput ? <EmptyPublicOutput email={email} /> : null}

        <CurrentsPreviewRail currents={currents} />
        <PublicationsRail articles={articles} />

        <div aria-label="Live public pulse" style={{ margin: "2rem 0" }}>
          <DualPulseSection />
        </div>

        <ManifestoPreview />
        <ContactLine email={email} />
        <TransparencyFooter />
      </div>
    </main>
  );
}

function IdentityStrip() {
  return (
    <section
      aria-labelledby="home-identity-title"
      id="about"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "2rem",
      }}
    >
      <h1
        className="mono"
        id="home-identity-title"
        style={{
          color: "var(--amber)",
          fontSize: "clamp(1.65rem, 4vw, 3.1rem)",
          fontWeight: 700,
          letterSpacing: "0.16em",
          lineHeight: 1.08,
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {theseusIdentity.homePage.identityTitle}
      </h1>
      <p
        style={{
          color: "var(--parchment)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "clamp(1.2rem, 2.2vw, 1.7rem)",
          lineHeight: 1.32,
          margin: "1rem 0 0",
          maxWidth: "44rem",
        }}
      >
        {theseusIdentity.oneLine}
      </p>
      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.94rem",
          lineHeight: 1.6,
          margin: "0.7rem 0 0",
          maxWidth: "42rem",
        }}
      >
        {theseusIdentity.homePage.commonsLine}
      </p>
      <div
        style={{
          alignItems: "center",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.85rem",
          marginTop: "1.45rem",
        }}
      >
        <Link
          className="mono"
          href="/about"
          style={{
            background: "var(--amber)",
            border: "1px solid var(--amber)",
            borderRadius: "3px",
            color: "#120d08",
            display: "inline-flex",
            fontSize: "0.68rem",
            fontWeight: 700,
            letterSpacing: "0.2em",
            padding: "0.72rem 1rem",
            textDecoration: "none",
            textTransform: "uppercase",
          }}
        >
          About →
        </Link>
        <Link
          className="mono"
          href="/login"
          style={{
            color: "var(--amber)",
            display: "inline-flex",
            fontSize: "0.68rem",
            letterSpacing: "0.2em",
            padding: "0.72rem 0",
            textDecoration: "none",
            textTransform: "uppercase",
          }}
        >
          Founder login →
        </Link>
      </div>
    </section>
  );
}

function CurrentsPreviewRail({ currents }: { currents: PublicOpinion[] }) {
  return (
    <section
      aria-labelledby="home-currents-title"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <RailHeader
        href="/currents"
        linkLabel="View all currents →"
        title="LATEST FROM THE FIRM · CURRENTS"
        titleId="home-currents-title"
      />

      {currents.length ? (
        <div
          data-testid="homepage-currents-preview"
          style={{
            display: "grid",
            gap: "0.9rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          }}
        >
          {currents.map((opinion) => (
            <Link
              data-testid="homepage-current-card"
              href={`/currents/${encodeURIComponent(opinion.id)}`}
              key={opinion.id}
              style={{
                background: "rgba(232, 225, 211, 0.035)",
                border: "1px solid rgba(232, 225, 211, 0.14)",
                borderRadius: "6px",
                color: "inherit",
                display: "block",
                minHeight: "11rem",
                padding: "1rem",
                textDecoration: "none",
              }}
            >
              <time
                className="mono"
                dateTime={opinion.generated_at}
                style={{
                  color: "var(--amber-dim)",
                  display: "block",
                  fontSize: "0.58rem",
                  letterSpacing: "0.16em",
                  marginBottom: "0.55rem",
                  textTransform: "uppercase",
                }}
              >
                {formatTimestamp(opinion.generated_at)}
              </time>
              <h3
                style={{
                  color: "var(--amber)",
                  fontFamily: "'Cinzel', serif",
                  fontSize: "1.05rem",
                  letterSpacing: "0.03em",
                  lineHeight: 1.25,
                  margin: 0,
                }}
              >
                {opinion.headline}
              </h3>
              <p
                style={{
                  color: "var(--parchment-dim)",
                  display: "-webkit-box",
                  fontSize: "0.92rem",
                  lineHeight: 1.45,
                  margin: "0.65rem 0 0",
                  overflow: "hidden",
                  WebkitBoxOrient: "vertical",
                  WebkitLineClamp: 2,
                }}
              >
                {summarizeOpinion(opinion)}
              </p>
            </Link>
          ))}
        </div>
      ) : (
        <RailEmpty>No Currents opinions are public yet.</RailEmpty>
      )}
    </section>
  );
}

function PublicationsRail({ articles }: { articles: PublishedConclusion[] }) {
  return (
    <section
      aria-labelledby="home-publications-title"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <RailHeader
        href="/responses?tab=articles"
        linkLabel="View all publications →"
        title="PUBLICATIONS · ESSAYS & MEMOS"
        titleId="home-publications-title"
      />

      {articles.length ? (
        <div
          style={{
            display: "grid",
            gap: "0.75rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          }}
        >
          {articles.map((article) => (
            <Link
              href={`/c/${encodeURIComponent(article.slug)}`}
              key={article.id}
              style={{
                border: "1px solid rgba(205, 151, 67, 0.22)",
                color: "inherit",
                display: "block",
                padding: "0.85rem",
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
                  marginBottom: "0.35rem",
                  textTransform: "uppercase",
                }}
              >
                {article.publishedAt.slice(0, 10)}
              </span>
              <strong
                style={{
                  color: "var(--amber)",
                  display: "block",
                  fontFamily: "'Cinzel', serif",
                  lineHeight: 1.25,
                }}
              >
                {article.payload.conclusionText}
              </strong>
              <span
                style={{
                  color: "var(--parchment-dim)",
                  display: "block",
                  fontSize: "0.9rem",
                  lineHeight: 1.45,
                  marginTop: "0.45rem",
                }}
              >
                {deriveExcerpt(
                  article.payload.evidenceSummary || article.payload.rationale,
                  160,
                )}
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <RailEmpty>No essays or memos are public yet.</RailEmpty>
      )}
    </section>
  );
}

function ManifestoPreview() {
  return (
    <section
      aria-labelledby="home-manifesto-title"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "1.5rem",
        padding: "0 0 1.75rem",
      }}
    >
      <h2
        className="mono"
        id="home-manifesto-title"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.72rem",
          letterSpacing: "0.3em",
          margin: "0 0 0.85rem",
          textTransform: "uppercase",
        }}
      >
        MANIFESTO
      </h2>
      <p
        style={{
          color: "var(--parchment)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "1.18rem",
          lineHeight: 1.55,
          margin: "0 0 0.85rem",
          maxWidth: "50rem",
        }}
      >
        {theseusIdentity.manifestoExcerpt}
      </p>
      <Link
        className="mono"
        href="/about#manifesto"
        style={{
          color: "var(--amber)",
          fontSize: "0.66rem",
          letterSpacing: "0.18em",
          textDecoration: "none",
          textTransform: "uppercase",
        }}
      >
        Read the full manifesto →
      </Link>
    </section>
  );
}

function ContactLine({ email }: { email: string }) {
  return (
    <p
      style={{
        color: "var(--parchment-dim)",
        fontSize: "0.95rem",
        lineHeight: 1.6,
        margin: "0",
      }}
    >
      Reach the firm at{" "}
      <a
        href={`mailto:${email}`}
        style={{ color: "var(--amber)", textDecoration: "none" }}
      >
        {email}
      </a>
      .
    </p>
  );
}

function EmptyPublicOutput({ email }: { email: string }) {
  return (
    <section
      aria-label="No public publications yet"
      className="ascii-frame"
      data-label="PUBLIC COMMONS"
      style={{
        margin: "0 0 2rem",
        padding: "1.3rem 1.4rem",
      }}
    >
      <p
        style={{
          color: "var(--parchment)",
          fontSize: "1rem",
          lineHeight: 1.55,
          margin: 0,
        }}
      >
        The firm has not yet published anything publicly. Reach out:{" "}
        <a
          href={`mailto:${email}`}
          style={{ color: "var(--amber)", textDecoration: "none" }}
        >
          {email}
        </a>
        .
      </p>
    </section>
  );
}

function RailHeader({
  href,
  linkLabel,
  title,
  titleId,
}: {
  href: string;
  linkLabel: string;
  title: string;
  titleId: string;
}) {
  return (
    <div
      style={{
        alignItems: "center",
        display: "flex",
        flexWrap: "wrap",
        gap: "0.8rem",
        justifyContent: "space-between",
        marginBottom: "0.85rem",
      }}
    >
      <h2
        className="mono"
        id={titleId}
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.72rem",
          letterSpacing: "0.3em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {title}
      </h2>
      <Link
        className="mono"
        href={href}
        style={{
          color: "var(--amber)",
          fontSize: "0.62rem",
          letterSpacing: "0.2em",
          textDecoration: "none",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        {linkLabel}
      </Link>
    </div>
  );
}

function RailEmpty({ children }: { children: string }) {
  return (
    <p
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
      {children}
    </p>
  );
}

function summarizeOpinion(opinion: PublicOpinion): string {
  if (opinion.abstention_reason) return opinion.abstention_reason;
  const body = stripMarkdown(opinion.body_markdown);
  return deriveExcerpt(body || opinion.event?.text || "", 140);
}

function stripMarkdown(text: string): string {
  return text
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[#>_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date pending";

  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    timeZone: "UTC",
    timeZoneName: "short",
    year: "numeric",
  }).format(date);
}

function deriveExcerpt(text: string, limit = 300): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "(no preview available)";
  if (cleaned.length <= limit) return cleaned;
  const cut = cleaned.slice(0, limit);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > limit * 0.65 ? cut.slice(0, lastSpace) : cut) + "…";
}
