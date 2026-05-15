/**
 * Public calibration scorecard — read-through layer.
 *
 * Source-of-truth precedence:
 *
 *   1. The nightly manifest written by `noosphere/forecasts/scheduler.py`
 *      (path resolved from THESEUS_PUBLIC_CALIBRATION_PATH or
 *      NOOSPHERE_DATA_DIR/public_calibration_manifest.json). Reading from
 *      the disk artifact is the auditable path: the same bytes that
 *      external auditors hash are the bytes the page renders.
 *
 *   2. Live DB fallback. If the manifest is not on disk (cold start, dev,
 *      no scheduler) we synthesize a partial manifest from Prisma. This
 *      is the lossy path — no method / domain attribution — but it lets
 *      the page render the aggregate Brier and reliability curve.
 *
 * All shaping (binning, bootstrap, hashing) happens in Python. This TS
 * file is a normalizer, not an estimator; it never recomputes the curve.
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { db } from "@/lib/db";

export const PUBLIC_CALIBRATION_SCHEMA = "theseus.public_calibration.manifest";

/**
 * Public calibration manifest schema version. Surfaced on
 * `/api/public/calibration/manifest` as both `meta.schemaVersion` and
 * the `X-Schema-Version` response header. External auditors pin against
 * this — bumping it is a published-contract change and requires an
 * entry in `docs/architecture/API_Envelope_Contract.md` under
 * "Schema-version changelog".
 *
 * v1 (2026-03): initial public release alongside the unified envelope.
 */
export const PUBLIC_CALIBRATION_SCHEMA_VERSION = 1;
export const SPARSE_BIN_THRESHOLD = 5;
export const STALE_DAYS = 14;

/**
 * Minimum number of resolved binary forecasts below which the headline
 * refuses to print a point estimate. A Brier over a handful of
 * resolutions is dominated by noise; the page says "n=K — too few
 * resolutions for a stable score" rather than reporting a flattering
 * number it cannot defend.
 */
export const HEADLINE_MIN_N = 25;
/** Bootstrap resample count + CI level for the headline Brier interval. */
export const HEADLINE_BOOTSTRAP_ITERS = 2000;
export const HEADLINE_CI_LEVEL = 0.9;

/**
 * Resolution-time-horizon buckets for the slice filter: the elapsed time
 * between a forecast being published and the market resolving it.
 */
export const HORIZON_BUCKETS: ReadonlyArray<{
  key: string;
  label: string;
  maxDays: number | null;
}> = [
  { key: "lt7", label: "≤ 7 days", maxDays: 7 },
  { key: "8-30", label: "8–30 days", maxDays: 30 },
  { key: "31-90", label: "31–90 days", maxDays: 90 },
  { key: "gt90", label: "> 90 days", maxDays: null },
];

export type CalibrationFilter = {
  domain?: string | null;
  methodName?: string | null;
  methodVersion?: string | null;
  venue?: string | null;
  horizon?: string | null;
};

export type BrierWindow = {
  label: string;
  days: number | null;
  n: number;
  meanBrier: number | null;
  meanLogLoss: number | null;
};

export type ReliabilityBin = {
  lo: number;
  hi: number;
  n: number;
  meanPredicted: number | null;
  observedFrequency: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  sparse: boolean;
};

export type CalibrationSlope = {
  slope: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  sampleSize: number;
};

export type DecileEntry = {
  predictionId: string;
  marketId: string;
  headline: string;
  marketTitle: string;
  marketUrl: string | null;
  domain: string;
  methodName: string | null;
  methodVersion: string | null;
  probabilityYes: number;
  outcome: string;
  brier: number;
  resolvedAt: string | null;
};

export type MethodFacet = {
  name: string;
  version: string;
  n: number;
};

/** A generic slice facet for the filter chips (venue, horizon, ...). */
export type CalibrationFacet = {
  key: string;
  label: string;
  n: number;
};

/**
 * The hero number. `stable` is false when `n < HEADLINE_MIN_N`; the page
 * then suppresses the point estimate entirely rather than report a
 * flattering figure it cannot defend. `ciLow`/`ciHigh` are a
 * non-parametric bootstrap interval over the per-forecast Brier scores —
 * null when the manifest revision predates the field or n is 0.
 */
export type HeadlineBrier = {
  meanBrier: number | null;
  n: number;
  ciLow: number | null;
  ciHigh: number | null;
  ciLevel: number;
  bootstrapIterations: number;
  stable: boolean;
};

/**
 * One resolved forecast in the calibration numerator, reduced to what the
 * audit list needs. Every entry is one click from its underlying record
 * at `/forecasts/{predictionId}` — this is what makes the scorecard
 * non-fakeable: every number on the page has a paper trail.
 */
export type ResolvedAuditEntry = {
  predictionId: string;
  headline: string;
  marketTitle: string;
  marketUrl: string | null;
  domain: string;
  venue: string | null;
  methodName: string | null;
  methodVersion: string | null;
  probabilityYes: number;
  outcome: string;
  brier: number;
  resolvedAt: string | null;
};

export type PublicCalibrationManifest = {
  schema: string;
  schemaVersion: number;
  generatedAt: string;
  source: "manifest" | "live";
  publishHorizonDays: number;
  sparseBinThreshold: number;
  bootstrapIterations: number;
  ciLevel: number;
  binCount: number;
  counts: {
    total: number;
    resolvedBinary: number;
    withdrawn: number;
    staleUnresolved: number;
    continuous: number;
  };
  withdrawnRate: number | null;
  resolutionSetHash: string;
  binaryMetricName: string;
  continuousMetricName: string;
  aggregateBrier: BrierWindow[];
  calibrationCurve: ReliabilityBin[];
  calibrationSlope: CalibrationSlope;
  decileBest: DecileEntry[];
  decileWorst: DecileEntry[];
  continuousQuadraticLoss: number | null;
  domains: string[];
  methods: MethodFacet[];
  venues: CalibrationFacet[];
  horizons: CalibrationFacet[];
  headlineBrier: HeadlineBrier;
  /** Fraction of resolved forecasts whose outcome was YES (the climatology base rate). */
  outcomeBaseRate: number | null;
  /** Every resolved forecast in the numerator, one click from its record. */
  resolvedIndex: ResolvedAuditEntry[];
  /**
   * True when `resolvedIndex` is the full numerator. False when it is
   * only the decile-derived subset (a manifest revision that predates the
   * full index); the page discloses the gap rather than implying coverage.
   */
  resolvedIndexComplete: boolean;
  filter: CalibrationFilter;
  notes: string[];
};

// ── Shared low-level helpers ──────────────────────────────────────────────

function asNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof value === "object" && value !== null && "toNumber" in (value as object)) {
    try {
      const n = (value as { toNumber: () => number }).toNumber();
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }
  return null;
}

function asString(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  return String(value);
}

function asBoolean(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value.trim().toLowerCase() === "true";
  return Boolean(value);
}

function isoOrNull(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "string") return value || null;
  return null;
}

