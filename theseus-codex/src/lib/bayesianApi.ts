import { BACKEND } from "@/lib/currentsApi";

/**
 * Founder-internal Bayesian-belief-layer surface.
 *
 * The Python side (`noosphere/inquiry/bayesian_network.py`,
 * `bn_inference.py`, `bn_learning.py`) derives a Bayesian DAG from the
 * cascade graph and computes a marginal probability per claim. This
 * client is the TS-side boundary to the founder route at
 * `/founder/conclusions/{conclusionId}/bayesian`, which returns the
 * payload built by `bn_inference.bayesian_view_payload`.
 *
 * Why this lives behind `/founder/`: marginal probabilities are NOT
 * displayed publicly without founder review — this is a founder-side
 * tool first. The route path makes an accidental public-side call fail
 * authn at the backend rather than silently leaking firm-internal
 * inference. The public conclusion page MUST NOT import this module.
 *
 * Like `edgeApi.ts`, this client tolerates the route being absent
 * (returns `null`) so the founder page degrades gracefully when the
 * Python service has not been deployed with the Bayesian layer enabled.
 */

/** One parent claim's sensitivity — mirrors `ParentSensitivity`. */
export interface ParentSensitivityDTO {
  parentId: string;
  parentRef: string;
  /** Marginal of the focus node with no pin on this parent. */
  baseline: number;
  /** Marginal if this parent were retracted (pinned False). */
  pIfRetracted: number;
  /** Marginal if this parent were confirmed (pinned True). */
  pIfHeld: number;
  /** `baseline - pIfRetracted` — the drop on retraction. */
  delta: number;
  /** `|pIfHeld - pIfRetracted|` — the full swing; ranking key. */
  influence: number;
}

/** Founder Bayesian-view payload — mirrors `bayesian_view_payload`. */
export interface BayesianViewDTO {
  nodeId: string;
  ref: string;
  kind: string;
  /** True while the CPT is a seeded stipulation, False once data-fit. */
  seeded: boolean;
  /** P(claim holds | evidence). */
  marginal: number;
  ciLow: number;
  ciHigh: number;
  /** "exact" (variable elimination) | "importance_sampling". */
  method: "exact" | "importance_sampling" | string;
  exact: boolean;
  /** CPT-resample count (exact path) or sample count (approximate). */
  nSamples: number;
  /** True when this node was itself pinned by an evidence update. */
  isEvidence: boolean;
  nodeCount: number;
  exactLimit: number;
  /** Cascade edges dropped to keep the BN projection acyclic. */
  droppedEdgeCount: number;
  /** Evidence pins applied to this inference run, by node id. */
  evidence: Record<string, boolean>;
  /** Most-influential parents, already ranked by influence desc. */
  parents: ParentSensitivityDTO[];
}

interface RawParentSensitivity {
  parent_id: string;
  parent_ref: string;
  baseline: number;
  p_if_retracted: number;
  p_if_held: number;
  delta: number;
  influence: number;
}

interface RawBayesianView {
  node_id: string;
  ref: string;
  kind: string;
  seeded: boolean;
  marginal: number;
  ci_low: number;
  ci_high: number;
  method: string;
  exact: boolean;
  n_samples: number;
  is_evidence: boolean;
  node_count: number;
  exact_limit: number;
  dropped_edge_count: number;
  evidence: Record<string, boolean>;
  parents: RawParentSensitivity[];
}

function normalizeParent(raw: RawParentSensitivity): ParentSensitivityDTO {
  return {
    parentId: raw.parent_id,
    parentRef: raw.parent_ref,
    baseline: raw.baseline,
    pIfRetracted: raw.p_if_retracted,
    pIfHeld: raw.p_if_held,
    delta: raw.delta,
    influence: raw.influence,
  };
}

function normalize(raw: RawBayesianView): BayesianViewDTO {
  return {
    nodeId: raw.node_id,
    ref: raw.ref,
    kind: raw.kind,
    seeded: raw.seeded,
    marginal: raw.marginal,
    ciLow: raw.ci_low,
    ciHigh: raw.ci_high,
    method: raw.method,
    exact: raw.exact,
    nSamples: raw.n_samples,
    isEvidence: raw.is_evidence,
    nodeCount: raw.node_count,
    exactLimit: raw.exact_limit,
    droppedEdgeCount: raw.dropped_edge_count,
    evidence: raw.evidence ?? {},
    parents: Array.isArray(raw.parents) ? raw.parents.map(normalizeParent) : [],
  };
}

function joinUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${BACKEND}${normalized}`;
}

/**
 * Fetch the founder Bayesian view for one conclusion.
 *
 * Returns `null` when the route is absent (404) or the backend is
 * unreachable — the caller renders a "not available" state rather than
 * erroring. `evidence` optionally pins claims to a truth value (a
 * retracted source → `false`, a resolved forecast → `true`) so the
 * founder can preview a what-if before it is committed to the cascade.
 */
export async function fetchBayesianView(
  conclusionId: string,
  options: {
    evidence?: Record<string, boolean>;
    signal?: AbortSignal;
  } = {},
): Promise<BayesianViewDTO | null> {
  if (!conclusionId) return null;
  const params = new URLSearchParams();
  if (options.evidence && Object.keys(options.evidence).length > 0) {
    params.set("evidence", JSON.stringify(options.evidence));
  }
  const query = params.toString();
  const path = `/founder/conclusions/${encodeURIComponent(conclusionId)}/bayesian${
    query ? `?${query}` : ""
  }`;
  try {
    const res = await fetch(joinUrl(path), {
      cache: "no-store",
      headers: { accept: "application/json" },
      method: "GET",
      signal: options.signal,
    });
    if (res.status === 404) return null;
    if (!res.ok) {
      console.error("bayesian_api_fetch_failed", {
        conclusionId,
        status: res.status,
      });
      return null;
    }
    const payload = (await res.json()) as RawBayesianView;
    if (!payload || typeof payload.marginal !== "number") return null;
    return normalize(payload);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return null;
    }
    console.error("bayesian_api_fetch_error", { conclusionId, error });
    return null;
  }
}

// ── display helpers ─────────────────────────────────────────────────────

/** Percent string for a probability, e.g. 0.557 → "55.7%". */
export function formatProbability(p: number): string {
  if (!Number.isFinite(p)) return "—";
  return `${(p * 100).toFixed(1)}%`;
}

/** Human label for the credible interval, e.g. "[48.2%, 71.0%]". */
export function formatCredibleInterval(view: BayesianViewDTO): string {
  return `[${formatProbability(view.ciLow)}, ${formatProbability(view.ciHigh)}]`;
}

/**
 * The honest one-line method caption. For graphs past the exact limit
 * this returns the "approximate inference (n=K samples, CI=[a,b])"
 * string the prompt requires — the UI never implies exactness it does
 * not have.
 */
export function methodCaption(view: BayesianViewDTO): string {
  if (view.exact) {
    return `exact inference (variable elimination, ${view.nodeCount} nodes)`;
  }
  return `approximate inference (n=${view.nSamples.toLocaleString()} samples, CI=${formatCredibleInterval(
    view,
  )})`;
}

/**
 * Founder-facing prose for one parent's sensitivity, e.g.
 * "if retracted, the marginal would fall from 49.0% to 10.0%".
 */
export function sensitivityProse(
  view: BayesianViewDTO,
  parent: ParentSensitivityDTO,
): string {
  const direction = parent.pIfRetracted <= view.marginal ? "fall" : "rise";
  return `if retracted, the marginal would ${direction} from ${formatProbability(
    view.marginal,
  )} to ${formatProbability(parent.pIfRetracted)}`;
}
