/**
 * Recalibration read path — translates the firm's stated confidence into
 * the track-record-conditional public number.
 *
 * Source-of-truth: the `CalibrationModel` rows written by
 * `noosphere/coherence/recalibration.py` on the weekly recalibration tick.
 * This file is a normalizer + apply layer; it never re-fits the isotonic
 * regression. The Python tick is the only thing that updates the curve.
 *
 * Constraints honoured:
 *
 *   - Domain partitioning. A model fit on `macro` is never applied to
 *     `geopolitics`. Each `(organizationId, domain)` pair has at most one
 *     active row.
 *
 *   - Conservative-by-default. Below the configured sample threshold
 *     (`THESEUS_RECALIBRATION_MIN_SAMPLES`, default 20) the active row
 *     is treated as insufficient and the caller is told to render the
 *     raw number with an "uncalibrated — small sample" tag.
 *
 *   - Founder override. A `RecalibrationOverride` row on a conclusion
 *     suppresses the calibrated display for that conclusion only —
 *     useful when the conclusion is itself the subject of a methodology
 *     change. The override row IS the audit trail.
 *
 *   - Display precision. `formatCalibratedDisplay` never prints the
 *     calibrated number with more decimals than the raw number it sits
 *     beside.
 */

import { db } from "@/lib/db";

export const DEFAULT_RECALIBRATION_MIN_SAMPLES = 20;
export const RECALIBRATION_MIN_SAMPLES_ENV = "THESEUS_RECALIBRATION_MIN_SAMPLES";

export type CalibrationKnots = {
  x: number[];
  y: number[];
};

export type LoadedCalibrationModel = {
  id: string;
  organizationId: string;
  domain: string;
  version: number;
  fitAt: string;
  sampleSize: number;
  resolutionHash: string;
  knots: CalibrationKnots;
};

export type RecalibrateResult = {
  raw: number;
  calibrated: number | null;
  modelId: string | null;
  modelFitAt: string | null;
  modelSampleSize: number | null;
  resolutionHash: string | null;
  domain: string;
  thresholdSamples: number;
  status:
    | "calibrated"
    | "no_model"
    | "insufficient_sample"
    | "domain_missing"
    | "override";
  reason?: string;
};

export function recalibrationMinSamples(): number {
  const raw = process.env[RECALIBRATION_MIN_SAMPLES_ENV]?.trim();
  if (!raw) return DEFAULT_RECALIBRATION_MIN_SAMPLES;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return DEFAULT_RECALIBRATION_MIN_SAMPLES;
  return Math.floor(n);
}

function clamp01(v: number): number {
  if (!Number.isFinite(v)) return 0;
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

/**
 * Apply piecewise-linear knots produced by the Python isotonic fit.
 * `knots.x` is ascending; `knots.y` is non-decreasing. Inputs outside
 * the knot range clamp to the nearest boundary; output is clamped to
 * `[0, 1]`.
 */
export function applyKnots(knots: CalibrationKnots, p: number): number {
  const xs = knots?.x ?? [];
  const ys = knots?.y ?? [];
  if (xs.length === 0 || ys.length === 0 || xs.length !== ys.length) {
    return clamp01(p);
  }
  const x = clamp01(p);
  if (x <= xs[0]) return clamp01(ys[0]);
  if (x >= xs[xs.length - 1]) return clamp01(ys[ys.length - 1]);
  for (let i = 1; i < xs.length; i += 1) {
    if (x <= xs[i]) {
      const x0 = xs[i - 1];
      const x1 = xs[i];
      const y0 = ys[i - 1];
      const y1 = ys[i];
      if (x1 === x0) return clamp01(y1);
      const t = (x - x0) / (x1 - x0);
      return clamp01(y0 + t * (y1 - y0));
    }
  }
  return clamp01(ys[ys.length - 1]);
}

function parseKnots(raw: unknown): CalibrationKnots {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const obj = raw as Record<string, unknown>;
    const x = Array.isArray(obj.x) ? (obj.x as unknown[]) : [];
    const y = Array.isArray(obj.y) ? (obj.y as unknown[]) : [];
    return {
      x: x.map((v) => Number(v)).filter((v) => Number.isFinite(v)),
      y: y.map((v) => Number(v)).filter((v) => Number.isFinite(v)),
    };
  }
  if (typeof raw === "string") {
    try {
      return parseKnots(JSON.parse(raw));
    } catch {
      return { x: [], y: [] };
    }
  }
  return { x: [], y: [] };
}