function manifestPath(): string {
  const explicit = process.env.THESEUS_PUBLIC_CALIBRATION_PATH?.trim();
  if (explicit) return explicit;
  const dataDir = process.env.NOOSPHERE_DATA_DIR?.trim();
  const root = dataDir ? dataDir : "/var/lib/theseus";
  return path.join(root, "public_calibration_manifest.json");
}

// ── Derived metrics & faceting (pure, shared by both source paths) ────────

/**
 * Deterministic PRNG (mulberry32). The headline bootstrap CI must be
 * reproducible: an auditor re-running the resample from the manifest's
 * resolution set gets the same interval the page renders.
 */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Non-parametric percentile bootstrap CI over a sample mean — used for
 * the headline Brier interval. Returns nulls for an empty sample. The
 * page never recomputes the *curve* (Python owns that), but the headline
 * interval is cheap and must exist even on the live fallback path.
 */
export function bootstrapMeanCi(
  values: number[],
  options: { iterations?: number; ciLevel?: number; seed?: number } = {},
): { ciLow: number | null; ciHigh: number | null } {
  const iterations = options.iterations ?? HEADLINE_BOOTSTRAP_ITERS;
  const ciLevel = options.ciLevel ?? HEADLINE_CI_LEVEL;
  const seed = options.seed ?? 0xca11b;
  const n = values.length;
  if (n === 0) return { ciLow: null, ciHigh: null };
  const rand = mulberry32(seed);
  const means: number[] = [];
  for (let it = 0; it < iterations; it += 1) {
    let sum = 0;
    for (let i = 0; i < n; i += 1) {
      sum += values[Math.floor(rand() * n)];
    }
    means.push(sum / n);
  }
  means.sort((a, b) => a - b);
  const alpha = (1 - ciLevel) / 2;
  const loIdx = Math.max(0, Math.floor(alpha * means.length));
  const hiIdx = Math.min(means.length - 1, Math.ceil((1 - alpha) * means.length) - 1);
  return { ciLow: means[loIdx], ciHigh: means[hiIdx] };
}

/**
 * Assemble a HeadlineBrier. `stable` gates the point estimate: below
 * HEADLINE_MIN_N resolutions the page shows the count, not the number.
 */
export function makeHeadlineBrier(
  meanBrier: number | null,
  n: number,
  ci: { ciLow: number | null; ciHigh: number | null },
): HeadlineBrier {
  return {
    meanBrier,
    n,
    ciLow: ci.ciLow,
    ciHigh: ci.ciHigh,
    ciLevel: HEADLINE_CI_LEVEL,
    bootstrapIterations: HEADLINE_BOOTSTRAP_ITERS,
    stable: n >= HEADLINE_MIN_N && meanBrier !== null,
  };
}

function venueFromSource(source: string | null | undefined): string | null {
  const s = (source ?? "").trim().toUpperCase();
  if (s === "POLYMARKET") return "Polymarket";
  if (s === "KALSHI") return "Kalshi";
  return s ? s[0] + s.slice(1).toLowerCase() : null;
}

function venueFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.includes("polymarket.com")) return "Polymarket";
  if (url.includes("kalshi.com")) return "Kalshi";
  return null;
}

/** Bucket an elapsed-days horizon into a HORIZON_BUCKETS key. */
export function horizonKeyForDays(days: number): string {
  for (const bucket of HORIZON_BUCKETS) {
    if (bucket.maxDays === null || days <= bucket.maxDays) return bucket.key;
  }
  return HORIZON_BUCKETS[HORIZON_BUCKETS.length - 1].key;
}

function horizonLabel(key: string): string {
  return HORIZON_BUCKETS.find((b) => b.key === key)?.label ?? key;
}

/** Outcome base rate (fraction YES) from a reliability curve. */
function baseRateFromCurve(bins: ReliabilityBin[]): number | null {
  let totalN = 0;
  let totalYes = 0;
  for (const b of bins) {
    if (b.n > 0 && b.observedFrequency !== null) {
      totalN += b.n;
      totalYes += b.n * b.observedFrequency;
    }
  }
  return totalN > 0 ? totalYes / totalN : null;
}

/** Count rows into facets by a key extractor, dropping null keys. */
function facetCounts<T>(
  rows: readonly T[],
  keyOf: (row: T) => string | null,
  labelOf: (key: string) => string = (k) => k,
): CalibrationFacet[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = keyOf(row);
    if (!key) continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key, n]) => ({ key, label: labelOf(key), n }));
}

function normalizeFacet(raw: Record<string, unknown>): CalibrationFacet {
  const key = asString(raw.key);
  return { key, label: asString(raw.label, key), n: Number(raw.n ?? 0) };
}

function normalizeAuditEntry(raw: Record<string, unknown>): ResolvedAuditEntry {
  const url = typeof raw.market_url === "string" ? raw.market_url : null;
  return {
    predictionId: asString(raw.prediction_id),
    headline: asString(raw.headline),
    marketTitle: asString(raw.market_title),
    marketUrl: url,
    domain: asString(raw.domain),
    venue:
      typeof raw.venue === "string" && raw.venue ? raw.venue : venueFromUrl(url),
    methodName: typeof raw.method_name === "string" ? raw.method_name : null,
    methodVersion: typeof raw.method_version === "string" ? raw.method_version : null,
    probabilityYes: Number(raw.probability_yes ?? 0),
    outcome: asString(raw.outcome),
    brier: Number(raw.brier ?? 0),
    resolvedAt: typeof raw.resolved_at === "string" ? raw.resolved_at : null,
  };
}

function decileToAuditEntry(e: DecileEntry): ResolvedAuditEntry {
  return {
    predictionId: e.predictionId,
    headline: e.headline,
    marketTitle: e.marketTitle,
    marketUrl: e.marketUrl,
    domain: e.domain,
    venue: venueFromUrl(e.marketUrl),
    methodName: e.methodName,
    methodVersion: e.methodVersion,
    probabilityYes: e.probabilityYes,
    outcome: e.outcome,
    brier: e.brier,
    resolvedAt: e.resolvedAt,
  };
}

/** Dedupe audit entries by prediction id, newest resolution first. */
function dedupeAuditEntries(entries: ResolvedAuditEntry[]): ResolvedAuditEntry[] {
  const byId = new Map<string, ResolvedAuditEntry>();
  for (const e of entries) {
    if (!byId.has(e.predictionId)) byId.set(e.predictionId, e);
  }
  return Array.from(byId.values()).sort((a, b) => {
    const ta = a.resolvedAt ?? "";
    const tb = b.resolvedAt ?? "";
    if (ta !== tb) return tb.localeCompare(ta);
    return a.predictionId.localeCompare(b.predictionId);
  });
}

// ── Disk path: read the canonical nightly manifest ────────────────────────

