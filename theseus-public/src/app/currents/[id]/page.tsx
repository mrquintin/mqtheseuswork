import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { PublicOpinion, PublicSource } from "@/lib/currentsTypes";
import { DetailClient } from "./DetailClient";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// Hit the FastAPI backend directly from the server. The client helper in
// `@/lib/currentsApi` uses a relative URL that only works in the browser.
const BACKEND = process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const resp = await fetch(
      new URL(`/v1/currents/${encodeURIComponent(id)}`, BACKEND),
      { cache: "no-store" },
    );
    if (!resp.ok) return { title: "Current event" };
    const op = await resp.json();
    const description =
      (op.body_markdown || "").slice(0, 220).replace(/\s+/g, " ").trim() + "…";
    return {
      title: op.headline,
      description,
      openGraph: {
        title: op.headline,
        description,
        type: "article",
        siteName: "Theseus",
        url: `/currents/${op.id}`,
      },
      twitter: {
        card: "summary_large_image",
        title: op.headline,
        description,
      },
    };
  } catch {
    return { title: "Current event" };
  }
}

async function getOpinionServer(id: string): Promise<PublicOpinion | null> {
  const resp = await fetch(
    new URL(`/v1/currents/${encodeURIComponent(id)}`, BACKEND),
    { cache: "no-store" },
  );
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`getCurrent ${resp.status}`);
  return (await resp.json()) as PublicOpinion;
}

async function getSourcesServer(id: string): Promise<PublicSource[]> {
  const resp = await fetch(
    new URL(`/v1/currents/${encodeURIComponent(id)}/sources`, BACKEND),
    { cache: "no-store" },
  );
  if (!resp.ok) throw new Error(`getSources ${resp.status}`);
  return (await resp.json()) as PublicSource[];
}

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let opinion: PublicOpinion | null;
  let sources: PublicSource[];
  try {
    [opinion, sources] = await Promise.all([
      getOpinionServer(id),
      getSourcesServer(id),
    ]);
  } catch (err) {
    console.error("currents_detail_fetch_failed", err);
    throw err;
  }
  if (!opinion) notFound();
  return <DetailClient opinion={opinion} sources={sources} />;
}
