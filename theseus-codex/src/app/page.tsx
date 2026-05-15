import Link from "next/link";

import TransparencyFooter from "@/app/(home)/TransparencyFooter";
import ArticlesRail from "@/components/home/ArticlesRail";
import ConclusionsRail from "@/components/home/ConclusionsRail";
import PublicAskBox from "@/components/PublicAskBox";
import PublicHeader from "@/components/PublicHeader";
import SubscribeForm from "@/components/SubscribeForm";
import {
  getTheseusContactEmail,
  theseusIdentity,
} from "@/content/theseusIdentity";
import { getCurrentsHealth, listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { firmVoice } from "@/lib/firmVoice";
import {
  CURRENTS_EMPTY_COPY,
  listHomepageArticles,
  listHomepageConclusions,
  type HomeArticleCard,
  type HomeConclusionCard,
} from "@/lib/publicSurface";

// SSR contract: every request rebuilds from the database so a publish
// shows up within one render cycle (well inside the 60-second SLO).
// We do not use a long static cache. Cache invalidation on publish is
// documented in `docs/operator/public_surfacing.md`.
export const dynamic = "force-dynamic";

const editorialTitleFont = "'EB Garamond', 'Iowan Old Style', Georgia, serif";
const HOME_PREVIEW_TIMEOUT_MS = 2_000;
const HOME_SURFACE_TIMEOUT_MS = 1_500;

async function softTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  fallback: T,
): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((resolve) => {
        timeoutId = setTimeout(() => resolve(fallback), timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId !== null) clearTimeout(timeoutId);
  }
}

async function latestCurrents(): Promise<PublicOpinion[]> {
  try {
    const response = await listCurrents(
      { limit: 3 },
      {
        next: { revalidate: 60, tags: ["public-home-currents"] },
        timeoutMs: HOME_PREVIEW_TIMEOUT_MS,
      },
    );
    return Array.isArray(response.items) ? response.items.slice(0, 3) : [];
  } catch (error) {
    console.error("homepage_currents_preview_failed", error);
    return [];
  }
}

async function latestArticles(): Promise<HomeArticleCard[]> {
  try {
    return await softTimeout(listHomepageArticles(5), HOME_SURFACE_TIMEOUT_MS, []);
  } catch (error) {
    console.error("homepage_articles_preview_failed", error);
    return [];
  }
}

async function latestConclusions(): Promise<HomeConclusionCard[]> {
  try {
    return await softTimeout(listHomepageConclusions(8), HOME_SURFACE_TIMEOUT_MS, []);
  } catch (error) {
    console.error("homepage_conclusions_preview_failed", error);
    return [];
  }
}

interface PublicSurfaceStatus {
  reachable: boolean;
  workersIdle: boolean;
}

async function publicSurfaceStatus(): Promise<PublicSurfaceStatus> {
  try {
    const health = await getCurrentsHealth({
      next: { revalidate: 60, tags: ["public-home-currents"] },
      timeoutMs: HOME_PREVIEW_TIMEOUT_MS,
    });
    return {
      reachable: true,
      workersIdle: health.disabled_reasons.length > 0,
    };
  } catch (error) {
    console.error("homepage_currents_health_failed", error);
    return { reachable: false, workersIdle: true };
  }
}

export default async function PublicHomePage() {
  const [currents, articles, conclusions, surfaceStatus] = await Promise.all([
    latestCurrents(),
    latestArticles(),
    latestConclusions(),
    publicSurfaceStatus(),
  ]);
  const email = getTheseusContactEmail();
  const hasPublicOutput =
    currents.length > 0 || articles.length > 0 || conclusions.length > 0;

  return (
    <main
      style={{
        minHeight: "100vh",
        position: "relative",
      }}
    >
      <PublicHeader authed={false} />

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

        <section
          aria-label="Inquiry search"
          style={{
            borderBottom: "1px solid var(--stroke)",
            marginBottom: "2rem",
            paddingBottom: "1.75rem",
          }}
        >
          <PublicAskBox mode="compact" />
        </section>

        {!hasPublicOutput ? (
          <EmptyPublicOutput email={email} status={surfaceStatus} />
        ) : null}

        <ArticlesRail articles={articles} />
        <ConclusionsRail conclusions={conclusions} />
        <CurrentsPreviewRail currents={currents} status={surfaceStatus} />

        <PublicSignalSurface status={surfaceStatus} />

        <ManifestoPreview />
        <section
          aria-labelledby="home-follow-title"
          style={{
            borderBottom: "1px solid var(--stroke)",
            marginBottom: "1.5rem",
            padding: "0 0 1.75rem",
          }}
        >
          <h2
            className="mono"
            id="home-follow-title"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.72rem",
              letterSpacing: "0.3em",
              margin: "0 0 0.85rem",
              textTransform: "uppercase",
            }}
          >
            FOLLOW THE FIRM
          </h2>
          <SubscribeForm
            target={{ scope: "firm" }}
            title="Subscribe to firm-wide digests"
            intro="A digest of new publications, revisions, and retractions across every method and domain the firm runs. Double opt-in. One-click unsubscribe in every email. No tracking pixels."
          />
        </section>
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

