import { BACKEND } from "@/lib/currentsApi";

/**
 * Founder-internal edge surface: Currents opinion ↔ Polymarket / Kalshi
 * market gap.
 *
 * The data is computed by ``noosphere/forecasts/edge_calc.py`` and exposed
 * through a backend route at ``/founder/currents/{opinionId}/edges``. This
 * client tolerates the route being absent (returns ``[]``) so the founder
 * page degrades gracefully when the Python service has not been deployed
 * with the linker enabled.
 *
 * The public Currents page MUST NOT call this. The path lives under
 * ``/founder/`` so an accidental call from a public-side caller fails
 * authn at the backend rather than silently leaking firm-internal signal.
 */

export interface EdgeReport {
  market_id: string;
  source: "POLYMARKET" | "KALSHI" | string;
  external_id: string;
  title: string;
  firm_yes_probability: number;
  market_yes_price: number;
  edge_pts: number;
  side: "YES" | "NO";
  surface: boolean;
  low_liquidity: boolean;
  suggested_stake_usd: number | null;
  market_url: string | null;
  threshold: number;
}

export interface EdgesForOpinionResponse {
  opinion_id: string;
  edges: EdgeReport[];
}

function joinUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${BACKEND}${normalized}`;
}

/**
 * Build the founder forecast-workspace URL with the suggested position
 * pre-filled. The founder still has to confirm; nothing auto-trades.
 */
export function forecastWorkspaceHref(edge: EdgeReport): string {
  const params = new URLSearchParams({
    market: edge.market_id,
    source: edge.source,
    side: edge.side,
  });
  if (edge.suggested_stake_usd !== null) {
    params.set("size_usd", edge.suggested_stake_usd.toFixed(2));
  }
  return `/forecasts/portfolio?${params.toString()}`;
}

export async function fetchEdgesForOpinion(
  opinionId: string,
  options: { signal?: AbortSignal } = {},
): Promise<EdgeReport[]> {
  if (!opinionId) return [];
  try {
    const res = await fetch(
      joinUrl(`/founder/currents/${encodeURIComponent(opinionId)}/edges`),
      {
        cache: "no-store",
        headers: { accept: "application/json" },
        method: "GET",
        signal: options.signal,
      },
    );
    if (res.status === 404) return [];
    if (!res.ok) {
      console.error("edge_api_fetch_failed", { opinionId, status: res.status });
      return [];
    }
    const payload = (await res.json()) as EdgesForOpinionResponse;
    return Array.isArray(payload?.edges) ? payload.edges : [];
  } catch (error) {
    console.error("edge_api_fetch_error", { opinionId, error });
    return [];
  }
}

export async function fetchEdgesForOpinions(
  opinionIds: readonly string[],
  options: { signal?: AbortSignal } = {},
): Promise<Map<string, EdgeReport[]>> {
  const entries = await Promise.all(
    opinionIds.map(async (id) => [id, await fetchEdgesForOpinion(id, options)] as const),
  );
  return new Map(entries);
}

export function formatEdgeBadgeLabel(edge: EdgeReport): string {
  const venue = edge.source === "POLYMARKET" ? "Polymarket" : edge.source === "KALSHI" ? "Kalshi" : edge.source;
  const marketPct = (edge.market_yes_price * 100).toFixed(0);
  const firmPct = (edge.firm_yes_probability * 100).toFixed(0);
  const delta = edge.edge_pts > 0 ? `+${edge.edge_pts.toFixed(0)}` : edge.edge_pts.toFixed(0);
  return `Edge available: yes (${venue} ${marketPct}%, firm ${firmPct}%, Δ=${delta} pts)`;
}
