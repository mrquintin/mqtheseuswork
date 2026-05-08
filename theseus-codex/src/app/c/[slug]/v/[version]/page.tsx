import type { Metadata } from "next";
import { notFound } from "next/navigation";

import ConclusionView from "@/components/ConclusionView";
import PublicHeader from "@/components/PublicHeader";
import SignatureBanner from "@/components/SignatureBanner";
import { getFounder } from "@/lib/auth";
import { getConclusionVersion, listConclusionVersions, responsesForPublishedId } from "@/lib/conclusionsRead";
import { db } from "@/lib/db";
import { isMqsFreshForPublic, mqsForConclusion } from "@/lib/methodologyProfiles";
import { evaluatePublicationSignatureStatus } from "@/lib/publicationService";

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

  const [allVersions, responses, sourceConclusion] = await Promise.all([
    listConclusionVersions(row.slug),
    responsesForPublishedId(row.id),
    db.conclusion.findUnique({
      where: { id: row.sourceConclusionId },
      select: { id: true, organizationId: true, updatedAt: true, createdAt: true },
    }),
  ]);

  let publicMqs = null as Awaited<ReturnType<typeof mqsForConclusion>>;
  if (sourceConclusion) {
    const fetched = await mqsForConclusion(sourceConclusion.organizationId, sourceConclusion.id);
    const lastEdited = sourceConclusion.updatedAt ?? sourceConclusion.createdAt;
    publicMqs = isMqsFreshForPublic(fetched, lastEdited) ? fetched : null;
  }

  const signatureStatus = await evaluatePublicationSignatureStatus(row.id, {
    slug: row.slug,
    version: row.version,
    publishedAt: row.publishedAt,
    discountedConfidence: row.discountedConfidence,
    statedConfidence: row.statedConfidence,
    payload: row.payload,
    mqs: publicMqs,
  });

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <div className="mx-auto max-w-3xl px-4">
        <SignatureBanner status={signatureStatus} slug={row.slug} version={row.version} />
      </div>
      <ConclusionView allVersions={allVersions} mqs={publicMqs} responses={responses} row={row} />
    </>
  );
}
