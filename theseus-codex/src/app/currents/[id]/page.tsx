import type { Metadata } from "next";

import DetailClient from "@/app/currents/[id]/DetailClient";
import { getCurrent, getCurrentSources } from "@/lib/currentsApi";
import { SITE } from "@/lib/site";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  try {
    const { id } = await params;
    const op = await getCurrent(id);
    const description = `${op.body_markdown
      .slice(0, 220)
      .replace(/\s+/g, " ")
      .trim()}...`;

    return {
      title: op.headline,
      description,
      openGraph: {
        title: op.headline,
        description,
        type: "article",
        siteName: "Theseus Codex",
        url: `${SITE}/currents/${op.id}`,
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

export default async function CurrentDetailPage({ params }: PageProps) {
  const { id } = await params;
  const [opinion, sources] = await Promise.all([
    getCurrent(id),
    getCurrentSources(id),
  ]);

  return <DetailClient opinion={opinion} sources={sources} />;
}
