import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { bundle, pickConclusion, responsesForPublishedId } from "@/lib/bundle";

import ConclusionView from "@/components/ConclusionView";

export async function generateStaticParams() {
  const slugs = new Set(bundle.conclusions.map((c) => c.slug));
  return [...slugs].map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const row = pickConclusion(slug);
  if (!row) return { title: "Not found" };
  return { title: row.payload.conclusionText.slice(0, 80) };
}

export default async function LatestConclusionPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const row = pickConclusion(slug);
  if (!row) notFound();

  const allVersions = bundle.conclusions.filter((c) => c.slug === row.slug).sort((a, b) => a.version - b.version);
  const responses = responsesForPublishedId(row.id);

  return <ConclusionView row={row} allVersions={allVersions} responses={responses} />;
}