export async function loadActiveModel(
  domain: string,
  organizationId?: string,
): Promise<LoadedCalibrationModel | null> {
  if (!domain) return null;
  // The Prisma client model is named `calibrationModel`. We accept a
  // missing `organizationId` and pick the most recent active row across
  // tenants — public callers (`/api/public/...`) typically don't carry
  // a tenant hint, and the public site is single-org in practice.
  const where: { domain: string; active: boolean; organizationId?: string } = {
    domain,
    active: true,
  };
  if (organizationId) where.organizationId = organizationId;
  const row = await db.calibrationModel.findFirst({
    where,
    orderBy: { fitAt: "desc" },
  });
  if (!row) return null;
  return {
    id: row.id,
    organizationId: row.organizationId,
    domain: row.domain,
    version: row.version,
    fitAt: row.fitAt instanceof Date ? row.fitAt.toISOString() : String(row.fitAt),
    sampleSize: row.sampleSize,
    resolutionHash: row.resolutionHash,
    knots: parseKnots(row.knots as unknown),
  };
}

export type RecalibrateOptions = {
  organizationId?: string;
  conclusionId?: string;
};

export async function recalibrate(
  rawConfidence: number,
  domain: string,
  opts: RecalibrateOptions = {},
): Promise<RecalibrateResult> {
  const threshold = recalibrationMinSamples();
  const raw = clamp01(rawConfidence);
  const cleanDomain = (domain ?? "").trim();
  if (!cleanDomain) {
    return {
      raw,
      calibrated: null,
      modelId: null,
      modelFitAt: null,
      modelSampleSize: null,
      resolutionHash: null,
      domain: "",
      thresholdSamples: threshold,
      status: "domain_missing",
      reason: "domain not specified — calibration is per-domain by design",
    };
  }
  if (opts.conclusionId) {
    const override = await db.recalibrationOverride.findUnique({
      where: { conclusionId: opts.conclusionId },
    });
    if (override) {
      return {
        raw,
        calibrated: null,
        modelId: null,
        modelFitAt: null,
        modelSampleSize: null,
        resolutionHash: null,
        domain: cleanDomain,
        thresholdSamples: threshold,
        status: "override",
        reason: override.reason || "founder override",
      };
    }
  }
  const model = await loadActiveModel(cleanDomain, opts.organizationId);
  if (!model) {
    return {
      raw,
      calibrated: null,
      modelId: null,
      modelFitAt: null,
      modelSampleSize: null,
      resolutionHash: null,
      domain: cleanDomain,
      thresholdSamples: threshold,
      status: "no_model",
    };
  }
  if (model.sampleSize < threshold) {
    return {
      raw,
      calibrated: null,
      modelId: model.id,
      modelFitAt: model.fitAt,
      modelSampleSize: model.sampleSize,
      resolutionHash: model.resolutionHash,
      domain: cleanDomain,
      thresholdSamples: threshold,
      status: "insufficient_sample",
    };
  }
  return {
    raw,
    calibrated: applyKnots(model.knots, raw),
    modelId: model.id,
    modelFitAt: model.fitAt,
    modelSampleSize: model.sampleSize,
    resolutionHash: model.resolutionHash,
    domain: cleanDomain,
    thresholdSamples: threshold,
    status: "calibrated",
  };
}

/**
 * Count significant decimals in a raw display string — `0.7` → 1,
 * `0.70` → 2, `70` → 0, `70.5%` → 1. The calibrated number must not
 * exceed this.
 */
export function decimalsInDisplay(rawDisplay: string): number {
  const m = rawDisplay.match(/\.(\d+)/);
  return m ? m[1].length : 0;
}

export function formatPercent(probability: number, decimals: number): string {
  const pct = clamp01(probability) * 100;
  return `${pct.toFixed(Math.max(0, decimals))}%`;
}

/**
 * Format the "calibrated estimate: X%" affordance, capping the
 * calibrated decimals at the raw display's decimals so the calibrated
 * number is never pseudo-precise relative to the firm's stated belief.
 */
export function formatCalibratedDisplay(
  rawDisplay: string,
  calibrated: number,
): string {
  const decimals = decimalsInDisplay(rawDisplay);
  return `calibrated estimate: ${formatPercent(calibrated, decimals)}`;
}
