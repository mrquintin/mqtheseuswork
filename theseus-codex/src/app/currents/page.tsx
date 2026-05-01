import FeedClient from "@/app/currents/FeedClient";
import {
  getCurrentsHealth,
  listCurrents,
  type CurrentsHealth,
} from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";

export const dynamic = "force-dynamic";

export default async function CurrentsPage() {
  let seed: PublicOpinion[] = [];
  let health: CurrentsHealth | null = null;

  const [seedResult, healthResult] = await Promise.allSettled([
    listCurrents({ limit: 20 }),
    getCurrentsHealth(),
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

  return <FeedClient health={health} seed={seed} />;
}
