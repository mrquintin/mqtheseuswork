import FeedClient from "@/app/currents/FeedClient";
import { Suspense } from "react";
import {
  getCurrentsHealth,
  listCurrents,
  type CurrentsHealth,
} from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const SEED_FETCH_TIMEOUT_MS = 8_000;

export default async function CurrentsPage() {
  let seed: PublicOpinion[] = [];
  let health: CurrentsHealth | null = null;

  const [seedResult, healthResult] = await Promise.allSettled([
    listCurrents(
      { limit: 20 },
      {
        cache: "no-store",
        signal: AbortSignal.timeout(SEED_FETCH_TIMEOUT_MS),
      },
    ),
    getCurrentsHealth({
      cache: "no-store",
      signal: AbortSignal.timeout(SEED_FETCH_TIMEOUT_MS),
    }),
  ] as const);
  if (seedResult.status === "fulfilled") {
    seed = seedResult.value.items;
  } else {
    console.error("currents_seed_fetch_failed", seedResult.reason);
  }
  if (healthResult.status === "fulfilled") {
    health = healthResult.value;
  } else {
    console.error("currents_health_fetch_failed", healthResult.reason);
  }

  return (
    <Suspense fallback={<CurrentsLoadingState />}>
      <FeedClient health={health} seed={seed} />
    </Suspense>
  );
}

function CurrentsLoadingState() {
  return (
    <section
      aria-label="Current-events opinions loading"
      style={{
        border: "1px solid var(--currents-border)",
        borderRadius: "6px",
        color: "var(--currents-parchment-dim)",
        padding: "1rem",
      }}
    >
      Loading currents.
    </section>
  );
}
