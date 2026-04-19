import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import SculptureBackdrop from "@/components/SculptureBackdrop";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";

/**
 * Public blog index — the Codex's front door.
 *
 * The Codex used to be entirely private: `/` rendered the Gate and
 * there was no public surface. That made the institution invisible to
 * anyone who hadn't already been told what it was. This page replaces
 * the private gate with a reading-focused blog index that lists every
 * Upload the founders have chosen to publish.
 *
 * What "published" means: `Upload.publishedAt IS NOT NULL` AND
 * `Upload.slug IS NOT NULL`. Both flags are flipped in the same
 * transaction when a founder hits the publish toggle (upload form or
 * dashboard); unpublishing just clears both. The Codex itself
 * (conclusions, contradictions, review queue, interlocutor) remains
 * private — `/dashboard` and everything under `(authed)/` are still
 * protected by middleware.
 *
 * Authenticated visitors get a small persistent link back to
 * `/dashboard` in the top-right corner. Unauthenticated visitors see
 * a modest "Founder login →" link instead.
 *
 * Rendering: RSC-direct Prisma query. Posts are small (one row per
 * published upload), so we don't bother with pagination in v1 —
 * cap at 50 and add pagination when the corpus justifies it.
 */

export const dynamic = "force-dynamic";
export const revalidate = 60; // still re-fetch every minute for freshness

