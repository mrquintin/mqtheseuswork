import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import ArticleRenderer from "@/components/article/ArticleRenderer";
import PrintButton from "@/components/PrintButton";
import PrintEndnotes, { type PrintEndnoteSource } from "@/components/PrintEndnotes";
import PrintMetadataBlock from "@/components/PrintMetadataBlock";
import PublicHeader from "@/components/PublicHeader";
import ReaderResponses from "./ReaderResponses";
import RespondCallout from "@/components/RespondCallout";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";
import {
  parsePublicationPayload,
  type PublishedConclusion,
} from "@/lib/conclusionsRead";
import { founderDisplayName } from "@/lib/founderDisplay";
import { getPublicSiteUrl } from "@/lib/site";

/**
 * Public blog post — individual article page.
 *
 * Renders any Upload with `publishedAt IS NOT NULL AND slug = :slug`.
 * Unpublished uploads 404 (instead of leaking existence via an auth
 * redirect). Because the same underlying Upload row powers the private
 * founder workspace, no data is duplicated — the Codex's blog is
 * literally "a published view of the same artifact".
 *
 * Rendering philosophy: we aim for long-form legibility. The body is
 * the `textContent` (plain prose from the extractor), wrapped at
 * ~70 characters via CSS max-width, set in EB Garamond for the
 * reading voice. No distracting sidebars. A small "← Back" link at
 * the top. The author byline + date sit just under the title.
 *
 * If the upload has a `description` that's distinct from the extracted
 * textContent (e.g. a founder wrote a short intro), we use it as a
 * pull-quote lede; otherwise the body begins immediately.
 */

export const dynamic = "force-dynamic";
export const revalidate = 60;

type PageProps = { params: Promise<{ slug: string }> };

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const post = await db.upload.findFirst({
    where: {
      slug,
      publishedAt: { not: null },
      deletedAt: null,
      // Only "org"-visibility uploads appear on the public blog. See
      // app/page.tsx for the symmetric rule on the index.
      visibility: "org",
    },
    select: { title: true, blogExcerpt: true, description: true, textContent: true },
  });
  if (!post) return { title: "Post not found · Theseus Codex" };
  const desc = post.blogExcerpt || post.description || post.textContent || "";
  return {
    title: `${post.title} · Theseus Codex`,
    description: desc.slice(0, 160).replace(/\s+/g, " "),
    openGraph: {
      title: post.title,
      description: desc.slice(0, 240).replace(/\s+/g, " "),
      type: "article",
    },
  };
}