function readManifestFromDisk(): PublicCalibrationManifest | null {
  const file = manifestPath();
  let text: string;
  try {
    text = fs.readFileSync(file, "utf8");
  } catch {
    return null;
  }
  try {
    const raw = JSON.parse(text) as Record<string, unknown>;
    return normalizeManifest(raw, "manifest");
  } catch (err) {
    console.warn("[public calibration] manifest parse failed:", err);
    return null;
  }
}

function normalizeManifest(
  raw: Record<string, unknown>,
  source: "manifest" | "live",
): PublicCalibrationManifest {
  const counts = (raw.counts ?? {}) as Record<string, unknown>;
  const filter = (raw.filter ?? {}) as Record<string, unknown>;
  const slope = (raw.calibration_slope ?? {}) as Record<string, unknown>;

  const aggregateBrier: BrierWindow[] = (
    (raw.aggregate_brier ?? []) as Array<Record<string, unknown>>
  ).map((w) => ({
    label: asString(w.label),
    days: w.days === null || w.days === undefined ? null : Number(w.days),
    n: Number(w.n ?? 0),
    meanBrier: asNumber(w.mean_brier),
    meanLogLoss: asNumber(w.mean_log_loss),
  }));
  const calibrationCurve: ReliabilityBin[] = (
    (raw.calibration_curve ?? []) as Array<Record<string, unknown>>
  ).map((b) => ({
    lo: Number(b.lo ?? 0),
    hi: Number(b.hi ?? 0),
    n: Number(b.n ?? 0),
    meanPredicted: asNumber(b.mean_predicted),
    observedFrequency: asNumber(b.observed_frequency),
    ciLow: asNumber(b.ci_low),
    ciHigh: asNumber(b.ci_high),
    sparse: asBoolean(b.sparse),
  }));
  const decileBest = ((raw.decile_best ?? []) as Array<Record<string, unknown>>).map(
    normalizeDecile,
  );
  const decileWorst = ((raw.decile_worst ?? []) as Array<Record<string, unknown>>).map(
    normalizeDecile,
  );

  // Headline = the all-time window. The bootstrap CI rides along on the
  // manifest if the Python build emitted `headline_brier`; otherwise it
  // is left null (the page says so rather than inventing an interval).
  const allTime = aggregateBrier.find((w) => w.label === "all-time");
  const headlineRaw = (raw.headline_brier ?? {}) as Record<string, unknown>;
  const headlineBrier = makeHeadlineBrier(
    allTime?.meanBrier ?? null,
    allTime?.n ?? Number(counts.resolved_binary ?? 0),
    { ciLow: asNumber(headlineRaw.ci_low), ciHigh: asNumber(headlineRaw.ci_high) },
  );
  const outcomeBaseRate =
    asNumber(raw.outcome_base_rate) ?? baseRateFromCurve(calibrationCurve);

  const venues = ((raw.venues ?? []) as Array<Record<string, unknown>>).map(normalizeFacet);
  const horizons = ((raw.horizons ?? []) as Array<Record<string, unknown>>).map(
    normalizeFacet,
  );

  const indexRaw = raw.resolution_index;
  let resolvedIndex: ResolvedAuditEntry[];
  let resolvedIndexComplete: boolean;
  if (Array.isArray(indexRaw)) {
    resolvedIndex = dedupeAuditEntries(
      (indexRaw as Array<Record<string, unknown>>).map(normalizeAuditEntry),
    );
    resolvedIndexComplete = true;
  } else {
    // Fall back to the decile views: still auditable, but only the
    // extremes — the page discloses the gap.
    resolvedIndex = dedupeAuditEntries(
      [...decileBest, ...decileWorst].map(decileToAuditEntry),
    );
    resolvedIndexComplete = false;
  }

  return {
    schema: asString(raw.schema, PUBLIC_CALIBRATION_SCHEMA),
    schemaVersion: Number(raw.schema_version ?? PUBLIC_CALIBRATION_SCHEMA_VERSION),
    generatedAt: asString(raw.generated_at, new Date().toISOString()),
    source,
    publishHorizonDays: Number(raw.publish_horizon_days ?? STALE_DAYS),
    sparseBinThreshold: Number(raw.sparse_bin_threshold ?? SPARSE_BIN_THRESHOLD),
    bootstrapIterations: Number(raw.bootstrap_iterations ?? 0),
    ciLevel: Number(raw.ci_level ?? 0.9),
    binCount: Number(raw.bin_count ?? 10),
    counts: {
      total: Number(counts.total ?? 0),
      resolvedBinary: Number(counts.resolved_binary ?? 0),
      withdrawn: Number(counts.withdrawn ?? 0),
      staleUnresolved: Number(counts.stale_unresolved ?? 0),
      continuous: Number(counts.continuous ?? 0),
    },
    withdrawnRate: asNumber(raw.withdrawn_rate),
    resolutionSetHash: asString(raw.resolution_set_hash),
    binaryMetricName: asString(raw.binary_metric_name, "brier_score"),
    continuousMetricName: asString(raw.continuous_metric_name, "quadratic_loss"),
    aggregateBrier,
    calibrationCurve,
    calibrationSlope: {
      slope: asNumber(slope.slope),
      ciLow: asNumber(slope.ci_low),
      ciHigh: asNumber(slope.ci_high),
      sampleSize: Number(slope.sample_size ?? 0),
    },
    decileBest,
    decileWorst,
    continuousQuadraticLoss: asNumber(raw.continuous_quadratic_loss),
    domains: ((raw.domains ?? []) as unknown[]).map((d) => asString(d)).filter(Boolean),
    methods: ((raw.methods ?? []) as Array<Record<string, unknown>>).map((m) => ({
      name: asString(m.name),
      version: asString(m.version),
      n: Number(m.n ?? 0),
    })),
    venues,
    horizons,
    headlineBrier,
    outcomeBaseRate,
    resolvedIndex,
    resolvedIndexComplete,
    filter: {
      domain: typeof filter.domain === "string" ? filter.domain : null,
      methodName: typeof filter.method_name === "string" ? filter.method_name : null,
      methodVersion:
        typeof filter.method_version === "string" ? filter.method_version : null,
      venue: typeof filter.venue === "string" ? filter.venue : null,
      horizon: typeof filter.horizon === "string" ? filter.horizon : null,
    },
    notes: ((raw.notes ?? []) as unknown[]).map((n) => asString(n)).filter(Boolean),
  };
}

function normalizeDecile(raw: Record<string, unknown>): DecileEntry {
  return {
    predictionId: asString(raw.prediction_id),
    marketId: asString(raw.market_id),
    headline: asString(raw.headline),
    marketTitle: asString(raw.market_title),
    marketUrl: typeof raw.market_url === "string" ? raw.market_url : null,
    domain: asString(raw.domain),
    methodName: typeof raw.method_name === "string" ? raw.method_name : null,
    methodVersion: typeof raw.method_version === "string" ? raw.method_version : null,
    probabilityYes: Number(raw.probability_yes ?? 0),
    outcome: asString(raw.outcome),
    brier: Number(raw.brier ?? 0),
    resolvedAt: typeof raw.resolved_at === "string" ? raw.resolved_at : null,
  };
}