function CurrentsPreviewRail({
  currents,
  status,
}: {
  currents: PublicOpinion[];
  status: PublicSurfaceStatus;
}) {
  return (
    <section
      aria-labelledby="home-currents-title"
      data-testid="homepage-currents-rail"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <RailHeader
        href="/currents"
        linkLabel="View all currents →"
        title="Currents from the firm"
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
              {/* R-008: title leads the card; meta strip lives beneath
                  in small caps separated by `·` middots. No pill fills. */}
              <h3
                style={{
                  color: "var(--amber)",
                  fontFamily: editorialTitleFont,
                  fontSize: "1.35rem",
                  fontWeight: 500,
                  letterSpacing: 0,
                  lineHeight: 1.22,
                  margin: 0,
                }}
                data-h3-glyph="off"
              >
                {opinion.headline}
              </h3>
              <p
                className="mono"
                style={{
                  color: "var(--amber-dim)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.16em",
                  margin: "0.4rem 0 0",
                  textTransform: "uppercase",
                }}
              >
                <time dateTime={opinion.generated_at}>
                  {formatTimestamp(opinion.generated_at)}
                </time>
                {opinion.topic_hint ? ` · ${opinion.topic_hint}` : ""}
              </p>
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
        <p
          data-testid="homepage-currents-empty"
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
          {currentsEmptyCopy(status)}
        </p>
      )}
    </section>
  );
}

function currentsEmptyCopy(status: PublicSurfaceStatus): string {
  if (!status.reachable) {
    return "Live publishing is paused — the Currents service is unreachable from the public site.";
  }
  if (status.workersIdle) {
    return "Live publishing is paused — the firm's ingestion workers are not running. Nothing new will appear here until they resume.";
  }
  return CURRENTS_EMPTY_COPY;
}

function PublicSignalSurface({ status }: { status: PublicSurfaceStatus }) {
  const heading = status.reachable && !status.workersIdle
    ? "LIVE PUBLIC SURFACES"
    : "PUBLIC SURFACES";
  const currentsBody = !status.reachable
    ? "Real-world X posts and other live signals, with the firm's public opinion in response. Live publishing is currently paused."
    : status.workersIdle
      ? "Real-world X posts and other live signals, with the firm's public opinion in response. Ingestion workers are not running, so new opinions are not being published right now."
      : "Real-world X posts and other live signals, with the firm's public opinion in response.";
  return (
    <section
      aria-labelledby="home-signal-title"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <h2
        className="mono"
        id="home-signal-title"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.72rem",
          letterSpacing: "0.3em",
          margin: "0 0 0.85rem",
          textTransform: "uppercase",
        }}
      >
        {heading}
      </h2>
      <div
        style={{
          display: "grid",
          gap: "0.85rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        }}
      >
        <SignalCard
          body={currentsBody}
          href="/currents"
          title="Currents"
        />
        <SignalCard
          body="Prediction-market forecasts with evidence, uncertainty, and eventual calibration."
          href="/forecasts"
          title="Forecasts"
        />
      </div>
    </section>
  );
}

function SignalCard({
  body,
  href,
  title,
}: {
  body: string;
  href: string;
  title: string;
}) {
  return (
    <Link
      href={href}
      style={{
        background: "rgba(232, 225, 211, 0.035)",
        border: "1px solid rgba(232, 225, 211, 0.14)",
        borderRadius: "6px",
        color: "inherit",
        display: "block",
        padding: "1rem",
        textDecoration: "none",
      }}
    >
      <strong
        style={{
          color: "var(--amber)",
          display: "block",
          fontFamily: "'Cinzel', serif",
          letterSpacing: "0.03em",
          marginBottom: "0.5rem",
        }}
      >
        {title}
      </strong>
      <span
        style={{
          color: "var(--parchment-dim)",
          display: "block",
          fontSize: "0.94rem",
          lineHeight: 1.5,
        }}
      >
        {body}
      </span>
    </Link>
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

function EmptyPublicOutput({
  email,
  status,
}: {
  email: string;
  status: PublicSurfaceStatus;
}) {
  const headline = !status.reachable
    ? "Public publishing is paused."
    : status.workersIdle
      ? "Public publishing is paused."
      : "No publications or Currents opinions are public yet.";
  const detail = !status.reachable
    ? "The Currents service is unreachable from the public site, so neither new opinions nor live signals can be published right now."
    : status.workersIdle
      ? "The firm's ingestion workers are not running. Nothing new will appear here until they resume."
      : "Currents will appear here when a real-world post crosses the firm's significance and relevance floors. Essays appear here when the firm releases them.";
  return (
    <section
      aria-label="No public publications yet"
      style={{
        background: "rgba(232, 225, 211, 0.035)",
        border: "1px solid var(--stroke)",
        borderRadius: "3px",
        margin: "0 0 2rem",
        padding: "1.1rem 1.2rem",
      }}
    >
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.62rem",
          letterSpacing: "0.2em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        Public commons
      </p>
      <p
        style={{
          color: "var(--parchment)",
          fontSize: "1rem",
          lineHeight: 1.55,
          margin: "0.4rem 0 0",
        }}
      >
        {headline}
      </p>
      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.94rem",
          lineHeight: 1.55,
          margin: "0.45rem 0 0",
        }}
      >
        {detail} Reach the firm at{" "}
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
  href?: string;
  linkLabel?: string;
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
        id={titleId}
        style={{
          color: "var(--parchment)",
          fontFamily: editorialTitleFont,
          fontSize: "clamp(1.22rem, 2vw, 1.48rem)",
          fontWeight: 500,
          letterSpacing: 0,
          lineHeight: 1.18,
          margin: 0,
        }}
      >
        {title}
      </h2>
      {href && linkLabel ? (
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
      ) : null}
    </div>
  );
}

function summarizeOpinion(opinion: PublicOpinion): string {
  if (opinion.abstention_reason) return opinion.abstention_reason;
  const body = stripMarkdown(opinion.body_markdown);
  return deriveExcerpt(body || opinion.event?.text || "", 140);
}

function stripMarkdown(text: string): string {
  return firmVoice(
    text
      .replace(/\[(?:\d+|C:[^\]\s]+)\]/g, "the firm")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/[#>_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim(),
  );
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
