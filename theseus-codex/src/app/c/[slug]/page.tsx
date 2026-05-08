import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import ConclusionView from "@/components/ConclusionView";
import PublicHeader from "@/components/PublicHeader";
import RespondCallout from "@/components/RespondCallout";
import { getFounder } from "@/lib/auth";
import { getConclusionBySlug, listConclusionVersions, responsesForPublishedId } from "@/lib/conclusionsRead";

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

  const [allVersions, responses] = await Promise.all([
    listConclusionVersions(row.slug),
    responsesForPublishedId(row.id),
  ]);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <ConclusionView
        row={row}
        allVersions={allVersions}
        responses={responses}
        topSlot={
          <>
            <Link
              href="/"
              className="mono"
              style={{
                color: "var(--amber-dim)",
                display: "inline-block",
                fontSize: "0.6rem",
                letterSpacing: "0.28em",
                marginBottom: "1.5rem",
                textDecoration: "none",
                textTransform: "uppercase",
              }}
            >
              &larr; Back to index
            </Link>
            <RespondCallout conclusions={[row]} />
          </>
        }
      />
    </>
  );
}