// ── Live fallback: read directly from Prisma when no manifest is on disk ──

function marketUrl(source: string, externalId: string | null): string | null {
  if (!externalId) return null;
  if (source === "POLYMARKET") return `https://polymarket.com/event/${externalId}`;
  if (source === "KALSHI") return `https://kalshi.com/markets/${externalId}`;
  return null;
}

type LiveRow = {
  predictionId: string;
  marketId: string;
  headline: string;
  marketTitle: string;
  marketUrl: string | null;
  domain: string;
  venue: string | null;
  horizonKey: string;
  probabilityYes: number;
  outcome: string;
  brier: number;
  logLoss: number | null;
  resolvedAt: Date;
  publishedAt: Date;
};

async function buildLiveManifest(filter: CalibrationFilter): Promise<PublicCalibrationManifest> {
  const predictions = await db.forecastPrediction.findMany({
    where: { status: "PUBLISHED" },
    include: {
      market: true,
      resolution: true,
    },
    take: 5000,
    orderBy: { createdAt: "desc" },
  });

  // Pass 1: classify every published prediction with NO filter applied,
  // so the slice facets always list every option even when a slice is
  // active (a filter must never make its own chip disappear).
  const resolvedAll: LiveRow[] = [];
  const withdrawnRows: Array<{ domain: string }> = [];
  const staleRows: Array<{ domain: string }> = [];
  const now = Date.now();
  for (const pred of predictions) {
    const market = pred.market;
    const resolution = pred.resolution;
    const domain = asString(market?.category ?? "", "");
    if (resolution && resolution.marketOutcome === "CANCELLED") {
      withdrawnRows.push({ domain });
      continue;
    }
    if (!resolution) {
      const ageMs = now - pred.createdAt.getTime();
      if (ageMs >= STALE_DAYS * 86_400_000) staleRows.push({ domain });
      continue;
    }
    if (resolution.marketOutcome !== "YES" && resolution.marketOutcome !== "NO") continue;
    const probability = asNumber(pred.probabilityYes);
    const brier = asNumber(resolution.brierScore);
    if (probability === null || brier === null) continue;
    const publishedAt = pred.createdAt;
    const resolvedAt = resolution.resolvedAt;
    const elapsedDays = Math.max(
      0,
      (resolvedAt.getTime() - publishedAt.getTime()) / 86_400_000,
    );
    resolvedAll.push({
      predictionId: pred.id,
      marketId: pred.marketId,
      headline: pred.headline,
      marketTitle: market?.title ?? pred.headline,
      marketUrl: market ? marketUrl(market.source, market.externalId) : null,
      domain,
      venue: market ? venueFromSource(market.source) : null,
      horizonKey: horizonKeyForDays(elapsedDays),
      probabilityYes: probability,
      outcome: resolution.marketOutcome,
      brier,
      logLoss: asNumber(resolution.logLoss),
      resolvedAt,
      publishedAt,
    });
  }

  // Facets are computed over the full resolved set (pre-slice).
  const domains = Array.from(
    new Set(resolvedAll.map((r) => r.domain).filter(Boolean)),
  ).sort();
  const venues = facetCounts(resolvedAll, (r) => r.venue);
  const horizons = facetCounts(resolvedAll, (r) => r.horizonKey, horizonLabel);

  // Pass 2: apply the requested slice for the metrics themselves.
  const matchesDomain = (d: string) => !filter.domain || filter.domain === d;
  const liveRows = resolvedAll.filter(
    (r) =>
      matchesDomain(r.domain) &&
      (!filter.venue || filter.venue === r.venue) &&
      (!filter.horizon || filter.horizon === r.horizonKey),
  );
  const withdrawn = withdrawnRows.filter((r) => matchesDomain(r.domain)).length;
  const staleUnresolved = staleRows.filter((r) => matchesDomain(r.domain)).length;

  const aggregateBrier = computeAggregateBrierLive(liveRows, now);
  const decileBest = liveRows
    .slice()
    .sort((a, b) => a.brier - b.brier)
    .slice(0, 10)
    .map(toDecileEntry);
  const decileWorst = liveRows
    .slice()
    .sort((a, b) => b.brier - a.brier)
    .slice(0, 10)
    .map(toDecileEntry);

  const denom = liveRows.length + withdrawn;
  const withdrawnRate = denom > 0 ? withdrawn / denom : null;
  const resolutionSetHash = liveResolutionHash(liveRows);

  const allTime = aggregateBrier.find((w) => w.label === "all-time");
  const headlineBrier = makeHeadlineBrier(
    allTime?.meanBrier ?? null,
    liveRows.length,
    bootstrapMeanCi(liveRows.map((r) => r.brier)),
  );
  const outcomeBaseRate =
    liveRows.length > 0
      ? liveRows.filter((r) => r.outcome === "YES").length / liveRows.length
      : null;
  const resolvedIndex = dedupeAuditEntries(liveRows.map(toAuditEntry));

  const notes: string[] = [
    "Live fallback: the nightly calibration manifest is not on disk. The binned reliability curve, per-method attribution and continuous-market metric are not available until the scheduler runs; the headline Brier, its bootstrap CI and the resolution audit below are computed live from the database.",
  ];
  if (staleUnresolved > 0) {
    notes.push(`${staleUnresolved} forecasts are unresolved-but-stale; flagged, not dropped.`);
  }
  if (withdrawn > 0) {
    notes.push(
      `${withdrawn} forecasts are withdrawn or revoked. Excluded from calibration metrics; counted toward the withdrawn rate.`,
    );
  }

  return {
    schema: PUBLIC_CALIBRATION_SCHEMA,
    schemaVersion: PUBLIC_CALIBRATION_SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    source: "live",
    publishHorizonDays: STALE_DAYS,
    sparseBinThreshold: SPARSE_BIN_THRESHOLD,
    bootstrapIterations: 0,
    ciLevel: HEADLINE_CI_LEVEL,
    binCount: 0,
    counts: {
      total: liveRows.length + withdrawn + staleUnresolved,
      resolvedBinary: liveRows.length,
      withdrawn,
      staleUnresolved,
      continuous: 0,
    },
    withdrawnRate,
    resolutionSetHash,
    binaryMetricName: "brier_score",
    continuousMetricName: "quadratic_loss",
    aggregateBrier,
    calibrationCurve: [],
    calibrationSlope: {
      slope: null,
      ciLow: null,
      ciHigh: null,
      sampleSize: liveRows.length,
    },
    decileBest,
    decileWorst,
    continuousQuadraticLoss: null,
    domains,
    methods: [],
    venues,
    horizons,
    headlineBrier,
    outcomeBaseRate,
    resolvedIndex,
    resolvedIndexComplete: true,
    filter: {
      domain: filter.domain ?? null,
      methodName: filter.methodName ?? null,
      methodVersion: filter.methodVersion ?? null,
      venue: filter.venue ?? null,
      horizon: filter.horizon ?? null,
    },
    notes,
  };
}

