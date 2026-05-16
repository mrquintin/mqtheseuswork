/**
 * Per-method track-record surface, materialized by `noosphere methods
 * track-record --rebuild` into the `MethodTrackRecord` table. The Python
 * aggregator owns every numerical decision (weighted Brier, OLS slope,
 * bootstrap CI); this TS lib is read-only — it normalizes Prisma rows
 * and exposes the publish gate.
 *
 * Sample-size publish gate: `MIN_PUBLISHABLE_SAMPLE = 5`. The public
 * `/methodology/[method]/track-record` page uses
 * `isPubliclyPublishable()` as a hard filter — methods below the
 * threshold do not get a public page.
 */
export const MIN_PUBLISHABLE_SAMPLE = 5;

export type MethodTrackRecordRow = {
  organizationId: string;
  methodName: string;
  methodVersion: string;
  domain: string;
  sampleSize: number;
  weightedBrier: number | null;
  calibrationSlope: number | null;
  calibrationSlopeCiLow: number | null;
  calibrationSlopeCiHigh: number | null;
  severityPassRate: number | null;
  computedAt: Date;
};

function decimalToNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof value === "object" && "toNumber" in (value as object)) {
    try {
      const n = (value as { toNumber: () => number }).toNumber();
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }
  return null;
}

function normalizeRow(raw: {
  organizationId: string;
  methodName: string;
  methodVersion: string;
  domain: string;
  sampleSize: number;
  weightedBrier: unknown;
  calibrationSlope: unknown;
  calibrationSlopeCiLow: unknown;
  calibrationSlopeCiHigh: unknown;
  severityPassRate: unknown;
  computedAt: Date;
}): MethodTrackRecordRow {
  return {
    organizationId: raw.organizationId,
    methodName: raw.methodName,
    methodVersion: raw.methodVersion,
    domain: raw.domain,
    sampleSize: raw.sampleSize,
    weightedBrier: decimalToNumber(raw.weightedBrier),
    calibrationSlope: decimalToNumber(raw.calibrationSlope),
    calibrationSlopeCiLow: decimalToNumber(raw.calibrationSlopeCiLow),
    calibrationSlopeCiHigh: decimalToNumber(raw.calibrationSlopeCiHigh),
    severityPassRate: decimalToNumber(raw.severityPassRate),
    computedAt: raw.computedAt,
  };
}

/** All track-record rows for a (method, version) across every domain
 *  in the given org. Caller is expected to pre-filter by org so we don't
 *  leak another tenant's rows through the public route by accident. */
export async function fetchTrackRecordsForMethod(
  organizationId: string,
  methodName: string,
  methodVersion: string,
): Promise<MethodTrackRecordRow[]> {
  try {
    const { db } = await import("@/lib/db");
    const rows = await db.methodTrackRecord.findMany({
      where: {
        organizationId,
        methodName,
        methodVersion,
      },
      orderBy: [{ domain: "asc" }],
    });
    return rows.map(normalizeRow);
  } catch (error) {
    if (
      !(error instanceof Error) ||
      !error.message.includes("DATABASE_URL must be set")
    ) {
      console.error("method_track_record_fetch_failed", error);
    }
    return [];
  }
}

/** Same as above, but returns a single record for the unspecified
 *  ("") domain when one exists — useful for the founder card on the
 *  method version page. */
export async function fetchPrimaryTrackRecord(
  organizationId: string,
  methodName: string,
  methodVersion: string,
): Promise<MethodTrackRecordRow | null> {
  const records = await fetchTrackRecordsForMethod(
    organizationId,
    methodName,
    methodVersion,
  );
  if (records.length === 0) return null;
  // Prefer the largest-n record when multiple domains exist; the
  // empty-domain row alone tends to be the unlabelled bucket and may be
  // smaller than per-domain rows.
  return [...records].sort((a, b) => b.sampleSize - a.sampleSize)[0];
}

/** Hard publish gate for the public site: a method's track record is
 *  only shown publicly when at least one domain row clears
 *  `MIN_PUBLISHABLE_SAMPLE`. */
export function isPubliclyPublishable(rows: MethodTrackRecordRow[]): boolean {
  return rows.some((r) => r.sampleSize >= MIN_PUBLISHABLE_SAMPLE);
}

/** Format a confidence band like "[0.42, 1.18]" or "—" when undefined. */
export function formatSlopeCi(row: MethodTrackRecordRow): string {
  const lo = row.calibrationSlopeCiLow;
  const hi = row.calibrationSlopeCiHigh;
  if (lo === null || hi === null) return "—";
  return `[${lo.toFixed(2)}, ${hi.toFixed(2)}]`;
}

/** UI helper: a one-line confidence verdict on a track-record row, used
 *  by both the founder card and the public page. Keep neutral wording —
 *  this surface is read by readers who didn't write the methodology and
 *  shouldn't be told what to think. */
export function describeConfidenceBand(row: MethodTrackRecordRow): string {
  if (row.sampleSize < MIN_PUBLISHABLE_SAMPLE) {
    return `n=${row.sampleSize} — below publication threshold (${MIN_PUBLISHABLE_SAMPLE}). Confidence band wide.`;
  }
  const lo = row.calibrationSlopeCiLow;
  const hi = row.calibrationSlopeCiHigh;
  if (lo === null || hi === null) {
    return `n=${row.sampleSize} — calibration slope undefined (probabilities may be clustered).`;
  }
  const width = hi - lo;
  if (width >= 1.0) {
    return `n=${row.sampleSize} — confidence band wide (Δ=${width.toFixed(2)}).`;
  }
  return `n=${row.sampleSize} — confidence band Δ=${width.toFixed(2)}.`;
}
