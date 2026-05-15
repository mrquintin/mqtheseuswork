import Link from "next/link";
import { notFound } from "next/navigation";

import LineageTimeline from "@/components/LineageTimeline";
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
 *
 * The view inherits the v2 layered swim-lane design via
 * `LineageTimeline`, mounted with `publicMode` — which re-applies the
 * strict visibility filter inside the component as a second guard, so a
 * private event can never reach the DOM even as a "[redacted]" stub.
 */

type PageProps = { params: Promise<{ slug: string }> };

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
      <style>{lineagePageCss}</style>

      <article
        className="lineage-public-article"
        style={{
          // Wider than a prose page: the layered timeline needs room for
          // its swim lanes on desktop. Below 720px the timeline reflows
          // to a single column (see LineageTimeline) so no horizontal
          // scroll is needed there — only the gutter padding shrinks.
          maxWidth: "1080px",
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

        <LineageTimeline lineage={lineage} publicMode />
      </article>
    </main>
  );
}

const lineagePageCss = `
@media (max-width: 720px) {
  .lineage-public-article {
    padding: 2rem 1.05rem 3rem !important;
  }
}
`;