function toDecileEntry(row: LiveRow): DecileEntry {
  return {
    predictionId: row.predictionId,
    marketId: row.marketId,
    headline: row.headline,
    marketTitle: row.marketTitle,
    marketUrl: row.marketUrl,
    domain: row.domain,
    methodName: null,
    methodVersion: null,
    probabilityYes: row.probabilityYes,
    outcome: row.outcome,
    brier: row.brier,
    resolvedAt: isoOrNull(row.resolvedAt),
  };
}

function toAuditEntry(row: LiveRow): ResolvedAuditEntry {
  return {
    predictionId: row.predictionId,
    headline: row.headline,
    marketTitle: row.marketTitle,
    marketUrl: row.marketUrl,
    domain: row.domain,
    venue: row.venue,
    methodName: null,
    methodVersion: null,
    probabilityYes: row.probabilityYes,
    outcome: row.outcome,
    brier: row.brier,
    resolvedAt: isoOrNull(row.resolvedAt),
  };
}

function computeAggregateBrierLive(rows: LiveRow[], nowMs: number): BrierWindow[] {
  const windows: Array<{ label: string; days: number | null }> = [
    { label: "all-time", days: null },
    { label: "30d", days: 30 },
    { label: "90d", days: 90 },
    { label: "365d", days: 365 },
  ];
  return windows.map(({ label, days }) => {
    const cutoff = days === null ? -Infinity : nowMs - days * 86_400_000;
    const bucket = rows.filter((r) => r.resolvedAt.getTime() >= cutoff);
    const briers = bucket.map((r) => r.brier);
    const losses = bucket.map((r) => r.logLoss).filter((v): v is number => v !== null);
    return {
      label,
      days,
      n: bucket.length,
      meanBrier: briers.length > 0 ? briers.reduce((a, b) => a + b, 0) / briers.length : null,
      meanLogLoss: losses.length > 0 ? losses.reduce((a, b) => a + b, 0) / losses.length : null,
    };
  });
}

function round12(value: number): number {
  return Number(value.toPrecision(12));
}

function liveResolutionHash(rows: LiveRow[]): string {
  const sorted = rows.slice().sort((a, b) => a.predictionId.localeCompare(b.predictionId));
  const payload = sorted.map((r) => ({
    id: r.predictionId,
    p: round12(r.probabilityYes),
    o: r.outcome,
    t: r.resolvedAt.toISOString().replace(".000Z", "Z"),
    b: round12(r.brier),
  }));
  const canon = JSON.stringify(payload);
  return createHash("sha256").update(canon, "utf8").digest("hex");
}

// ── Filtering ─────────────────────────────────────────────────────────────

function applyFilter(
  manifest: PublicCalibrationManifest,
  filter: CalibrationFilter,
): PublicCalibrationManifest {
  const isFiltered = Boolean(
    filter.domain ||
      filter.methodName ||
      filter.methodVersion ||
      filter.venue ||
      filter.horizon,
  );
  if (!isFiltered) return manifest;
  // Only the decile + audit views are easy to re-filter client-side
  // without re-running the bootstrap. For a real sliced drill-down the
  // manifest exposes the filter slot — the Python build_manifest is the
  // authoritative path. Until a sliced manifest is published, we keep the
  // all-cohort curve and headline and record the filter so the page can
  // render a "slice pending" notice rather than imply the headline moved.
  const matchEntry = (e: DecileEntry): boolean => {
    if (filter.domain && e.domain !== filter.domain) return false;
    if (filter.methodName && e.methodName !== filter.methodName) return false;
    if (filter.methodVersion && e.methodVersion !== filter.methodVersion) return false;
    if (filter.venue && venueFromUrl(e.marketUrl) !== filter.venue) return false;
    return true;
  };
  const matchAudit = (e: ResolvedAuditEntry): boolean => {
    if (filter.domain && e.domain !== filter.domain) return false;
    if (filter.methodName && e.methodName !== filter.methodName) return false;
    if (filter.methodVersion && e.methodVersion !== filter.methodVersion) return false;
    if (filter.venue && (e.venue ?? venueFromUrl(e.marketUrl)) !== filter.venue) {
      return false;
    }
    return true;
  };
  return {
    ...manifest,
    filter: {
      domain: filter.domain ?? null,
      methodName: filter.methodName ?? null,
      methodVersion: filter.methodVersion ?? null,
      venue: filter.venue ?? null,
      horizon: filter.horizon ?? null,
    },
    decileBest: manifest.decileBest.filter(matchEntry),
    decileWorst: manifest.decileWorst.filter(matchEntry),
    resolvedIndex: manifest.resolvedIndex.filter(matchAudit),
    notes: [
      ...manifest.notes,
      "Filter applied to the decile and audit views only. The headline Brier and reliability curve are the all-cohort numbers from the published manifest — re-run the Python build for a fully sliced manifest. (The resolution-horizon slice needs publish timestamps the disk manifest does not carry; it is recorded but not applied here.)",
    ],
  };
}

// ── Public entry points ───────────────────────────────────────────────────

export async function loadPublicCalibrationManifest(
  filter: CalibrationFilter = {},
): Promise<PublicCalibrationManifest> {
  const fromDisk = readManifestFromDisk();
  if (fromDisk) return applyFilter(fromDisk, filter);
  const live = await buildLiveManifest(filter);
  return live;
}

export function manifestPathForTests(): string {
  return manifestPath();
}

// ══════════════════════════════════════════════════════════════════════════
// Horizon calibration — calibration sliced by time-to-resolution.
//
// A 7-day forecast and a 1-year forecast are different animals; a single
// Brier hides the decay. This section buckets resolved forecasts by their
// horizon (publish -> resolution elapsed time), scores each bucket, and
// derives the firm's empirically *useful prediction horizon*.
//
// Source-of-truth precedence mirrors the manifest above:
//   1. `horizon_calibration` block on the nightly manifest, when present —
//      the auditable path (Python `noosphere.coherence.horizon_calibration`
//      owns the math).
//   2. Live DB fallback. The disk manifest's resolved index does not carry
//      publish timestamps, so when the block is absent we recompute from
//      Prisma — the same live-fallback discipline `buildLiveManifest` uses
//      for the headline. Method attribution is unavailable on this path.
//
// The 5-bucket scheme {<7d, 7-30d, 30-90d, 90-365d, >365d} is the one
// prompt 35 specifies, and is intentionally finer than the 4-bucket
// `HORIZON_BUCKETS` the slice-filter chips use — keep them distinct.
// ══════════════════════════════════════════════════════════════════════════

/** The uninformative-forecaster Brier (random / always-50%). A bucket
 *  "beats chance" when its bootstrap Brier CI sits entirely below this. */
export const HORIZON_CHANCE_BRIER = 0.25;

/** Below this many resolved forecasts in a bucket we report the sample
 *  size only — never a slope, never a "beats chance" verdict. */
