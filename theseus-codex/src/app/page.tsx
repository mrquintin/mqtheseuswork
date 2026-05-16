import Link from "next/link";

import TransparencyFooter from "@/app/(home)/TransparencyFooter";
import ArticlesRail from "@/components/home/ArticlesRail";
import ConclusionsRail from "@/components/home/ConclusionsRail";
import LiveActivityRefresher from "@/components/home/LiveActivityRefresher";
import PublicAskBox from "@/components/PublicAskBox";
import PublicHeader from "@/components/PublicHeader";
import SubscribeForm from "@/components/SubscribeForm";
import {
  getTheseusContactEmail,
  theseusIdentity,
} from "@/content/theseusIdentity";
import {
  THESEUS_AXIOMS,
  THESEUS_IDENTITY_HEADINGS,
  THESEUS_ONE_PARAGRAPH,
  THESEUS_PIPELINE_ASCII,
  THESEUS_TAGLINE,
} from "@/lib/copy/identity";
import {
  listPublicAlgorithms,
  listInvocationsForAlgorithm,
  type PublicInvocationRow,
  type PublicAlgorithmRow,
} from "@/lib/algorithmsPublicApi";
import { getFounder } from "@/lib/auth";
import { getCurrentsHealth, listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { db } from "@/lib/db";
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
export const dynamic = "force-dynamic";

const editorialTitleFont = "'EB Garamond', 'Iowan Old Style', Georgia, serif";
const HOME_PREVIEW_TIMEOUT_MS = 2_000;
const HOME_SURFACE_TIMEOUT_MS = 1_500;
const PITCH_DECK_HREF =
  "https://github.com/mrquintin/mqtheseuswork/blob/main/docs/pitch/2026_philosopher_in_a_box/deck.pdf";

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

interface LiveInvocationCard {
  algorithm: PublicAlgorithmRow;
  invocation: PublicInvocationRow;
}

interface LatestMemoCard {
  id: string;
  slug: string | null;
  title: string;
  publishedAt: Date | null;
  tldr: string | null;
}

async function publicOrganizationId(): Promise<string> {
  const founder = await getFounder().catch(() => null);
  return (
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    ""
  );
}

async function liveInvocations(
  organizationId: string,
): Promise<LiveInvocationCard[]> {
  if (!organizationId) return [];
  try {
    const algorithms = await listPublicAlgorithms(organizationId, {
      status: "ACTIVE",
    });
    const candidates = algorithms.filter((a) => a.latestInvocationAt);
    candidates.sort(
      (a, b) =>
        (b.latestInvocationAt?.getTime() ?? 0) -
        (a.latestInvocationAt?.getTime() ?? 0),
    );
    const top = candidates.slice(0, 3);
    const cards: LiveInvocationCard[] = [];
    for (const algorithm of top) {
      const invocations = await listInvocationsForAlgorithm(algorithm.id, 1);
      const invocation = invocations[0];
      if (invocation) cards.push({ algorithm, invocation });
    }
    return cards;
  } catch (error) {
    console.error("homepage_live_invocations_failed", error);
    return [];
  }
}

async function latestPublishedMemo(): Promise<LatestMemoCard | null> {
  const memoApi = (db as unknown as {
    investmentMemo?: {
      findFirst: (args: unknown) => Promise<{
        id: string;
        slug: string | null;
        title: string | null;
        publishedAt: Date | null;
        payloadJson: string;
      } | null>;
    };
  }).investmentMemo;
  if (!memoApi) return null;
  try {
    const row = await memoApi.findFirst({
      where: { status: "PUBLIC" },
      orderBy: { publishedAt: "desc" },
      select: {
        id: true,
        slug: true,
        title: true,
        publishedAt: true,
        payloadJson: true,
      },
    });
    if (!row) return null;
    let tldr: string | null = null;
    try {
      const parsed = JSON.parse(row.payloadJson) as { tldr?: string };
      if (parsed?.tldr && typeof parsed.tldr === "string") tldr = parsed.tldr;
    } catch {
      tldr = null;
    }
    return {
      id: row.id,
      slug: row.slug,
      title: row.title ?? "Untitled memo",
      publishedAt: row.publishedAt,
      tldr,
    };
  } catch (error) {
    console.error("homepage_latest_memo_failed", error);
    return null;
  }
}

export default async function PublicHomePage() {
  const organizationId = await publicOrganizationId();
  const [currents, articles, conclusions, surfaceStatus, invocations, memo] =
    await Promise.all([
      latestCurrents(),
      latestArticles(),
      latestConclusions(),
      publicSurfaceStatus(),
      liveInvocations(organizationId),
      latestPublishedMemo(),
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
        <PhilosopherInABoxHero />
        <AxiomsCards />
        <MachineDiagram />
        <LiveActivityRail invocations={invocations} memo={memo} />

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

function PhilosopherInABoxHero() {
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
        {THESEUS_TAGLINE}
      </h1>
      <p
        style={{
          color: "var(--parchment)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "clamp(1.05rem, 1.7vw, 1.32rem)",
          lineHeight: 1.5,
          margin: "1.1rem 0 0",
          maxWidth: "48rem",
        }}
      >
        {THESEUS_ONE_PARAGRAPH}
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
            color: "var(--on-amber)",
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
        <a
          className="mono"
          href={PITCH_DECK_HREF}
          rel="noreferrer"
          target="_blank"
          style={{
            border: "1px solid var(--amber)",
            borderRadius: "3px",
            color: "var(--amber)",
            display: "inline-flex",
            fontSize: "0.68rem",
            letterSpacing: "0.2em",
            padding: "0.72rem 1rem",
            textDecoration: "none",
            textTransform: "uppercase",
          }}
        >
          {THESEUS_IDENTITY_HEADINGS.readTheDeck} →
        </a>
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
      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.9rem",
          lineHeight: 1.55,
          margin: "1.1rem 0 0",
          maxWidth: "42rem",
        }}
      >
        {theseusIdentity.homePage.commonsLine}
      </p>
    </section>
  );
}

function AxiomsCards() {
  return (
    <section
      aria-labelledby="home-axioms-title"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <h2
        className="mono"
        id="home-axioms-title"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.72rem",
          letterSpacing: "0.3em",
          margin: "0 0 0.9rem",
          textTransform: "uppercase",
        }}
      >
        {THESEUS_IDENTITY_HEADINGS.axiomsHeading}
      </h2>
      <div
        style={{
          display: "grid",
          gap: "0.85rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        }}
      >
        {THESEUS_AXIOMS.map((axiom) => (
          <article
            key={axiom.name}
            style={{
              background: "rgba(232, 225, 211, 0.035)",
              border: "1px solid rgba(232, 225, 211, 0.14)",
              borderRadius: "6px",
              padding: "1rem",
            }}
          >
            <h3
              style={{
                color: "var(--amber)",
                fontFamily: editorialTitleFont,
                fontSize: "1.2rem",
                fontWeight: 500,
                lineHeight: 1.22,
                margin: 0,
              }}
              data-h3-glyph="off"
            >
              {axiom.name}
            </h3>
            <p
              className="mono"
              style={{
                color: "var(--amber-dim)",
                fontSize: "0.62rem",
                letterSpacing: "0.18em",
                margin: "0.4rem 0 0",
                textTransform: "uppercase",
              }}
            >
              {axiom.summary}
            </p>
            <p
              style={{
                color: "var(--parchment-dim)",
                fontSize: "0.92rem",
                lineHeight: 1.5,
                margin: "0.7rem 0 0",
              }}
            >
              {axiom.elaboration}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function MachineDiagram() {
  return (
    <section
      aria-labelledby="home-machine-title"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <h2
        className="mono"
        id="home-machine-title"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.72rem",
          letterSpacing: "0.3em",
          margin: "0 0 0.9rem",
          textTransform: "uppercase",
        }}
      >
        {THESEUS_IDENTITY_HEADINGS.machineRail}
      </h2>
      <pre
        aria-label="Theseus pipeline diagram"
        className="mono"
        style={{
          background: "rgba(232, 225, 211, 0.035)",
          border: "1px solid rgba(232, 225, 211, 0.14)",
          borderRadius: "6px",
          color: "var(--parchment)",
          fontSize: "0.82rem",
          lineHeight: 1.55,
          margin: 0,
          overflowX: "auto",
          padding: "1.1rem 1.2rem",
          whiteSpace: "pre",
        }}
      >
{THESEUS_PIPELINE_ASCII}
      </pre>
      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.9rem",
          lineHeight: 1.55,
          margin: "0.85rem 0 0",
          maxWidth: "42rem",
        }}
      >
        Inputs are the curated corpus and live observations. The
        synthesizer extracts principles. Algorithms apply those
        principles to whatever the world is doing this morning. When the
        prediction is sharp enough, the portfolio agent places the bet.
      </p>
    </section>
  );
}

function LiveActivityRail({
  invocations,
  memo,
}: {
  invocations: LiveInvocationCard[];
  memo: LatestMemoCard | null;
}) {
  const empty = invocations.length === 0 && !memo;
  return (
    <section
      aria-labelledby="home-live-title"
      data-testid="homepage-live-activity"
      style={{
        borderBottom: "1px solid var(--stroke)",
        marginBottom: "2rem",
        paddingBottom: "1.75rem",
      }}
    >
      <LiveActivityRefresher />
      <div
        style={{
          alignItems: "baseline",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          justifyContent: "space-between",
          marginBottom: "0.85rem",
        }}
      >
        <h2
          className="mono"
          id="home-live-title"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.72rem",
            letterSpacing: "0.3em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          {THESEUS_IDENTITY_HEADINGS.liveActivity}
        </h2>
        <Link
          className="mono"
          href="/algorithms"
          style={{
            color: "var(--amber)",
            fontSize: "0.62rem",
            letterSpacing: "0.2em",
            textDecoration: "none",
            textTransform: "uppercase",
          }}
        >
          All algorithms →
        </Link>
      </div>
      {empty ? (
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
          No algorithm has fired and no memo has been published yet. The
          machine is quiet.
        </p>
      ) : (
        <div
          style={{
            display: "grid",
            gap: "0.85rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          }}
        >
          {invocations.map((card) => (
            <Link
              key={card.invocation.id}
              data-testid="homepage-live-invocation"
              href={`/algorithms/${encodeURIComponent(
                card.algorithm.id,
              )}/invocations/${encodeURIComponent(card.invocation.id)}`}
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
              <p
                className="mono"
                style={{
                  color: "var(--amber-dim)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.18em",
                  margin: 0,
                  textTransform: "uppercase",
                }}
              >
                Algorithm · {formatTimestamp(card.invocation.invokedAt)}
              </p>
              <h3
                style={{
                  color: "var(--amber)",
                  fontFamily: editorialTitleFont,
                  fontSize: "1.18rem",
                  fontWeight: 500,
                  lineHeight: 1.22,
                  margin: "0.35rem 0 0",
                }}
                data-h3-glyph="off"
              >
                {card.algorithm.name}
              </h3>
              <p
                style={{
                  color: "var(--parchment-dim)",
                  fontSize: "0.9rem",
                  lineHeight: 1.5,
                  margin: "0.55rem 0 0",
                }}
              >
                {summarizeInvocation(card.invocation)}
              </p>
              {card.invocation.betImplied ? (
                <p
                  className="mono"
                  style={{
                    color: "var(--amber)",
                    fontSize: "0.62rem",
                    letterSpacing: "0.16em",
                    margin: "0.65rem 0 0",
                    textTransform: "uppercase",
                  }}
                >
                  bet · {card.invocation.betImplied.direction}{" "}
                  {card.invocation.betImplied.instrument}
                </p>
              ) : null}
            </Link>
          ))}
          {memo ? (
            <Link
              key={memo.id}
              data-testid="homepage-live-memo"
              href={`/memos/${memo.slug || memo.id}`}
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
              <p
                className="mono"
                style={{
                  color: "var(--amber-dim)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.18em",
                  margin: 0,
                  textTransform: "uppercase",
                }}
              >
                Memo · {memo.publishedAt ? formatTimestamp(memo.publishedAt) : "Unpublished"}
              </p>
              <h3
                style={{
                  color: "var(--amber)",
                  fontFamily: editorialTitleFont,
                  fontSize: "1.18rem",
                  fontWeight: 500,
                  lineHeight: 1.22,
                  margin: "0.35rem 0 0",
                }}
                data-h3-glyph="off"
              >
                {memo.title}
              </h3>
              {memo.tldr ? (
                <p
                  style={{
                    color: "var(--parchment-dim)",
                    fontSize: "0.9rem",
                    lineHeight: 1.5,
                    margin: "0.55rem 0 0",
                  }}
                >
                  {memo.tldr}
                </p>
              ) : null}
            </Link>
          ) : null}
        </div>
      )}
    </section>
  );
}

function summarizeInvocation(invocation: PublicInvocationRow): string {
  const reasoning = invocation.reasoningTrace
    .filter((step) => typeof step === "string" && step.trim().length > 0)
    .join(" ");
  if (reasoning) return deriveExcerpt(reasoning, 160);
  const output = invocation.derivedOutput;
  if (output && typeof output === "object") {
    const summary = (output as Record<string, unknown>).summary;
    if (typeof summary === "string" && summary.trim()) {
      return deriveExcerpt(summary, 160);
    }
  }
  return "Invocation recorded; full reasoning available on the algorithm page.";
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
        title="The firm thinking in public — Currents"
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
    ? "The firm in public"
    : "Public surfaces (paused)";
  const currentsBody = !status.reachable
    ? "Live X posts and other signals, with the firm's principles applied in response. Publishing is paused."
    : status.workersIdle
      ? "Live X posts and other signals, with the firm's principles applied in response. Ingestion workers are not running."
      : "Live X posts and other signals — the firm's principles applied to the day, in public.";
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
          body="Prediction-market forecasts — the same algorithms applied to questions with a settlement date. Calibration is public."
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
        style={{
          color: "var(--amber)",
          textDecoration: "underline",
          textDecorationThickness: "0.08em",
          textUnderlineOffset: "0.16em",
        }}
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
      : "Currents will appear here when a real-world post crosses the firm's significance and relevance floors. Memos appear here when the firm releases them.";
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
          style={{
            color: "var(--amber)",
            textDecoration: "underline",
            textDecorationThickness: "0.08em",
            textUnderlineOffset: "0.16em",
          }}
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

function formatTimestamp(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
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
