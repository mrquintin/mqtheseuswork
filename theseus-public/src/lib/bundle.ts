import type { PublicConclusion, PublishedBundle } from "@/lib/types";

import raw from "../../content/published.json";

export const bundle = raw as PublishedBundle;

export function latestConclusions(bundle: PublishedBundle): PublicConclusion[] {
  const map = new Map<string, PublicConclusion>();
  for (const c of bundle.conclusions) {
    const cur = map.get(c.slug);
    if (!cur || c.version > cur.version) {
      map.set(c.slug, c);
    }
  }
  return [...map.values()].sort((a, b) => a.slug.localeCompare(b.slug));
}

export function pickConclusion(slug: string, version?: number): PublicConclusion | null {
  const rows = bundle.conclusions.filter((c) => c.slug === slug);
  if (!rows.length) return null;
  if (typeof version === "number") {
    return rows.find((c) => c.version === version) ?? null;
  }
  return rows.reduce((a, b) => (b.version > a.version ? b : a));
}

export function responsesForPublishedId(publishedId: string): PublishedBundle["responses"] {
  return bundle.responses.filter((r) => r.publishedConclusionId === publishedId);
}
