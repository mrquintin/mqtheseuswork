import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import PublicHeader from "@/components/PublicHeader";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";

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
      visibility: { not: "private" },
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
    // a retracted post behaves the same as an unknown slug. Private
    // rows 404 too — visibility=private can't coexist with a publish
    // state in the normal code path, but we enforce it here anyway.
    where: {
      slug,
      publishedAt: { not: null },
      deletedAt: null,
      visibility: { not: "private" },
    },
    select: {
      id: true,
      title: true,
      description: true,
      authorBio: true,
      blogExcerpt: true,
      textContent: true,
      publishedAt: true,
      sourceType: true,
      founder: { select: { name: true } },
    },
  });

  if (!post) {
    notFound();
  }

  const date = new Date(post.publishedAt!).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const body = post.textContent || "";
  const paragraphs = splitParagraphs(body);

  return (
    <main style={{ minHeight: "100vh" }}>
      <PublicHeader authed={Boolean(founder)} />

      <article
        style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: "3rem 1.75rem 5rem",
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
            marginBottom: "1.5rem",
            display: "inline-block",
          }}
        >
          ← Back to index
        </Link>

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
            {date} · {post.authorBio || post.founder.name}
            {post.sourceType && post.sourceType !== "written"
              ? ` · ${post.sourceType}`
              : ""}
          </p>
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "clamp(2rem, 5vw, 3rem)",
              letterSpacing: "0.08em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
              lineHeight: 1.25,
              fontWeight: 700,
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

        <div
          className="post-body"
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "var(--parchment)",
            fontSize: "1.1rem",
            lineHeight: 1.7,
          }}
        >
          {paragraphs.length === 0 ? (
            <p style={{ color: "var(--parchment-dim)", fontStyle: "italic" }}>
              (This post has no body text. If it was ingested from audio,
              the transcript may still be processing.)
            </p>
          ) : (
            paragraphs.map((p, i) => (
              <p key={i} style={{ margin: "0 0 1.1rem" }}>
                {p}
              </p>
            ))
          )}
        </div>

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
            {post.authorBio || post.founder.name}
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

/**
 * Split prose into paragraphs. A "paragraph" is a block separated by
 * one-or-more blank lines. We also soft-split runs of plain single-line
 * content into paragraphs if they're long enough to warrant breaks —
 * but only when there are ZERO paragraph-break signals, so we don't
 * double-split well-formed text.
 */
function splitParagraphs(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  // Primary split: double-newline paragraph breaks (the normal case).
  const blocks = trimmed.split(/\n\s*\n+/);
  if (blocks.length > 1) {
    return blocks
      .map((b) => b.trim().replace(/\s+/g, " "))
      .filter(Boolean);
  }
  // Fallback: treat every 3–4 sentences as a paragraph so a long
  // one-line dump doesn't become an unreadable wall. 400 chars is a
  // reasonable paragraph in EB Garamond at 1.1rem.
  const SENT = /([^.!?]+[.!?]+)\s+(?=[A-Z])/g;
  const sentences = trimmed.replace(SENT, "$1\n").split(/\n/);
  const out: string[] = [];
  let buf = "";
  for (const s of sentences) {
    buf = buf ? buf + " " + s.trim() : s.trim();
    if (buf.length >= 400) {
      out.push(buf);
      buf = "";
    }
  }
  if (buf) out.push(buf);
  return out.length > 0 ? out : [trimmed];
}