export const HORIZON_MIN_BUCKET_N = 10;

export const HORIZON_CALIBRATION_BUCKETS: ReadonlyArray<{
  key: string;
  label: string;
  minDays: number;
  maxDays: number | null;
}> = [
  { key: "lt7", label: "< 7 days", minDays: 0, maxDays: 7 },
  { key: "7-30", label: "7–30 days", minDays: 7, maxDays: 30 },
  { key: "30-90", label: "30–90 days", minDays: 30, maxDays: 90 },
  { key: "90-365", label: "90–365 days", minDays: 90, maxDays: 365 },
  { key: "gt365", label: "> 365 days", minDays: 365, maxDays: null },
];

export type HorizonBucketCalibration = {
  key: string;
  label: string;
  n: number;
  meanBrier: number | null;
  brierCiLow: number | null;
  brierCiHigh: number | null;
  /** null below HORIZON_MIN_BUCKET_N — the honesty constraint, not a gap. */
  slope: number | null;
  slopeCiLow: number | null;
  slopeCiHigh: number | null;
  baseRate: number | null;
  climatologyBrier: number | null;
  beatsChance: boolean;
  note: string;
};

export type UsefulHorizon = {
  /** Upper edge (days) of the longest run of buckets, contiguous from
   *  zero, that each beat chance. null = either no decay observed or no
   *  horizon could be established — disambiguated by the flag + rationale. */
  horizonDays: number | null;
  horizonLabel: string;
  limitingBucketKey: string | null;
  rationale: string;
  beatsChanceAtEveryHorizon: boolean;
};

export type MethodHorizonCell = {
  methodName: string;
  methodVersion: string;
  horizonKey: string;
  horizonLabel: string;
  n: number;
  meanBrier: number | null;
  slope: number | null;
  beatsChance: boolean;
};

export type HorizonCalibration = {
  schema: string;
  generatedAt: string;
  source: "manifest" | "live";
  chanceBrier: number;
  minBucketN: number;
  bootstrapIterations: number;
  ciLevel: number;
  nTotal: number;
  buckets: HorizonBucketCalibration[];
  usefulHorizon: UsefulHorizon;
  usefulHorizonByDomain: Record<string, UsefulHorizon>;
  methodHorizon: MethodHorizonCell[];
  domains: string[];
  notes: string[];
};

/** Advisory verdict for a forecast a founder is about to issue. */
export type HorizonWarningVerdict = {
  shouldWarn: boolean;
  domain: string;
  horizonDays: number;
  usefulHorizonDays: number | null;
  message: string;
};

/** Bucket a publish->resolution elapsed-days value into a 5-bucket key. */
export function horizonCalibrationBucketKey(days: number): string {
  const d = Math.max(0, days);
  for (const bucket of HORIZON_CALIBRATION_BUCKETS) {
    if (d >= bucket.minDays && (bucket.maxDays === null || d < bucket.maxDays)) {
      return bucket.key;
    }
  }
  return HORIZON_CALIBRATION_BUCKETS[HORIZON_CALIBRATION_BUCKETS.length - 1].key;
}

function horizonBucketLabel(key: string): string {
  return HORIZON_CALIBRATION_BUCKETS.find((b) => b.key === key)?.label ?? key;
}

// ── Pure estimators (mirror noosphere.evaluation.method_track_record) ──────

type SlopePoint = { p: number; y: number };

/** OLS slope of outcome ~ probability. null when n < 2 or p is constant. */
export function olsSlope(points: SlopePoint[]): number | null {
  const n = points.length;
  if (n < 2) return null;
  let meanX = 0;
  let meanY = 0;
  for (const q of points) {
    meanX += q.p;
    meanY += q.y;
  }
  meanX /= n;
  meanY /= n;
  let num = 0;
  let den = 0;
  for (const q of points) {
    const dx = q.p - meanX;
    num += dx * (q.y - meanY);
    den += dx * dx;
  }
  if (den <= 0) return null;
  return num / den;
}

/** Non-parametric percentile bootstrap CI on the OLS slope. (None, None)
 *  below n=5, matching `method_track_record.bootstrap_slope_ci`. */
export function bootstrapSlopeCi(
  points: SlopePoint[],
  options: { iterations?: number; ciLevel?: number; seed?: number } = {},
): { ciLow: number | null; ciHigh: number | null } {
  const iterations = options.iterations ?? 200;
  const ciLevel = options.ciLevel ?? 0.9;
  const seed = options.seed ?? 0xc0dec0de;
  const n = points.length;
  if (n < 5) return { ciLow: null, ciHigh: null };
  const rand = mulberry32(seed);
  const slopes: number[] = [];
  for (let it = 0; it < iterations; it += 1) {
    const sample: SlopePoint[] = [];
    for (let i = 0; i < n; i += 1) sample.push(points[Math.floor(rand() * n)]);
    const s = olsSlope(sample);
    if (s !== null) slopes.push(s);
  }
  if (slopes.length < iterations / 2) return { ciLow: null, ciHigh: null };
  slopes.sort((a, b) => a - b);
  const alpha = (1 - ciLevel) / 2;
  const loIdx = Math.max(0, Math.floor(alpha * slopes.length));
  const hiIdx = Math.min(slopes.length - 1, Math.ceil((1 - alpha) * slopes.length) - 1);
  return { ciLow: slopes[loIdx], ciHigh: slopes[hiIdx] };
}

// ── Bucket + decay computation (shared by manifest + live paths) ──────────

type HorizonRow = {
  domain: string;
  horizonKey: string;
  probabilityYes: number;
  outcomeY: number; // 1 = YES, 0 = NO
  brier: number;
  methodName: string | null;
  methodVersion: string | null;
};

function hashKey(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i += 1) {
    h = (Math.imul(h, 31) + key.charCodeAt(i)) | 0;
  }
  return h >>> 0;
}

