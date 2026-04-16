import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { bundle, pickConclusion, responsesForPublishedId } from "@/lib/bundle";

import ConclusionView from "@/components/ConclusionView";

export async function generateStaticParams() {
  return bundle.conclusions.map((c) => ({ slug: c.slug, version: String(c.version) }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; version: string }>;
}): Promise<Metadata> {
  const { slug, version } = await params;
  const v = Number(version);
  const row = pickConclusion(slug, Number.isFinite(v) ? v : undefined);
  if (!row) return { title: "Not found" };
  return { title: `${row.payload.conclusionText.slice(0, 72)} (v${row.version})` };
}

export default async function VersionedConclusionPage({
  params,
}: {
  params: Promise<{ slug: string; version: string }>;
}) {
  const { slug, version } = await params;
  const v = Number(version);
  if (!Number.isFinite(v)) notFound();

  const row = pickConclusion(slug, v);
  if (!row) notFound();

  const allVersions = bundle.conclusions.filter((c) => c.slug === row.slug).sort((a, b) => a.version - b.version);
  const responses = responsesForPublishedId(row.id);

  return <ConclusionView row={row} allVersions={allVersions} responses={responses} />;
}
