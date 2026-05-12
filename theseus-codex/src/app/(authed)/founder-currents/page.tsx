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
import { relativeTime } from "@/lib/relativeTime";

export const dynamic = "force-dynamic";

interface BackendStatus {
  reachable: boolean;
  error: string | null;
}

export default async function FounderCurrentsPage() {
  let seed: PublicOpinion[] = [];
  let health: CurrentsHealth | null = null;
  const backend: BackendStatus = { reachable: false, error: null };

  const [seedResult, healthResult] = await Promise.allSettled([
    listCurrents({ limit: 20 }, { timeoutMs: 6_000 }),
    getCurrentsHealth({ timeoutMs: 4_000 }),
  ] as const);
  if (seedResult.status === "fulfilled") {
    seed = seedResult.value.items;
  } else {
    console.error("founder_currents_seed_fetch_failed", seedResult.reason);
  }
  if (healthResult.status === "fulfilled") {
    health = healthResult.value;
    backend.reachable = true;
  } else {
    console.error("founder_currents_health_fetch_failed", healthResult.reason);
    backend.error =
      healthResult.reason instanceof Error
        ? healthResult.reason.message
        : String(healthResult.reason);
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

      <BackendHealthPanel
        backend={backend}
        health={health}
        latestSeed={seed[0] ?? null}
      />

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

      <FeedClient
        detailBasePath="/founder-currents"
        diagnostic
        health={health}
        seed={seed}
      />
    </main>
  );
}

function timestampOrDash(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toISOString().replace(/\.\d{3}Z$/, "Z")} (${relativeTime(value)})`;
}

function BackendHealthPanel({
  backend,
  health,
  latestSeed,
}: {
  backend: BackendStatus;
  health: CurrentsHealth | null;
  latestSeed: PublicOpinion | null;
}) {
  const cycle = health?.last_cycle ?? null;
  const lastOpinionIso =
    health?.last_opinion_at ?? latestSeed?.generated_at ?? null;
  const lastEventIso =
    health?.last_event_at ?? cycle?.started_at ?? health?.last_cycle_at ?? null;
  const lastError = cycle?.last_error ?? backend.error ?? null;
  const lastErrorCommand =
    'cd noosphere && python -m noosphere.currents once 2>&1 | tail -n 40';

  const okBorder = "rgba(180, 200, 145, 0.45)";
  const warnBorder = "rgba(255, 111, 82, 0.55)";
  const panelBorder = backend.reachable && !lastError ? okBorder : warnBorder;

  return (
    <section
      aria-label="Currents backend health"
      style={{
        background: "rgba(20, 16, 11, 0.55)",
        border: `1px solid ${panelBorder}`,
        borderLeft: `4px solid ${panelBorder}`,
        borderRadius: "6px",
        marginBottom: "1.4rem",
        padding: "0.95rem 1rem",
      }}
    >
      <header
        style={{
          alignItems: "baseline",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.6rem",
          justifyContent: "space-between",
          marginBottom: "0.65rem",
        }}
      >
        <h2
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.66rem",
            letterSpacing: "0.2em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          Backend health
        </h2>
        <span
          className="mono"
          style={{
            color: backend.reachable
              ? "var(--success, #b4c891)"
              : "var(--ember, #ff6f52)",
            fontSize: "0.66rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          {backend.reachable ? "Reachable" : "Unreachable"}
        </span>
      </header>

      <dl
        style={{
          display: "grid",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.78rem",
          gap: "0.35rem 1.2rem",
          gridTemplateColumns: "minmax(160px, max-content) 1fr",
          margin: 0,
        }}
      >
        <dt style={{ color: "var(--amber-dim)" }}>X bearer token</dt>
        <dd style={{ margin: 0 }}>
          {health?.x_bearer_present
            ? "present"
            : "missing (set X_BEARER_TOKEN)"}
        </dd>

        <dt style={{ color: "var(--amber-dim)" }}>Curated accounts</dt>
        <dd style={{ margin: 0 }}>{health?.curated_count ?? "—"}</dd>

        <dt style={{ color: "var(--amber-dim)" }}>Search queries</dt>
        <dd style={{ margin: 0 }}>{health?.search_count ?? "—"}</dd>

        <dt style={{ color: "var(--amber-dim)" }}>Last scheduler cycle</dt>
        <dd style={{ margin: 0 }}>{timestampOrDash(health?.last_cycle_at ?? null)}</dd>

        <dt style={{ color: "var(--amber-dim)" }}>Last X post ingested</dt>
        <dd style={{ margin: 0 }}>{timestampOrDash(lastEventIso)}</dd>

        <dt style={{ color: "var(--amber-dim)" }}>Last opinion generated</dt>
        <dd style={{ margin: 0 }}>{timestampOrDash(lastOpinionIso)}</dd>

        <dt style={{ color: "var(--amber-dim)" }}>Events / opinions (24h)</dt>
        <dd style={{ margin: 0 }}>
          {(health?.events_last_24h ?? 0)} ingested ·{" "}
          {(health?.opinions_last_24h ?? 0)} opinions
        </dd>

        <dt style={{ color: "var(--amber-dim)" }}>Last cycle outcome</dt>
        <dd style={{ margin: 0 }}>
          {cycle
            ? `${cycle.ingested} ingested · ${cycle.opined} opined · ${cycle.rejected} rejected · ${cycle.duration_ms}ms`
            : "no cycle recorded yet"}
        </dd>

        {cycle ? (
          <>
            <dt style={{ color: "var(--amber-dim)" }}>Rejected breakdown</dt>
            <dd style={{ margin: 0 }}>
              below_significance={cycle.abstained_below_significance} ·{" "}
              off_domain={cycle.abstained_off_domain} ·{" "}
              insufficient_sources={cycle.abstained_insufficient} ·{" "}
              near_duplicate={cycle.abstained_near_duplicate} ·{" "}
              budget={cycle.abstained_budget}
            </dd>
          </>
        ) : null}

        {health?.disabled_reasons.length ? (
          <>
            <dt style={{ color: "var(--ember, #ff6f52)" }}>Disabled reasons</dt>
            <dd style={{ color: "var(--ember, #ff6f52)", margin: 0 }}>
              {health.disabled_reasons.join(", ")}
            </dd>
          </>
        ) : null}

        {lastError ? (
          <>
            <dt style={{ color: "var(--ember, #ff6f52)" }}>Last error</dt>
            <dd style={{ color: "var(--currents-parchment)", margin: 0 }}>
              <div style={{ wordBreak: "break-word" }}>{lastError}</div>
              <div
                style={{
                  color: "var(--amber-dim)",
                  marginTop: "0.35rem",
                }}
              >
                Reproduce:{" "}
                <code
                  style={{
                    background: "rgba(232, 225, 211, 0.05)",
                    borderRadius: "3px",
                    padding: "0.1rem 0.35rem",
                  }}
                >
                  {lastErrorCommand}
                </code>
              </div>
            </dd>
          </>
        ) : null}
      </dl>
    </section>
  );
}