function computeHorizonBucket(
  spec: (typeof HORIZON_CALIBRATION_BUCKETS)[number],
  rows: HorizonRow[],
  seedBase: number,
): HorizonBucketCalibration {
  const n = rows.length;
  if (n === 0) {
    return {
      key: spec.key,
      label: spec.label,
      n: 0,
      meanBrier: null,
      brierCiLow: null,
      brierCiHigh: null,
      slope: null,
      slopeCiLow: null,
      slopeCiHigh: null,
      baseRate: null,
      climatologyBrier: null,
      beatsChance: false,
      note: "no resolved forecasts in this horizon bucket",
    };
  }
  const briers = rows.map((r) => r.brier);
  const meanBrier = briers.reduce((a, b) => a + b, 0) / n;
  const baseRate = rows.reduce((a, r) => a + r.outcomeY, 0) / n;
  const climatologyBrier = baseRate * (1 - baseRate);

  if (n < HORIZON_MIN_BUCKET_N) {
    return {
      key: spec.key,
      label: spec.label,
      n,
      meanBrier,
      brierCiLow: null,
      brierCiHigh: null,
      slope: null,
      slopeCiLow: null,
      slopeCiHigh: null,
      baseRate,
      climatologyBrier,
      beatsChance: false,
      note: `n=${n} < ${HORIZON_MIN_BUCKET_N} — sample size only, no slope or CI`,
    };
  }

  const seed = (seedBase ^ hashKey(spec.key)) >>> 0;
  const { ciLow: brierCiLow, ciHigh: brierCiHigh } = bootstrapMeanCi(briers, {
    iterations: 400,
    ciLevel: 0.9,
    seed,
  });
  const points: SlopePoint[] = rows.map((r) => ({ p: r.probabilityYes, y: r.outcomeY }));
  const slope = olsSlope(points);
  const { ciLow: slopeCiLow, ciHigh: slopeCiHigh } = bootstrapSlopeCi(points, {
    iterations: 200,
    ciLevel: 0.9,
    seed,
  });
  const beatsChance = brierCiHigh !== null && brierCiHigh < HORIZON_CHANCE_BRIER;
  const note = beatsChance
    ? `bootstrap Brier CI upper bound ${brierCiHigh!.toFixed(3)} < ${HORIZON_CHANCE_BRIER} — beats chance`
    : `bootstrap Brier CI upper bound ${
        brierCiHigh === null ? "—" : brierCiHigh.toFixed(3)
      } does not clear ${HORIZON_CHANCE_BRIER} — not distinguishable from chance`;

  return {
    key: spec.key,
    label: spec.label,
    n,
    meanBrier,
    brierCiLow,
    brierCiHigh,
    slope,
    slopeCiLow,
    slopeCiHigh,
    baseRate,
    climatologyBrier,
    beatsChance,
    note,
  };
}

function computeHorizonBuckets(rows: HorizonRow[], seedBase: number): HorizonBucketCalibration[] {
  return HORIZON_CALIBRATION_BUCKETS.map((spec) =>
    computeHorizonBucket(
      spec,
      rows.filter((r) => r.horizonKey === spec.key),
      seedBase,
    ),
  );
}

function edgeLabel(edge: number | null): string {
  return edge === null ? "no useful horizon" : `${edge.toFixed(0)} days`;
}

/** Walk buckets short -> long; the useful horizon ends at the first bucket
 *  that fails to beat chance (or cannot be assessed). Contiguous from zero. */
export function computeUsefulHorizon(buckets: HorizonBucketCalibration[]): UsefulHorizon {
  const byKey = new Map(buckets.map((b) => [b.key, b]));
  let lastPassEdge: number | null = null;
  let lastPassLabel = "";
  for (const spec of HORIZON_CALIBRATION_BUCKETS) {
    const cal = byKey.get(spec.key);
    if (!cal || cal.n === 0) {
      return {
        horizonDays: lastPassEdge,
        horizonLabel: edgeLabel(lastPassEdge),
        limitingBucketKey: spec.key,
        rationale: `no resolved forecasts in the ${spec.label} bucket — useful horizon cannot be extended past the last measured bucket`,
        beatsChanceAtEveryHorizon: false,
      };
    }
    if (cal.n < HORIZON_MIN_BUCKET_N) {
      return {
        horizonDays: lastPassEdge,
        horizonLabel: edgeLabel(lastPassEdge),
        limitingBucketKey: spec.key,
        rationale: `the ${spec.label} bucket has only n=${cal.n} resolved forecasts (< ${HORIZON_MIN_BUCKET_N}) — not enough to claim signal at this horizon`,
        beatsChanceAtEveryHorizon: false,
      };
    }
    if (!cal.beatsChance) {
      return {
        horizonDays: lastPassEdge,
        horizonLabel: edgeLabel(lastPassEdge),
        limitingBucketKey: spec.key,
        rationale: `calibration in the ${spec.label} bucket is not distinguishable from chance (${cal.note})`,
        beatsChanceAtEveryHorizon: false,
      };
    }
    lastPassEdge = spec.maxDays;
    lastPassLabel = spec.label;
  }
  return {
    horizonDays: null,
    horizonLabel: "no decay observed",
    limitingBucketKey: null,
    rationale: `calibration beats chance at every measured horizon, including the ${lastPassLabel} bucket — no useful-horizon ceiling found`,
    beatsChanceAtEveryHorizon: true,
  };
}

/** Decide whether issuing a forecast in `domain` at `horizonDays` out
 *  should surface the soft warning. Advisory only — the founder may
 *  knowingly proceed. Mirrors `horizon_calibration.horizon_warning_for`. */
export function horizonWarningFor(
  domain: string,
  horizonDays: number,
  calibration: HorizonCalibration,
): HorizonWarningVerdict {
  const domainKey = domain || "";
  const perDomain = calibration.usefulHorizonByDomain[domainKey];
  const useful = perDomain ?? calibration.usefulHorizon;
  const usedDomain = Boolean(perDomain);
  const ceiling = useful.horizonDays;

  if (useful.beatsChanceAtEveryHorizon || ceiling === null) {
    return {
      shouldWarn: false,
      domain: domainKey,
      horizonDays,
      usefulHorizonDays: ceiling,
      message: "",
    };
  }
  const shouldWarn = horizonDays > ceiling;
  const scope = usedDomain && domainKey ? `for ${domainKey}` : "firm-wide";
  const message = shouldWarn
    ? `Our calibration drops below significance at horizons > ${ceiling.toFixed(
        0,
      )} days ${scope} — are you sure? Beyond this horizon, issue the forecast with the explicit "low confidence, long horizon" framing.`
    : "";
  return { shouldWarn, domain: domainKey, horizonDays, usefulHorizonDays: ceiling, message };
}

// ── Disk path: read a `horizon_calibration` block when the manifest has one ─

function normalizeUsefulHorizon(raw: Record<string, unknown>): UsefulHorizon {
  return {
    horizonDays: asNumber(raw.horizon_days),
    horizonLabel: asString(raw.horizon_label, "no useful horizon"),
    limitingBucketKey:
      typeof raw.limiting_bucket_key === "string" ? raw.limiting_bucket_key : null,
    rationale: asString(raw.rationale),
    beatsChanceAtEveryHorizon: asBoolean(raw.beats_chance_at_every_horizon),
  };
}

