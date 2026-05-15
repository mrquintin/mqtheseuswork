import { db } from "@/lib/db";

/**
 * Read/write surface for the quantitative-formalisation spec layer.
 *
 * Bridges the firm's logical principles to numerical, falsifiable
 * tests. The noosphere drafter
 * (`noosphere/noosphere/quantitative/drafter.py`) proposes one
 * `QuantitativeFormalisation` per principle; the founder triage UI
 * under `/principles/[id]/quantitative` accepts / rejects / edits;
 * the public surface at `/methodology/principles/[id]` reads any
 * APPROVED row.
 *
 * Constraints enforced here:
 *   - The drafter never marks anything APPROVED. Acceptance is a
 *     founder-only action (`approveFormalisation`).
 *   - APPROVED rows must have a non-empty null hypothesis, ≥ 1 metric,
 *     ≥ 1 test. Enforced both client-side (the form requires fields)
 *     and server-side (this module's `approveFormalisation` refuses).
 */

export type FormalisationStatus =
  | "DRAFT"
  | "PENDING_REVIEW"
  | "APPROVED"
  | "RETIRED"
  | "UNFORMALISABLE";

export type MetricSpec = {
  name: string;
  definition: string;
  unit: string;
  source_dataset: string;
  update_cadence: string;
};

export type StatisticalTestKind =
  | "regression"
  | "classification"
  | "event_study"
  | "correlation"
  | "hazard"
  | "ks_test"
  | "ab";

export type StatisticalTestSpec = {
  kind: StatisticalTestKind;
  dependent: string;
  independents: string[];
  controls: string[];
  dataset_filter: string;
  expected_sign_or_magnitude: string;
  expected_p_threshold: number;
};

export type DataSourceSpec = {
  name: string;
  provenance: string;
  license: string;
  refresh_cadence: string;
};

export type QuantitativeFormalisationRow = {
  id: string;
  organizationId: string;
  principleId: string;
  status: FormalisationStatus;
  nullHypothesis: string;
  metrics: MetricSpec[];
  tests: StatisticalTestSpec[];
  dataSources: DataSourceSpec[];
  decisionThresholds: string[];
  unformalisableReason: string | null;
  drafterModel: string;
  drafterNotes: string;
  reviewedByFounderId: string | null;
  reviewedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
};

function safeJsonArray<T>(value: string, fallback: T[]): T[] {
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) return fallback;
    return parsed as T[];
  } catch {
    return fallback;
  }
}

type PrismaRow = {
  id: string;
  organizationId: string;
  principleId: string;
  status: string;
  nullHypothesis: string;
  metricsJson: string;
  testsJson: string;
  dataSourcesJson: string;
  decisionThresholdsJson: string;
  unformalisableReason: string | null;
  drafterModel: string;
  drafterNotes: string;
  reviewedByFounderId: string | null;
  reviewedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
};

function rowFromPrisma(p: PrismaRow): QuantitativeFormalisationRow {
  return {
    id: p.id,
    organizationId: p.organizationId,
    principleId: p.principleId,
    status: (p.status as FormalisationStatus) ?? "DRAFT",
    nullHypothesis: p.nullHypothesis ?? "",
    metrics: safeJsonArray<MetricSpec>(p.metricsJson, []),
    tests: safeJsonArray<StatisticalTestSpec>(p.testsJson, []),
    dataSources: safeJsonArray<DataSourceSpec>(p.dataSourcesJson, []),
    decisionThresholds: safeJsonArray<string>(p.decisionThresholdsJson, []),
    unformalisableReason: p.unformalisableReason,
    drafterModel: p.drafterModel ?? "",
    drafterNotes: p.drafterNotes ?? "",
    reviewedByFounderId: p.reviewedByFounderId,
    reviewedAt: p.reviewedAt,
    createdAt: p.createdAt,
    updatedAt: p.updatedAt,
  };
}

/**
 * Return the most-recent formalisation row for a principle, or null
 * if none has been drafted yet.
 */
export async function getFormalisationForPrinciple(
  organizationId: string,
  principleId: string,
): Promise<QuantitativeFormalisationRow | null> {
  // @ts-expect-error — generated client may not be regenerated yet;
  // the model exists in schema.prisma. Runtime resolves correctly
  // once `prisma generate` runs.
  const row: PrismaRow | null = await db.quantitativeFormalisation?.findFirst({
    where: { organizationId, principleId },
    orderBy: { updatedAt: "desc" },
  });
  return row ? rowFromPrisma(row) : null;
}

/**
 * Public-surface read: only APPROVED rows are returned.
 */
export async function getApprovedFormalisationForPrinciple(
  principleId: string,
  organizationId?: string,
): Promise<QuantitativeFormalisationRow | null> {
  // @ts-expect-error — see above.
  const row: PrismaRow | null = await db.quantitativeFormalisation?.findFirst({
    where: {
      principleId,
      status: "APPROVED",
      ...(organizationId ? { organizationId } : {}),
    },
    orderBy: { reviewedAt: "desc" },
  });
  return row ? rowFromPrisma(row) : null;
}

export type ApproveInput = {
  nullHypothesis: string;
  metrics: MetricSpec[];
  tests: StatisticalTestSpec[];
  dataSources: DataSourceSpec[];
  decisionThresholds: string[];
};

export class FormalisationInvariantError extends Error {}

/**
 * Founder approval. Enforces the schema invariants for APPROVED rows
 * (non-empty null hypothesis, ≥ 1 metric, ≥ 1 test); throws
 * `FormalisationInvariantError` otherwise so the UI can surface the
 * specific reason rather than persisting an invalid spec.
 */
export async function approveFormalisation(
  organizationId: string,
  id: string,
  founderId: string,
  input: ApproveInput,
): Promise<void> {
  if (!input.nullHypothesis.trim()) {
    throw new FormalisationInvariantError(
      "APPROVED formalisation requires a non-empty null hypothesis",
    );
  }
  if (input.metrics.length === 0) {
    throw new FormalisationInvariantError(
      "APPROVED formalisation requires at least one metric",
    );
  }
  if (input.tests.length === 0) {
    throw new FormalisationInvariantError(
      "APPROVED formalisation requires at least one test",
    );
  }
  // @ts-expect-error — see above.
  await db.quantitativeFormalisation?.updateMany({
    where: { id, organizationId },
    data: {
      status: "APPROVED",
      nullHypothesis: input.nullHypothesis.trim(),
      metricsJson: JSON.stringify(input.metrics),
      testsJson: JSON.stringify(input.tests),
      dataSourcesJson: JSON.stringify(input.dataSources),
      decisionThresholdsJson: JSON.stringify(input.decisionThresholds),
      reviewedByFounderId: founderId,
      reviewedAt: new Date(),
    },
  });
}

export async function rejectFormalisation(
  organizationId: string,
  id: string,
  founderId: string,
  reason: string,
): Promise<void> {
  // @ts-expect-error — see above.
  await db.quantitativeFormalisation?.updateMany({
    where: { id, organizationId },
    data: {
      status: "RETIRED",
      drafterNotes: reason.trim(),
      reviewedByFounderId: founderId,
      reviewedAt: new Date(),
    },
  });
}