export default async function PublicBlogIndex() {
  const founder = await getFounder();

  const posts = await db.upload.findMany({
    where: {
      publishedAt: { not: null },
      slug: { not: null },
      // Soft-deleted posts disappear from the public surface the same
      // moment the owner (or an accepted DeletionRequest) flips the flag.
      deletedAt: null,
      // Belt-and-suspenders: the /api/upload and /api/publish endpoints
      // already reject private+published combinations, but filtering
      // here means a direct DB write (migration back-fill, admin tool)
      // that left a private row flagged as published still wouldn't
      // leak it onto the public index.
      visibility: { not: "private" },
    },
    orderBy: { publishedAt: "desc" },
    take: 50,
    select: {
      id: true,
      slug: true,
      title: true,
      description: true,
      blogExcerpt: true,
      authorBio: true,
      textContent: true,
      publishedAt: true,
      createdAt: true,
      audioUrl: true,
      audioDurationSec: true,
      founder: { select: { name: true } },
      organization: { select: { slug: true } },
    },
  });

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <PublicHeader authed={Boolean(founder)} />

      {/* Hero section — minimal, just a wordmark + thesis line. */}
      <section
        style={{
          position: "relative",
          overflow: "hidden",
          minHeight: "42vh",
          padding: "3.5rem 2rem 2rem",
          textAlign: "center",
        }}
      >
        <SculptureBackdrop
          src="/sculptures/discobolus-alt.mesh.bin"
          side="right"
          opacity={0.42}
          widthVW={50}
        />
        <div
          style={{
            position: "relative",
            zIndex: 1,
            maxWidth: "44rem",
            margin: "0 auto",
          }}
        >
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "clamp(2.5rem, 6vw, 4.25rem)",
              letterSpacing: "0.18em",
              color: "var(--amber)",
              textShadow: "var(--glow-lg)",
              margin: 0,
              fontWeight: 700,
            }}
          >
            THESEUS
          </h1>
          <p
            className="mono"
            style={{
              fontSize: "0.78rem",
              letterSpacing: "0.3em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              marginTop: "0.5rem",
              marginBottom: "1rem",
            }}
          >
            Codex · Public Ledger
          </p>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1.18rem",
              color: "var(--parchment)",
              maxWidth: "32em",
              margin: "0 auto 0.4rem",
              lineHeight: 1.55,
            }}
          >
            In consilio lucem.{" "}
            <span style={{ opacity: 0.55 }}>·</span> Light in the deliberation.
          </p>
          <p
            style={{
              fontSize: "0.95rem",
              color: "var(--parchment-dim)",
              maxWidth: "32em",
              margin: "0.5rem auto 0",
              lineHeight: 1.55,
            }}
          >
            Sessions, essays, and transcripts that the firm has chosen to make
            public. The instrument itself — private deliberation,
            contradiction detection, open questions — sits behind the gate.
          </p>
        </div>
      </section>

      {/* Blog index ─────────────────────────────────────────────── */}
      <section
        style={{
          position: "relative",
          maxWidth: "800px",
          margin: "0 auto",
          padding: "1rem 2rem 6rem",
        }}
      >
        <h2
          className="mono"
          style={{
            fontSize: "0.72rem",
            letterSpacing: "0.3em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            margin: "0 0 1.5rem",
            borderBottom: "1px solid var(--stroke)",
            paddingBottom: "0.65rem",
          }}
        >
          Acta · Publications
        </h2>

        {posts.length === 0 ? (
          <div
            className="ascii-frame"
            data-label="TABULA RASA"
            style={{ padding: "2rem 1.5rem", textAlign: "center" }}
          >
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                color: "var(--parchment)",
                fontSize: "1.1rem",
                margin: "0 0 0.35rem",
              }}
            >
              Adhuc nihil publicum.
            </p>
            <p
              style={{
                color: "var(--parchment-dim)",
                fontSize: "0.9rem",
                margin: 0,
              }}
            >
              Nothing has been published yet. Founders, head to{" "}
              <Link
                href="/upload"
                style={{
                  color: "var(--amber)",
                  textDecoration: "underline",
                }}
              >
                /upload
              </Link>{" "}
              and tick <em>Publish as blog post</em>.
            </p>
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "1.5rem",
            }}
          >
            {posts.map((p) => (
              <PostCard
                key={p.id}
                slug={p.slug!}
                title={p.title}
                byline={p.authorBio || p.founder.name}
                publishedAt={p.publishedAt!}
                excerpt={
                  p.blogExcerpt ||
                  deriveExcerpt(p.description || p.textContent || "")
                }
                isAudio={Boolean(p.audioUrl)}
                audioDurationSec={p.audioDurationSec || null}
              />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function PostCard({
  slug,
  title,
  byline,
  publishedAt,
  excerpt,
  isAudio,
  audioDurationSec,
}: {
  slug: string;
  title: string;
  byline: string;
  publishedAt: Date;
  excerpt: string;
  isAudio: boolean;
  audioDurationSec: number | null;
}) {
  const date = new Date(publishedAt).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const durationLabel = (() => {
    if (!audioDurationSec || audioDurationSec <= 0) return "";
    const total = Math.floor(audioDurationSec);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const mm = m.toString().padStart(2, "0");
    const ss = s.toString().padStart(2, "0");
    return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
  })();
  return (
    <article
      className="portal-card"
      style={{
        padding: "1.5rem 1.75rem",
        transition: "border-color 0.2s ease, transform 0.2s ease",
      }}
    >
      <Link
        href={`/post/${slug}`}
        style={{
          textDecoration: "none",
          color: "inherit",
          display: "block",
        }}
      >
        <p
          className="mono"
          style={{
            fontSize: "0.6rem",
            letterSpacing: "0.25em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            margin: "0 0 0.4rem",
            display: "flex",
            alignItems: "center",
            gap: "0.55rem",
            flexWrap: "wrap",
          }}
        >
          <span>
            {date} · {byline}
          </span>
          {isAudio ? (
            <span
              style={{
                color: "var(--amber)",
                border: "1px solid var(--amber)",
                padding: "0.12rem 0.45rem",
                borderRadius: "2px",
                fontSize: "0.56rem",
                letterSpacing: "0.22em",
              }}
              title="Audio episode — click through to listen with the transcript"
            >
              ◀︎ Listen{durationLabel ? ` · ${durationLabel}` : ""}
            </span>
          ) : null}
        </p>
        <h3
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "1.45rem",
            letterSpacing: "0.04em",
            color: "var(--amber)",
            margin: "0 0 0.6rem",
            fontWeight: 600,
          }}
        >
          {title}
        </h3>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "var(--parchment)",
            fontSize: "1rem",
            lineHeight: 1.55,
            margin: 0,
          }}
        >
          {excerpt}
        </p>
        <span
          className="mono"
          style={{
            display: "inline-block",
            fontSize: "0.62rem",
            letterSpacing: "0.25em",
            textTransform: "uppercase",
            color: "var(--amber)",
            marginTop: "0.9rem",
          }}
        >
          {isAudio ? "Lege et Audi → Read & Listen" : "Lege → Read"}
        </span>
      </Link>
    </article>
  );
}

/**
 * Produce a readable one-paragraph excerpt from a long body. We look
 * for the first paragraph break; failing that, cut at ~280 chars on
 * a word boundary so we don't slice a sentence mid-word.
 */
function deriveExcerpt(text: string): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "(no preview available)";
  if (cleaned.length <= 300) return cleaned;
  const cut = cleaned.slice(0, 300);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > 200 ? cut.slice(0, lastSpace) : cut) + "…";
}
