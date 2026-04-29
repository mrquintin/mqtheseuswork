import FeedClient from "@/app/currents/FeedClient";
import { listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";

export const dynamic = "force-dynamic";

export default async function CurrentsPage() {
  let seed: PublicOpinion[] = [];

  try {
    const resp = await listCurrents({ limit: 20 });
    seed = resp.items;
  } catch (err) {
    console.error("currents_seed_fetch_failed", err);
  }

  return <FeedClient seed={seed} />;
}
