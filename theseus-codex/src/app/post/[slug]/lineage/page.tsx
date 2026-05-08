import Link from "next/link";
import { notFound } from "next/navigation";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { assembleLineage, filterPublic, type Lineage } from "@/lib/lineage";

export const dynamic = "force-dynamic";
export const revalidate = 60;

/**
 * Public lineage page for a published post.
 *
 * The visible content is exactly `filterPublic(lineage)` — sources,
 * supporting claims, methodology (when published), the conclusion, and
 * any published versions. Private nodes (drift, revisions, peer review,
 * unpublished methodology) are absent from the rendered list AND from
 * the JSON payload of the API endpoint that backs it; readers cannot
 * tell whether private steps exist.
 */

type PageProps = { params: Promise<{ slug: string }> };

const KIND_LABELS: Record<string, string> = {
  source: "Source",
  claim: "Claim",
  methodology: "Methodology",
  method_invocation: "Method",
  conclusion: "Conclusion",
  publication: "Published",
  citation: "Citation",
};

export default async function PublicLineagePage({ params }: PageProps) {
  const { slug } = await params;
  const founder = await getFounder();

  // Resolve the slug → published conclusion → conclusion id. We accept
  // the slug from either the Upload (post slug) or the PublishedConclusion
  // record so /post/<slug>/lineage works for both routes.
  const upload = await db.upload.findFirst({
    where: { slug, publishedAt: { not: null }, deletedAt: null, visibility: "org" },
    select: { id: true, organizationId: true, title: true },
  });
  const published = upload
    ? await db.publishedConclusion.findFirst({
        where: {
          organizationId: upload.organizationId,
          OR: [
            { sourceConclusionId: upload.id },
            { slug: upload.id },
            { slug },
          ],
        },
        orderBy: { publishedAt: "desc" },
        select: {
          organizationId: true,
          sourceConclusionId: true,
          slug: true,
          version: true,
        },
      })
    : await db.publishedConclusion.findFirst({
        where: { slug },
        orderBy: { publishedAt: "desc" },
        select: {
          organizationId: true,
          sourceConclusionId: true,
          slug: true,
          version: true,
        },
      });

  if (!published) {
    notFound();
  }

  let lineage: Lineage;
  try {
    const full = await assembleLineage({
      conclusionId: published.sourceConclusionId,
      organizationId: published.organizationId,
    });
    lineage = filterPublic(full);
  } catch {
    notFound();
  }

  return (
    <main style={{ minHeight: "100vh" }}>
      <PublicHeader authed={Boolean(founder)} />

      <article
        style={{
          maxWidth: "780px",
          margin: "0 auto",
          padding: "3rem 1.75rem 5rem",
        }}
      >
        <Link
          href={`/post/${slug}`}
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
          ← Back to post
        </Link>

        <header style={{ marginBottom: "2rem" }}>
          <p
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              margin: "0 0 0.6rem",
            }}
          >
            Public lineage
          </p>
          <h1
            style={{
              fontFamily: "'EB Garamond', Georgia, serif",
              fontSize: "clamp(1.7rem, 4vw, 2.4rem)",
              color: "var(--amber)",
              margin: 0,
              fontWeight: 600,
              letterSpacing: "-0.005em",
            }}
          >
            How this conclusion was reached
          </h1>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              color: "var(--parchment-dim)",
              margin: "0.75rem 0 0",
            }}
          >
            Source documents, supporting claims, methodology, and public
            revisions — in causal order.
          </p>
        </header>

        {lineage.nodes.length === 0 ? (
          <p
            style={{
              color: "var(--parchment-dim)",
              fontStyle: "italic",
            }}
          >
            No public lineage steps have been recorded for this conclusion.
          </p>
        ) : (
          <ol
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              borderLeft: "1px solid var(--stroke)",
            }}
          >
            {lineage.nodes.map((n) => (
              <li
                key={n.id}
                style={{
                  position: "relative",
                  paddingLeft: "1.25rem",
                  paddingTop: "0.6rem",
                  paddingBottom: "0.9rem",
                }}
              >
                <span
                  aria-hidden
                  style={{
                    position: "absolute",
                    left: -4,
                    top: "0.85rem",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "var(--amber)",
                  }}
                />
                <div
                  style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}
                >
                  <span
                    className="mono"
                    style={{
                      fontSize: "0.55rem",
                      letterSpacing: "0.2em",
                      textTransform: "uppercase",
                      color: "var(--amber-dim)",
                      minWidth: "9ch",
                    }}
                  >
                    {KIND_LABELS[n.kind] ?? n.kind}
                  </span>
                  <span
                    style={{
                      fontFamily: "'EB Garamond', serif",
                      fontSize: "1.05rem",
                      color: "var(--parchment)",
                    }}
                  >
                    {n.recordUrl ? (
                      <Link
                        href={n.recordUrl}
                        style={{ color: "var(--amber)", textDecoration: "none" }}
                      >
                        {n.label}
                      </Link>
                    ) : (
                      n.label
                    )}
                  </span>
                </div>
                <div
                  className="mono"
                  style={{
                    fontSize: "0.6rem",
                    color: "var(--parchment-dim)",
                    marginTop: "0.2rem",
                  }}
                >
                  {new Date(n.timestamp).toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </div>
                {n.summary ? (
                  <p
                    style={{
                      fontFamily: "'EB Garamond', serif",
                      margin: "0.5rem 0 0",
                      color: "var(--parchment)",
                      fontSize: "0.95rem",
                      lineHeight: 1.55,
                    }}
                  >
                    {n.summary}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </article>
    </main>
  );
}
