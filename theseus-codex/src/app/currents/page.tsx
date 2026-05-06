import FeedClient from "@/app/currents/FeedClient";
import { Suspense } from "react";
import {
  getCurrentsHealth,
  listCurrents,
  type CurrentsHealth,
} from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";

export const revalidate = 15;

export default async function CurrentsPage() {
  let seed: PublicOpinion[] = [];
  let health: CurrentsHealth | null = null;

  const [seedResult, healthResult] = await Promise.allSettled([
    listCurrents({ limit: 20 }, { next: { revalidate: 15, tags: ["currents-seed"] } }),
    getCurrentsHealth({ next: { revalidate: 15, tags: ["currents-health"] } }),
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