export default async function PostPage({ params }: PageProps) {
  const { slug } = await params;
  const founder = await getFounder();

  const post = await db.upload.findFirst({
    // Soft-deleted posts 404 rather than render, so a shared link for
    // a retracted post behaves the same as an unknown slug. The
    // `visibility: "org"` filter excludes both "private" (uploader-
    // only) and "semi-private" (firm-only) rows; by construction
    // these shouldn't coexist with a publish state, but enforcing it
    // here guarantees that even a stale slug cached in a post's URL
    // history can't pull the content back onto the public blog.
    where: {
      slug,
      publishedAt: { not: null },
      deletedAt: null,
      visibility: "org",
    },
    select: {
      id: true,
      organizationId: true,
      title: true,
      slug: true,
      description: true,
      authorBio: true,
      blogExcerpt: true,
      textContent: true,
      publishedAt: true,
      sourceType: true,
      // New podcast fields — when audioUrl is set we render an
      // <audio controls> player at the top of the post and label
      // the card/byline line with the episode duration.
      audioUrl: true,
      audioDurationSec: true,
      founder: { select: { displayName: true, name: true, username: true } },
    },
  });

  if (!post) {
    notFound();
  }

  const responseTarget = await responseTargetForPost(post, slug);

  const date = new Date(post.publishedAt!).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const body = post.textContent || "";
  const byline = post.authorBio || founderDisplayName(post.founder);

  const canonicalUrl = `${getPublicSiteUrl()}/post/${encodeURIComponent(post.slug ?? slug)}`;
  const signatureFingerprint = await loadSignatureFingerprint(post.slug ?? slug);
  const printEndnotes = postPrintEndnotes(post);

  return (
    <main style={{ minHeight: "100vh" }}>
      <PublicHeader authed={Boolean(founder)} />

      <PrintMetadataBlock
        title={post.title}
        byline={byline}
        publishedAt={new Date(post.publishedAt!).toISOString()}
        methodology={post.sourceType ?? null}
        canonicalUrl={canonicalUrl}
        signatureFingerprint={signatureFingerprint}
      />

      <article
        className="public-post-article"
        data-testid="post-article"
        style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: "3rem 1.75rem 5rem",
        }}
      >
        <div
          className="no-print"
          style={{
            alignItems: "center",
            display: "flex",
            justifyContent: "space-between",
            gap: "1rem",
            marginBottom: "1.5rem",
          }}
        >
          <Link
            href="/"
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              textDecoration: "none",
              display: "inline-block",
            }}
          >
            ← Back to index
          </Link>
          <PrintButton
            className="mono"
            style={{
              background: "transparent",
              border: "1px solid var(--amber-dim)",
              borderRadius: "4px",
              color: "var(--amber)",
              cursor: "pointer",
              fontSize: "0.6rem",
              letterSpacing: "0.22em",
              padding: "0.35rem 0.7rem",
              textTransform: "uppercase",
            }}
          />
        </div>

        <RespondCallout conclusions={[responseTarget]} />

        <header style={{ marginBottom: "2rem" }}>
          <p
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              margin: "0 0 0.8rem",
            }}
          >
            {date} · {byline}
            {post.sourceType && post.sourceType !== "written"
              ? ` · ${post.sourceType}`
              : ""}
            {post.audioUrl ? (
              <span style={{ color: "var(--amber)" }}>
                {" · "}
                Episode
                {post.audioDurationSec
                  ? ` · ${formatDuration(post.audioDurationSec)}`
                  : ""}
              </span>
            ) : null}
          </p>
          <h1
            style={{
              fontFamily: "'EB Garamond', 'Iowan Old Style', Georgia, serif",
              fontSize: "clamp(1.85rem, 4.4vw, 2.6rem)",
              letterSpacing: "-0.005em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
              lineHeight: 1.18,
              fontWeight: 600,
            }}
          >
            {post.title}
          </h1>
          {post.description ? (
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                fontSize: "1.18rem",
                color: "var(--parchment)",
                lineHeight: 1.55,
                margin: "1.25rem 0 0",
                borderLeft: "2px solid var(--amber-dim)",
                paddingLeft: "1rem",
              }}
            >
              {post.description}
            </p>
          ) : null}
        </header>

        {post.audioUrl ? (
          <section
            className="ascii-frame"
            data-label="AUDIO · EPISODE"
            style={{
              margin: "0 0 2rem",
              padding: "1.25rem 1.25rem 1rem",
              background:
                "linear-gradient(180deg, rgba(212,160,23,0.08), rgba(212,160,23,0.02))",
            }}
          >
            <p
              className="mono"
              style={{
                fontSize: "0.6rem",
                letterSpacing: "0.26em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                margin: "0 0 0.6rem",
              }}
            >
              ◀︎ Listen {post.audioDurationSec
                ? `· ${formatDuration(post.audioDurationSec)}`
                : ""}
            </p>
            {/*
              Native HTML5 audio player — zero JS dependency, works on
              every modern browser + iOS Safari. We skip `preload="auto"`
              so the 30MB podcast file doesn't download until the
              visitor actually hits play.
            */}
            <audio
              controls
              preload="metadata"
              style={{ width: "100%" }}
              aria-label={`Audio for ${post.title}`}
            >
              <source src={post.audioUrl} />
              Your browser doesn&rsquo;t support HTML5 audio.{" "}
              <a
                href={post.audioUrl}
                style={{ color: "var(--amber)" }}
                target="_blank"
                rel="noopener noreferrer"
              >
                Download the file
              </a>
              .
            </audio>
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                fontSize: "0.9rem",
                color: "var(--parchment-dim)",
                margin: "0.75rem 0 0",
              }}
            >
              Transcript below — scroll to read, or hit play to listen.
            </p>
          </section>
        ) : null}

        {body.trim() ? (
          <ArticleRenderer
            body={body}
            className="post-body public-article-body"
            testId="post-article-body"
          />
        ) : (
          <div
            className="post-body public-article-body"
            style={{
              fontFamily: "'EB Garamond', serif",
              color: "var(--parchment)",
              fontSize: "1.1rem",
              lineHeight: 1.7,
            }}
          >
            <p style={{ color: "var(--parchment-dim)", fontStyle: "italic" }}>
              (This post has no body text. If it was ingested from audio,
              the transcript may still be processing.)
            </p>
          </div>
        )}

        <PrintEndnotes sources={printEndnotes} />

        <ReaderResponses
          organizationId={post.organizationId}
          postId={post.id}
          postSlug={post.slug ?? slug}
        />

        <footer
          style={{
            marginTop: "3rem",
            paddingTop: "1.2rem",
            borderTop: "1px solid var(--stroke)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <p
            className="mono"
            style={{
              fontSize: "0.62rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              margin: 0,
            }}
          >
            {byline}
            <span style={{ opacity: 0.5 }}> · Theseus Codex</span>
          </p>
          <Link
            href="/"
            className="mono"
            style={{
              fontSize: "0.62rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--amber)",
              textDecoration: "none",
            }}
          >
            More from the Codex →
          </Link>
        </footer>
      </article>
    </main>
  );
}

