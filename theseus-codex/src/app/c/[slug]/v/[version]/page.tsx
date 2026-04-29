import type { Metadata } from "next";
import { notFound } from "next/navigation";

import ConclusionView from "@/components/ConclusionView";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { getConclusionVersion, listConclusionVersions, responsesForPublishedId } from "@/lib/conclusionsRead";

export const dynamic = "force-dynamic";
export const revalidate = 60;

type PageProps = { params: Promise<{ slug: string; version: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug, version } = await params;
  const v = Number(version);
  if (!Number.isFinite(v)) return { title: "Not found" };
  const row = await getConclusionVersion(slug, v);
  if (!row) return { title: "Not found" };
  return { title: `${row.payload.conclusionText.slice(0, 72)} (v${row.version})` };
}

export default async function VersionedConclusionPage({ params }: PageProps) {
  const { slug, version } = await params;
  const v = Number(version);
  if (!Number.isFinite(v)) notFound();

  const founder = await getFounder();
  const row = await getConclusionVersion(slug, v);
  if (!row) notFound();

  const [allVersions, responses] = await Promise.all([
    listConclusionVersions(row.slug),
    responsesForPublishedId(row.id),
  ]);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <ConclusionView row={row} allVersions={allVersions} responses={responses} />
    </>
  );
}
