import Link from "next/link";

import FeedClient from "@/app/currents/FeedClient";
import EdgeBadge from "@/components/EdgeBadge";
import {
  getCurrentsHealth,
  listCurrents,
  type CurrentsHealth,
} from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { fetchEdgesForOpinions, type EdgeReport } from "@/lib/edgeApi";

export const dynamic = "force-dynamic";

export default async function FounderCurrentsPage() {
  let seed: PublicOpinion[] = [];
  let health: CurrentsHealth | null = null;

  const [seedResult, healthResult] = await Promise.allSettled([
    listCurrents({ limit: 20 }),
    getCurrentsHealth(),
  ] as const);
  if (seedResult.status === "fulfilled") {
    seed = seedResult.value.items;
  } else {
    console.error("founder_currents_seed_fetch_failed", seedResult.reason);
  }
  if (healthResult.status === "fulfilled") {
    health = healthResult.value;
  } else {
    console.error("founder_currents_health_fetch_failed", healthResult.reason);
  }

  const edgeMap = await fetchEdgesForOpinions(seed.map((opinion) => opinion.id));
  const surfacedEdges = seed
    .map((opinion) => ({
      opinion,
      edges: (edgeMap.get(opinion.id) ?? []).filter((edge) => edge.surface),
    }))
    .filter((entry): entry is { opinion: PublicOpinion; edges: EdgeReport[] } =>
      entry.edges.length > 0,
    );

  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "1.5rem 1.25rem 4rem" }}>
      <header
        style={{
          alignItems: "end",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.85rem",
          justifyContent: "space-between",
          marginBottom: "1.2rem",
        }}
      >
        <div>
          <p
            className="mono"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.62rem",
              letterSpacing: "0.18em",
              margin: 0,
              textTransform: "uppercase",
            }}
          >
            Founder portal
          </p>
          <h1
            style={{
              color: "var(--gold)",
              fontFamily: "'Cinzel', serif",
              letterSpacing: "0.08em",
              margin: "0.25rem 0 0",
            }}
          >
            Currents
          </h1>
        </div>
        <Link
          className="mono"
          href="/currents"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.75rem",
            textDecoration: "none",
          }}
        >
          Public view
        </Link>
      </header>

      {surfacedEdges.length > 0 ? (
        <section
          aria-label="Edges available"
          style={{ display: "grid", gap: "0.5rem", marginBottom: "1.4rem" }}
        >
          <p
            className="mono"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.62rem",
              letterSpacing: "0.18em",
              margin: 0,
              textTransform: "uppercase",
            }}
          >
            Edges available — firm-internal
          </p>
          {surfacedEdges.flatMap(({ opinion, edges }) =>
            edges.map((edge) => (
              <div key={`${opinion.id}-${edge.market_id}`}>
                <Link
                  href={`/founder-currents/${encodeURIComponent(opinion.id)}`}
                  style={{
                    color: "var(--currents-parchment, #e8e1d3)",
                    display: "block",
                    fontSize: "0.82rem",
                    marginBottom: "0.2rem",
                    textDecoration: "none",
                  }}
                >
                  {opinion.headline}
                </Link>
                <EdgeBadge edge={edge} opinionHeadline={opinion.headline} />
              </div>
            )),
          )}
        </section>
      ) : null}

      <FeedClient detailBasePath="/founder-currents" health={health} seed={seed} />
    </main>
  );
}