type PostResponseTargetInput = {
  id: string;
  organizationId: string;
  title: string;
  slug: string | null;
  publishedAt: Date | null;
};

type PublishedConclusionDbRow = {
  id: string;
  kind: string;
  slug: string;
  version: number;
  sourceConclusionId: string;
  publishedAt: Date | string;
  doi: string;
  zenodoRecordId: string;
  discountedConfidence: number;
  statedConfidence: number;
  calibrationDiscountReason: string;
  payloadJson: string;
};

async function responseTargetForPost(
  post: PostResponseTargetInput,
  routeSlug: string,
): Promise<PublishedConclusion> {
  const published = await db.publishedConclusion.findFirst({
    where: {
      organizationId: post.organizationId,
      OR: [
        { id: post.id },
        { sourceConclusionId: post.id },
        { sourceConclusionId: `article:${post.id}` },
        { slug: post.slug ?? routeSlug },
      ],
    },
    orderBy: { publishedAt: "desc" },
    select: {
      id: true,
      kind: true,
      slug: true,
      version: true,
      sourceConclusionId: true,
      publishedAt: true,
      doi: true,
      zenodoRecordId: true,
      discountedConfidence: true,
      statedConfidence: true,
      calibrationDiscountReason: true,
      payloadJson: true,
    },
  });

  return published
    ? publishedConclusionFromRow(published as PublishedConclusionDbRow)
    : fallbackPostResponseTarget(post, routeSlug);
}

function publishedConclusionFromRow(row: PublishedConclusionDbRow): PublishedConclusion {
  return {
    id: row.id,
    kind: row.kind,
    slug: row.slug,
    version: row.version,
    sourceConclusionId: row.sourceConclusionId,
    publishedAt:
      row.publishedAt instanceof Date
        ? row.publishedAt.toISOString()
        : new Date(row.publishedAt).toISOString(),
    doi: row.doi,
    zenodoRecordId: row.zenodoRecordId,
    discountedConfidence: row.discountedConfidence,
    statedConfidence: row.statedConfidence,
    calibrationDiscountReason: row.calibrationDiscountReason,
    payload: parsePublicationPayload(row),
  };
}

function fallbackPostResponseTarget(
  post: PostResponseTargetInput,
  routeSlug: string,
): PublishedConclusion {
  const publishedAt = post.publishedAt
    ? post.publishedAt.toISOString()
    : new Date().toISOString();
  const slug = post.slug ?? routeSlug;

  return {
    id: post.id,
    kind: "POST",
    slug,
    version: 1,
    sourceConclusionId: `post:${post.id}`,
    publishedAt,
    doi: "",
    zenodoRecordId: "",
    discountedConfidence: 0,
    statedConfidence: 0,
    calibrationDiscountReason: "",
    payload: {
      schema: "theseus.publicConclusion.v1",
      conclusionText: `Respond to this post: ${post.title}`,
      rationale: "",
      topicHint: "",
      evidenceSummary: "",
      exitConditions: [],
      strongestObjection: { objection: "", firmAnswer: "" },
      openQuestionsAdjacent: [],
      voiceComparisons: [],
      methodology: {
        schema: "theseus.methodology.v1",
        reviewerNarrative: "",
        profiles: [],
      },
      timeline: [],
      whatWouldChangeOurMind: [],
      citations: [],
    },
  };
}

async function loadSignatureFingerprint(slug: string): Promise<string | null> {
  try {
    const sig = await db.publicationSignature.findFirst({
      where: { slug },
      orderBy: { version: "desc" },
      select: { keyFingerprint: true },
    });
    return sig?.keyFingerprint ?? null;
  } catch {
    return null;
  }
}

function postPrintEndnotes(post: {
  audioUrl: string | null;
  sourceType: string | null;
}): PrintEndnoteSource[] {
  const out: PrintEndnoteSource[] = [];
  // Posts don't carry inline citation popovers (their citations land
  // in the published-conclusion view), but if the post has an audio
  // source we surface the audio URL as the one externally-checkable
  // anchor a printed reader can hit.
  if (post.audioUrl) {
    out.push({
      label: "A1",
      title: "Audio source",
      kind: post.sourceType ?? "audio",
      url: post.audioUrl,
    });
  }
  return out;
}

/**
 * Format a duration in seconds as `MM:SS` or `H:MM:SS` — what a podcast
 * app would show next to the play button.
 */
function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = m.toString().padStart(2, "0");
  const ss = s.toString().padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

