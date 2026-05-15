/**
 * Shared calibration primitives for the unified portfolio surface.
 *
 * The forecasts portfolio scores binary YES/NO outcomes with the Brier
 * rule. The equities portfolio scores three-class signals
 * (BULLISH / BEARISH / NEUTRAL) with directional accuracy. Both
 * tracks share the same surface, so the math lives in one place — the
 * page never reimplements it.
 */

export type BinaryCalibrationBucket = {
  bucket: number;
  predictionCount: number;
  resolvedCount: number;
  meanProbabilityYes: number | null;
  empiricalYesRate: number | null;
  meanBrier: number | null;
};

export type BinaryOutcome = {
  /** model-stated probability of YES, in [0, 1]. */
  probabilityYes: number;
  /** truth: 1 for YES, 0 for NO. */
  outcome: 0 | 1;
};

export type DirectionalSignal = "BULLISH" | "BEARISH" | "NEUTRAL";
export type DirectionalActual = "UP" | "DOWN" | "FLAT";

export type DirectionalSample = {
  predicted: DirectionalSignal;
  actual: DirectionalActual;
};

export type DirectionalAccuracyBucket = {
  predicted: DirectionalSignal;
  total: number;
  correct: number;
  accuracy: number | null;
};

/**
 * One-prediction Brier score for a binary outcome.
 *
 * Brier = (p - y)^2 where p ∈ [0, 1] and y ∈ {0, 1}.
 */
export function brierScore(probabilityYes: number, outcome: 0 | 1): number {
  const p = clamp01(probabilityYes);
  return (p - outcome) ** 2;
}

export function meanBrier(rows: BinaryOutcome[]): number | null {
  if (rows.length === 0) return null;
  let total = 0;
  for (const row of rows) total += brierScore(row.probabilityYes, row.outcome);
  return total / rows.length;
}

/**
 * Bucket a stream of binary forecasts into ten equal-width probability
 * buckets [0, 0.1), [0.1, 0.2), … [0.9, 1.0]. The aggregate rate inside
 * each bucket is the empirical reliability curve we plot on the
 * overview tab.
 */
export function bucketBinary(
  rows: BinaryOutcome[],
  binCount = 10,
): BinaryCalibrationBucket[] {
  if (binCount < 1) throw new RangeError("binCount must be ≥ 1");
  const buckets: BinaryOutcome[][] = Array.from({ length: binCount }, () => []);
  for (const row of rows) {
    const p = clamp01(row.probabilityYes);
    const idx = Math.min(binCount - 1, Math.floor(p * binCount));
    buckets[idx].push(row);
  }
  return buckets.map((bucketRows, idx) => {
    const center = (idx + 0.5) / binCount;
    if (bucketRows.length === 0) {
      return {
        bucket: roundTo(center, 3),
        predictionCount: 0,
        resolvedCount: 0,
        meanProbabilityYes: null,
        empiricalYesRate: null,
        meanBrier: null,
      };
    }
    const meanP =
      bucketRows.reduce((sum, row) => sum + clamp01(row.probabilityYes), 0) /
      bucketRows.length;
    const yesCount = bucketRows.reduce((sum, row) => sum + row.outcome, 0);
    return {
      bucket: roundTo(center, 3),
      predictionCount: bucketRows.length,
      resolvedCount: bucketRows.length,
      meanProbabilityYes: meanP,
      empiricalYesRate: yesCount / bucketRows.length,
      meanBrier: meanBrier(bucketRows),
    };
  });
}

/**
 * Convert one three-class signal vs. realised return into a
 * directional-accuracy verdict. NEUTRAL is treated as a hit only
 * when the realised move was FLAT.
 */
export function isDirectionalHit(
  predicted: DirectionalSignal,
  actual: DirectionalActual,
): boolean {
  if (predicted === "BULLISH") return actual === "UP";
  if (predicted === "BEARISH") return actual === "DOWN";
  return actual === "FLAT";
}

/**
 * Directional accuracy across a sequence of three-class signals.
 * Returns the share of signals whose realised move matches the
 * predicted direction. Returns null for an empty input rather than
 * defaulting to 0 — there is no calibration to claim with zero
 * samples.
 */
export function directionalAccuracy(rows: DirectionalSample[]): number | null {
  if (rows.length === 0) return null;
  const correct = rows.reduce(
    (sum, row) => sum + (isDirectionalHit(row.predicted, row.actual) ? 1 : 0),
    0,
  );
  return correct / rows.length;
}

/**
 * Per-class breakdown of directional accuracy, so the overview can
 * show that (e.g.) BEARISH calls are unreliable even when the overall
 * hit rate is acceptable.
 */
export function directionalAccuracyByClass(
  rows: DirectionalSample[],
): DirectionalAccuracyBucket[] {
  const labels: DirectionalSignal[] = ["BULLISH", "BEARISH", "NEUTRAL"];
  return labels.map((label) => {
    const subset = rows.filter((row) => row.predicted === label);
    const correct = subset.reduce(
      (sum, row) => sum + (isDirectionalHit(row.predicted, row.actual) ? 1 : 0),
      0,
    );
    return {
      predicted: label,
      total: subset.length,
      correct,
      accuracy: subset.length === 0 ? null : correct / subset.length,
    };
  });
}

export function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function roundTo(value: number, places: number): number {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}