function readHorizonFromDisk(): HorizonCalibration | null {
  let text: string;
  try {
    text = fs.readFileSync(manifestPath(), "utf8");
  } catch {
    return null;
  }
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(text) as Record<string, unknown>;
  } catch {
    return null;
  }
  const block = raw.horizon_calibration;
  if (!block || typeof block !== "object") return null;
  const hc = block as Record<string, unknown>;
  const buckets: HorizonBucketCalibration[] = (
    (hc.buckets ?? []) as Array<Record<string, unknown>>
  ).map((b) => ({
    key: asString(b.key),
    label: asString(b.label, asString(b.key)),
    n: Number(b.n ?? 0),
    meanBrier: asNumber(b.mean_brier),
    brierCiLow: asNumber(b.brier_ci_low),
    brierCiHigh: asNumber(b.brier_ci_high),
    slope: asNumber(b.slope),
    slopeCiLow: asNumber(b.slope_ci_low),
    slopeCiHigh: asNumber(b.slope_ci_high),
    baseRate: asNumber(b.base_rate),
    climatologyBrier: asNumber(b.climatology_brier),
    beatsChance: asBoolean(b.beats_chance),
    note: asString(b.note),
  }));
  const byDomainRaw = (hc.useful_horizon_by_domain ?? {}) as Record<
    string,
    Record<string, unknown>
  >;
  const usefulHorizonByDomain: Record<string, UsefulHorizon> = {};
  for (const [domain, value] of Object.entries(byDomainRaw)) {
    usefulHorizonByDomain[domain] = normalizeUsefulHorizon(value);
  }
  const methodHorizon: MethodHorizonCell[] = (
    (hc.method_horizon ?? []) as Array<Record<string, unknown>>
  ).map((c) => ({
    methodName: asString(c.method_name),
    methodVersion: asString(c.method_version),
    horizonKey: asString(c.horizon_key),
    horizonLabel: asString(c.horizon_label, asString(c.horizon_key)),
    n: Number(c.n ?? 0),
    meanBrier: asNumber(c.mean_brier),
    slope: asNumber(c.slope),
    beatsChance: asBoolean(c.beats_chance),
  }));
  return {
    schema: asString(hc.schema, "theseus.horizon_calibration.v1"),
    generatedAt: asString(hc.generated_at, new Date().toISOString()),
    source: "manifest",
    chanceBrier: Number(hc.chance_brier ?? HORIZON_CHANCE_BRIER),
    minBucketN: Number(hc.min_bucket_n ?? HORIZON_MIN_BUCKET_N),
    bootstrapIterations: Number(hc.bootstrap_iterations ?? 0),
    ciLevel: Number(hc.ci_level ?? 0.9),
    nTotal: Number(hc.n_total ?? 0),
    buckets,
    usefulHorizon: normalizeUsefulHorizon(
      (hc.useful_horizon ?? {}) as Record<string, unknown>,
    ),
    usefulHorizonByDomain,
    methodHorizon,
    domains: ((hc.domains ?? []) as unknown[]).map((d) => asString(d)).filter(Boolean),
    notes: ((hc.notes ?? []) as unknown[]).map((n) => asString(n)).filter(Boolean),
  };
}

// ── Live fallback: recompute horizon calibration from Prisma ───────────────

async function buildLiveHorizonCalibration(
  filter: { domain?: string | null } = {},
): Promise<HorizonCalibration> {
  const predictions = await db.forecastPrediction.findMany({
    where: { status: "PUBLISHED" },
    include: { market: true, resolution: true },
    take: 5000,
    orderBy: { createdAt: "desc" },
  });

  let nonPositive = 0;
  const rows: HorizonRow[] = [];
  for (const pred of predictions) {
    const resolution = pred.resolution;
    if (!resolution) continue;
    if (resolution.marketOutcome !== "YES" && resolution.marketOutcome !== "NO") continue;
    const probability = asNumber(pred.probabilityYes);
    const brier = asNumber(resolution.brierScore);
    if (probability === null || brier === null) continue;
    const elapsedDays =
      (resolution.resolvedAt.getTime() - pred.createdAt.getTime()) / 86_400_000;
    if (elapsedDays <= 0) nonPositive += 1;
    const horizonDays = Math.max(0, elapsedDays);
    rows.push({
      domain: asString(pred.market?.category ?? "", ""),
      horizonKey: horizonCalibrationBucketKey(horizonDays),
      probabilityYes: probability,
      outcomeY: resolution.marketOutcome === "YES" ? 1 : 0,
      brier,
      // ForecastPrediction carries no conclusion link on the live path, so
      // method attribution is unavailable here — see note below.
      methodName: null,
      methodVersion: null,
    });
  }

  const seedBase = 0x40120350;
  const scoped = filter.domain
    ? rows.filter((r) => r.domain === filter.domain)
    : rows;
  const buckets = computeHorizonBuckets(scoped, seedBase);
  const usefulHorizon = computeUsefulHorizon(buckets);

  // Per-domain useful horizons — the new-forecast warning is per-domain.
  const byDomain = new Map<string, HorizonRow[]>();
  for (const r of rows) {
    const list = byDomain.get(r.domain) ?? [];
    list.push(r);
    byDomain.set(r.domain, list);
  }
  const usefulHorizonByDomain: Record<string, UsefulHorizon> = {};
  for (const [domain, domainRows] of byDomain) {
    usefulHorizonByDomain[domain] = computeUsefulHorizon(
      computeHorizonBuckets(domainRows, seedBase),
    );
  }

  const notes: string[] = [
    "Live fallback: the nightly manifest carries no horizon_calibration block. Per-bucket Brier, calibration slope, bootstrap CIs and the useful-horizon estimate are recomputed live from the database; the canonical estimator is noosphere.coherence.horizon_calibration.",
    "Method × horizon attribution requires the nightly manifest — published forecasts carry no method→outcome link on the live path.",
  ];
  const thin = scoped.length
    ? buckets.filter((b) => b.n > 0 && b.n < HORIZON_MIN_BUCKET_N).length
    : 0;
  if (thin > 0) {
    notes.push(
      `${thin} horizon bucket(s) have fewer than ${HORIZON_MIN_BUCKET_N} resolved forecasts; sample size is reported but no slope or CI is.`,
    );
  }
  if (nonPositive > 0) {
    notes.push(
      `${nonPositive} forecast(s) resolved at or before their publish time (a backfill artifact); clamped into the < 7 days bucket.`,
    );
  }
  if (usefulHorizon.horizonDays !== null && !usefulHorizon.beatsChanceAtEveryHorizon) {
    notes.push(
      `Useful prediction horizon ends at ${usefulHorizon.horizonLabel} — beyond it, forecasts should carry the explicit "low confidence, long horizon" framing.`,
    );
  }

  return {
    schema: "theseus.horizon_calibration.v1",
    generatedAt: new Date().toISOString(),
    source: "live",
    chanceBrier: HORIZON_CHANCE_BRIER,
    minBucketN: HORIZON_MIN_BUCKET_N,
    bootstrapIterations: 400,
    ciLevel: 0.9,
    nTotal: scoped.length,
    buckets,
    usefulHorizon,
    usefulHorizonByDomain,
    methodHorizon: [],
    domains: Array.from(new Set(rows.map((r) => r.domain).filter(Boolean))).sort(),
    notes,
  };
}

/**
 * Load the horizon-calibration artifact: the manifest's `horizon_calibration`
 * block when present, else a live recompute from Prisma.
 */
export async function loadHorizonCalibration(
  filter: { domain?: string | null } = {},
): Promise<HorizonCalibration> {
  const fromDisk = readHorizonFromDisk();
  if (fromDisk) return fromDisk;
  return buildLiveHorizonCalibration(filter);
}
