import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import ConclusionView from "@/components/ConclusionView";
import PrintButton from "@/components/PrintButton";
import PrintMetadataBlock from "@/components/PrintMetadataBlock";
import PublicHeader from "@/components/PublicHeader";
import ReaderResponses from "./ReaderResponses";
import RespondCallout from "@/components/RespondCallout";
import { getFounder } from "@/lib/auth";
import { getConclusionBySlug, listConclusionVersions, responsesForPublishedId } from "@/lib/conclusionsRead";
import { db } from "@/lib/db";
import { getPublicSiteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";
export const revalidate = 60;

type PageProps = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const row = await getConclusionBySlug(slug);
  if (!row) return { title: "Not found" };
  return { title: row.payload.conclusionText.slice(0, 80) };
}

export default async function LatestConclusionPage({ params }: PageProps) {
  const { slug } = await params;
  const founder = await getFounder();
  const row = await getConclusionBySlug(slug);
  if (!row) notFound();

  const [allVersions, responses, signature] = await Promise.all([
    listConclusionVersions(row.slug),
    responsesForPublishedId(row.id),
    loadSignatureFingerprint(row.slug, row.version),
  ]);

  const canonicalUrl = `${getPublicSiteUrl()}/c/${encodeURIComponent(row.slug)}`;
  const methodologyLabel = row.payload.methodology.profiles[0]?.patternType ?? null;

  return (
    <div data-testid="conclusion-page">
      <PublicHeader authed={Boolean(founder)} />
      <PrintMetadataBlock
        title={row.payload.conclusionText}
        byline="Theseus"
        publishedAt={row.publishedAt}
        methodology={methodologyLabel}
        confidence={row.discountedConfidence}
        confidenceContext={
          row.statedConfidence
            ? `stated ${(row.statedConfidence * 100).toFixed(0)}%`
            : null
        }
        canonicalUrl={canonicalUrl}
        signatureFingerprint={signature}
      />
      <ConclusionView
        row={row}
        allVersions={allVersions}
        responses={responses}
        topSlot={
          <div
            className="no-print"
            style={{
              alignItems: "center",
              display: "flex",
              gap: "1rem",
              justifyContent: "space-between",
              marginBottom: "1.5rem",
            }}
          >
            <Link
              href="/"
              className="mono"
              style={{
                color: "var(--amber-dim)",
                display: "inline-block",
                fontSize: "0.6rem",
                letterSpacing: "0.28em",
                textDecoration: "none",
                textTransform: "uppercase",
              }}
            >
              &larr; Back to index
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
            <RespondCallout conclusions={[row]} />
          </div>
        }
        bottomSlot={<ReaderResponses publishedConclusionId={row.id} />}
      />
    </div>
  );
}

async function loadSignatureFingerprint(
  slug: string,
  version: number,
): Promise<string | null> {
  try {
    const sig = await db.publicationSignature.findFirst({
      where: { slug, version },
      orderBy: { version: "desc" },
      select: { keyFingerprint: true },
    });
    if (sig?.keyFingerprint) return sig.keyFingerprint;
    const fallback = await db.publicationSignature.findFirst({
      where: { slug },
      orderBy: { version: "desc" },
      select: { keyFingerprint: true },
    });
    return fallback?.keyFingerprint ?? null;
  } catch {
    return null;
  }
}
