import { FeedClient } from "./FeedClient";
import { paramsToFilter } from "@/lib/filterMatch";
import type { PaginatedOpinions, PublicOpinion } from "@/lib/currentsTypes";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// Server components can't use the relative-URL client helper in
// `@/lib/currentsApi`, so we hit the FastAPI backend directly for the
// initial seed. Client-side hydration still goes through the Next proxy
// via `useLiveOpinions` / `listCurrents` for pagination.
const BACKEND = process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088";

async function listCurrentsServerSide(params: {
  limit: number;
  topic?: string | null;
  stance?: string | null;
  since?: string | null;
}): Promise<PaginatedOpinions> {
  const url = new URL("/v1/currents", BACKEND);
  url.searchParams.set("limit", String(params.limit));
  if (params.topic) url.searchParams.set("topic", params.topic);
  if (params.stance) url.searchParams.set("stance", params.stance);
  if (params.since) url.searchParams.set("since", params.since);
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) throw new Error(`listCurrents ${resp.status}`);
  return (await resp.json()) as PaginatedOpinions;
}

export default async function CurrentsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = await searchParams;
  const filter = paramsToFilter(sp);
  let seed: PublicOpinion[] = [];
  try {
    const resp = await listCurrentsServerSide({
      limit: 20,
      topic: filter.topic,
      stance: filter.stance,
      since: filter.since,
    });
    seed = resp.items;
  } catch (err) {
    // Empty seed is a valid render — the client hook will hydrate over SSE
    // once it mounts. Keeps `next build` green even when the backend is
    // unreachable during a static build pass.
    console.error("currents_initial_fetch_failed", err);
  }
  return <FeedClient seed={seed} initialFilter={filter} />;
}
