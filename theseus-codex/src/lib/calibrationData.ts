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
export const PUBLIC_CALIBRATION_SCHEMA_VERSION = 1;
export const SPARSE_BIN_THRESHOLD = 5;
export const STALE_DAYS = 14;

export type CalibrationFilter = {
  domain?: string | null;
  methodName?: string | null;
  methodVersion?: string | null;
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
    aggregateBrier: ((raw.aggregate_brier ?? []) as Array<Record<string, unknown>>).map((w) => ({
      label: asString(w.label),
      days: w.days === null || w.days === undefined ? null : Number(w.days),
      n: Number(w.n ?? 0),
      meanBrier: asNumber(w.mean_brier),
      meanLogLoss: asNumber(w.mean_log_loss),
    })),
    calibrationCurve: ((raw.calibration_curve ?? []) as Array<Record<string, unknown>>).map((b) => ({
      lo: Number(b.lo ?? 0),
      hi: Number(b.hi ?? 0),
      n: Number(b.n ?? 0),
      meanPredicted: asNumber(b.mean_predicted),
      observedFrequency: asNumber(b.observed_frequency),
      ciLow: asNumber(b.ci_low),
      ciHigh: asNumber(b.ci_high),
      sparse: asBoolean(b.sparse),
    })),
    calibrationSlope: {
      slope: asNumber(slope.slope),
      ciLow: asNumber(slope.ci_low),
      ciHigh: asNumber(slope.ci_high),
      sampleSize: Number(slope.sample_size ?? 0),
    },
    decileBest: ((raw.decile_best ?? []) as Array<Record<string, unknown>>).map(normalizeDecile),
    decileWorst: ((raw.decile_worst ?? []) as Array<Record<string, unknown>>).map(normalizeDecile),
    continuousQuadraticLoss: asNumber(raw.continuous_quadratic_loss),
    domains: ((raw.domains ?? []) as unknown[]).map((d) => asString(d)).filter(Boolean),
    methods: ((raw.methods ?? []) as Array<Record<string, unknown>>).map((m) => ({
      name: asString(m.name),
      version: asString(m.version),
      n: Number(m.n ?? 0),
    })),
    filter: {
      domain: typeof filter.domain === "string" ? filter.domain : null,
      methodName: typeof filter.method_name === "string" ? filter.method_name : null,
      methodVersion: typeof filter.method_version === "string" ? filter.method_version : null,
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

  const liveRows: LiveRow[] = [];
  let withdrawn = 0;
  let staleUnresolved = 0;
  const now = Date.now();
  const staleCutoff = now - STALE_DAYS * 86_400_000;
  for (const pred of predictions) {
    const market = pred.market;
    const resolution = pred.resolution;
    const domain = asString(market?.category ?? "", "");
    if (filter.domain && filter.domain !== domain) continue;
    if (resolution && resolution.marketOutcome === "CANCELLED") {
      withdrawn += 1;
      continue;
    }
    if (!resolution) {
      const ageMs = now - pred.createdAt.getTime();
      if (ageMs >= STALE_DAYS * 86_400_000) staleUnresolved += 1;
      continue;
    }
    if (resolution.marketOutcome !== "YES" && resolution.marketOutcome !== "NO") continue;
    const probability = asNumber(pred.probabilityYes);
    const brier = asNumber(resolution.brierScore);
    if (probability === null || brier === null) continue;
    liveRows.push({
      predictionId: pred.id,
      marketId: pred.marketId,
      headline: pred.headline,
      marketTitle: market?.title ?? pred.headline,
      marketUrl: market ? marketUrl(market.source, market.externalId) : null,
      domain,
      probabilityYes: probability,
      outcome: resolution.marketOutcome,
      brier,
      logLoss: asNumber(resolution.logLoss),
      resolvedAt: resolution.resolvedAt,
      publishedAt: pred.createdAt,
    });
    void staleCutoff; // keep for reference; the loop above counts via age
  }

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

  const notes: string[] = [
    "Live fallback: nightly calibration manifest is not on disk. Method / domain attribution and bootstrap CIs are not available until the scheduler runs.",
  ];
  if (staleUnresolved > 0) {
    notes.push(`${staleUnresolved} forecasts are unresolved-but-stale; flagged, not dropped.`);
  }
  if (withdrawn > 0) {
    notes.push(
      `${withdrawn} forecasts are withdrawn or revoked. Excluded from calibration metrics; counted toward the withdrawn rate.`,
    );
  }

  const domains = Array.from(new Set(liveRows.map((r) => r.domain).filter(Boolean))).sort();

  return {
    schema: PUBLIC_CALIBRATION_SCHEMA,
    schemaVersion: PUBLIC_CALIBRATION_SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    source: "live",
    publishHorizonDays: STALE_DAYS,
    sparseBinThreshold: SPARSE_BIN_THRESHOLD,
    bootstrapIterations: 0,
    ciLevel: 0.9,
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
    filter: {
      domain: filter.domain ?? null,
      methodName: filter.methodName ?? null,
      methodVersion: filter.methodVersion ?? null,
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
  const isFiltered = Boolean(filter.domain || filter.methodName || filter.methodVersion);
  if (!isFiltered) return manifest;
  // Only the decile views are easy to re-filter client-side without
  // re-running bootstrap. For a real per-method drill-down, the manifest
  // already exposes the filter slot — the Python build_manifest is the
  // authoritative path. Until a per-method manifest is published, we
  // return the unfiltered curve with the filter recorded so the page can
  // render a "filter pending" notice.
  const matchEntry = (e: DecileEntry): boolean => {
    if (filter.domain && e.domain !== filter.domain) return false;
    if (filter.methodName && e.methodName !== filter.methodName) return false;
    if (filter.methodVersion && e.methodVersion !== filter.methodVersion) return false;
    return true;
  };
  return {
    ...manifest,
    filter: {
      domain: filter.domain ?? null,
      methodName: filter.methodName ?? null,
      methodVersion: filter.methodVersion ?? null,
    },
    decileBest: manifest.decileBest.filter(matchEntry),
    decileWorst: manifest.decileWorst.filter(matchEntry),
    notes: [
      ...manifest.notes,
      "Filter applied to decile views only. Aggregate Brier and reliability curve are the all-cohort numbers from the published manifest.",
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
