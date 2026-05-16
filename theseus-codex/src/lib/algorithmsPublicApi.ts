import { db } from "@/lib/db";
import type {
  AlgorithmInputRow,
  AlgorithmOutputRow,
  AlgorithmQueueStatus,
  AlgorithmReasoningStep,
} from "@/lib/algorithmsApi";

/**
 * Read surface for the public `/algorithms` page family.
 *
 * The triage queue surface in `algorithmsApi.ts` only ever exposes
 * DRAFT/UNDER_REVIEW rows; the public surface needs ACTIVE / PAUSED /
 * RETIRED — and their invocations, observations, and calibration
 * series. This module is the loaderlayer the public pages consume,
 * keeping field-stripping (no `_meta`, no internal hashes) in one
 * place so the routes downstream cannot accidentally leak operator-
 * only fields.
 */

export type PublicAlgorithmStatus = AlgorithmQueueStatus;

export type PublicAlgorithmCorrectness =
  | "CORRECT"
  | "INCORRECT"
  | "PARTIALLY_CORRECT"
  | "INDETERMINATE";

export type PublicAlgorithmRow = {
  id: string;
  name: string;
  description: string;
  status: PublicAlgorithmStatus;
  retiredReason: string | null;
  sourcePrincipleIds: string[];
  inputs: AlgorithmInputRow[];
  output: AlgorithmOutputRow;
  reasoningChain: AlgorithmReasoningStep[];
  triggerPredicate: string;
  createdAt: Date;
  updatedAt: Date;
  lastInvokedAt: Date | null;
  hitRate: { ratio: number | null; n: number };
  latestInvocationId: string | null;
  latestInvocationAt: Date | null;
  invocationCount: number;
};

export type PublicInvocationRow = {
  id: string;
  algorithmId: string;
  invokedAt: Date;
  triggerInputs: Record<string, unknown>;
  derivedOutput: Record<string, unknown>;
  reasoningTrace: string[];
  confidenceLow: number;
  confidenceHigh: number;
  predictedHorizon: number;
  betImplied: PublicBetImplied | null;
  resolvedAt: Date | null;
  actualOutcome: Record<string, unknown> | null;
  correctness: PublicAlgorithmCorrectness | null;
  brierEquivalent: number | null;
};

export type PublicBetImplied = {
  venue: string;
  instrument: string;
  direction: string;
  sizingHint: string | null;
  rationale: string;
};

export type PublicObservationRow = {
  id: string;
  invocationId: string;
  inputName: string;
  value: unknown;
  observedAt: Date;
  sourceArtifactId: string | null;
  sourceUrl: string | null;
};

export type PublicCalibrationPoint = {
  index: number;
  invocationId: string;
  ratio: number;
  correctness: PublicAlgorithmCorrectness;
  brierEquivalent: number | null;
};

function safeParseJson(value: string | null | undefined): unknown {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === "string");
}

function parseInput(raw: unknown): AlgorithmInputRow {
  const obj = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    name: asString(obj.name),
    type: asString(obj.type),
    description: asString(obj.description),
    observability_source: asString(obj.observability_source),
    enum_values: asStringArray(obj.enum_values),
    units: typeof obj.units === "string" ? obj.units : null,
  };
}

function parseOutput(raw: unknown): AlgorithmOutputRow {
  const obj = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const rangeRaw = obj.range;
  let range: [number, number] | null = null;
  if (
    Array.isArray(rangeRaw) &&
    rangeRaw.length === 2 &&
    typeof rangeRaw[0] === "number" &&
    typeof rangeRaw[1] === "number"
  ) {
    range = [rangeRaw[0], rangeRaw[1]];
  }
  const fieldsRaw = Array.isArray(obj.fields) ? obj.fields : [];
  return {
    name: asString(obj.name),
    type: asString(obj.type),
    description: asString(obj.description),
    units: typeof obj.units === "string" ? obj.units : null,
    range,
    fields: fieldsRaw
      .filter((f): f is Record<string, unknown> => Boolean(f && typeof f === "object"))
      .map((f) => ({
        name: asString(f.name),
        type: typeof f.type === "string" ? f.type : undefined,
      })),
  };
}

function parseChain(raw: unknown): AlgorithmReasoningStep[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((s): s is Record<string, unknown> => Boolean(s && typeof s === "object"))
    .map((s) => {
      const kind = asString(s.step_kind).toUpperCase();
      const safeKind: AlgorithmReasoningStep["step_kind"] =
        kind === "DETECT" ||
        kind === "APPLY_PRINCIPLE" ||
        kind === "SYNTHESIZE" ||
        kind === "OUTPUT"
          ? kind
          : "DETECT";
      return {
        step_kind: safeKind,
        principle_id: typeof s.principle_id === "string" ? s.principle_id : null,
        predicate: typeof s.predicate === "string" ? s.predicate : null,
        derived_fact: typeof s.derived_fact === "string" ? s.derived_fact : null,
      };
    });
}

/**
 * Strip operator-only fields from a derived-output JSON dict.
 *
 * The runtime stores its idempotency hash under `_meta.input_hash`
 * and the `forced` flag under `_meta.forced` — neither belongs on the
 * public surface. The strip happens here, in a single place, so a
 * later page or API route cannot bypass it by reading the JSON
 * directly.
 */
function stripMeta(payload: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== "object") return {};
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(payload as Record<string, unknown>)) {
    if (k === "_meta") continue;
    out[k] = v;
  }
  return out;
}

function isCorrectness(v: unknown): v is PublicAlgorithmCorrectness {
  return (
    v === "CORRECT" ||
    v === "INCORRECT" ||
    v === "PARTIALLY_CORRECT" ||
    v === "INDETERMINATE"
  );
}

function asCorrectness(v: unknown): PublicAlgorithmCorrectness | null {
  return isCorrectness(v) ? v : null;
}

type AlgorithmDbRow = {
  id: string;
  name: string;
  description: string;
  status: string;
  sourcePrincipleIdsJson: string;
  inputsJson: string;
  outputJson: string;
  reasoningChainJson: string;
  triggerPredicate: string;
  retiredReason: string | null;
  payloadJson: string;
  createdAt: Date;
  updatedAt: Date;
  lastInvokedAt: Date | null;
};

type InvocationDbRow = {
  id: string;
  algorithmId: string;
  invokedAt: Date;
  triggerInputsJson: string;
  derivedOutputJson: string;
  reasoningTraceJson: string;
  confidenceLow: number;
  confidenceHigh: number;
  predictedHorizon: number;
  betImpliedJson: string | null;
  resolvedAt: Date | null;
  actualOutcomeJson: string | null;
  correctness: string | null;
  brierEquivalent: number | null;
};

type ObservationDbRow = {
  id: string;
  invocationId: string;
  inputName: string;
  valueJson: string;
  observedAt: Date;
  sourceArtifactId: string | null;
  sourceUrl: string | null;
};

function rowFromAlgorithm(
  row: AlgorithmDbRow,
  invocations: InvocationDbRow[],
): PublicAlgorithmRow {
  const payload = (safeParseJson(row.payloadJson) ?? {}) as Record<string, unknown>;
  const inputsRaw = safeParseJson(row.inputsJson);
  const outputRaw = safeParseJson(row.outputJson);
  const chainRaw = safeParseJson(row.reasoningChainJson);
  const sourceIds = asStringArray(safeParseJson(row.sourcePrincipleIdsJson));

  const description = (row.description ?? "").replace(/\s*\[drafter:[^\]]+\]\s*$/, "");
  const latest = invocations[0] ?? null;

  return {
    id: row.id,
    name: row.name,
    description,
    status: (row.status as PublicAlgorithmStatus) ?? "DRAFT",
    retiredReason: row.retiredReason,
    sourcePrincipleIds: sourceIds.length
      ? sourceIds
      : asStringArray(payload.source_principle_ids),
    inputs: Array.isArray(inputsRaw) ? inputsRaw.map(parseInput) : [],
    output: parseOutput(outputRaw ?? payload.output),
    reasoningChain: parseChain(chainRaw ?? payload.reasoning_chain),
    triggerPredicate: row.triggerPredicate ?? "",
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
    lastInvokedAt: row.lastInvokedAt,
    hitRate: hitRateFromInvocations(invocations),
    latestInvocationId: latest?.id ?? null,
    latestInvocationAt: latest?.invokedAt ?? null,
    invocationCount: invocations.length,
  };
}

function rowFromInvocation(row: InvocationDbRow): PublicInvocationRow {
  const trigger = (safeParseJson(row.triggerInputsJson) ?? {}) as Record<string, unknown>;
  const derived = safeParseJson(row.derivedOutputJson);
  const trace = safeParseJson(row.reasoningTraceJson);
  const betRaw = safeParseJson(row.betImpliedJson);
  const actual = safeParseJson(row.actualOutcomeJson);

  let bet: PublicBetImplied | null = null;
  if (betRaw && typeof betRaw === "object") {
    const obj = betRaw as Record<string, unknown>;
    bet = {
      venue: asString(obj.venue),
      instrument: asString(obj.instrument),
      direction: asString(obj.direction),
      sizingHint: typeof obj.sizing_hint === "string" ? obj.sizing_hint : null,
      rationale: asString(obj.rationale),
    };
  }

  return {
    id: row.id,
    algorithmId: row.algorithmId,
    invokedAt: row.invokedAt,
    triggerInputs: trigger,
    derivedOutput: stripMeta(derived),
    reasoningTrace: Array.isArray(trace)
      ? (trace.filter((s) => typeof s === "string") as string[])
      : [],
    confidenceLow: row.confidenceLow,
    confidenceHigh: row.confidenceHigh,
    predictedHorizon: row.predictedHorizon,
    betImplied: bet,
    resolvedAt: row.resolvedAt,
    actualOutcome: actual && typeof actual === "object" ? (actual as Record<string, unknown>) : null,
    correctness: asCorrectness(row.correctness),
    brierEquivalent: row.brierEquivalent,
  };
}

function rowFromObservation(row: ObservationDbRow): PublicObservationRow {
  return {
    id: row.id,
    invocationId: row.invocationId,
    inputName: row.inputName,
    value: safeParseJson(row.valueJson),
    observedAt: row.observedAt,
    sourceArtifactId: row.sourceArtifactId,
    sourceUrl: row.sourceUrl,
  };
}

export function hitRateFromInvocations(
  invocations: InvocationDbRow[] | PublicInvocationRow[],
): { ratio: number | null; n: number } {
  let n = 0;
  let score = 0;
  for (const inv of invocations) {
    const c = inv.correctness;
    if (!c || c === "INDETERMINATE") continue;
    n += 1;
    if (c === "CORRECT") score += 1;
    else if (c === "PARTIALLY_CORRECT") score += 0.5;
  }
  if (n === 0) return { ratio: null, n: 0 };
  return { ratio: Math.round((score / n) * 10000) / 10000, n };
}

export function calibrationSeries(
  invocations: PublicInvocationRow[],
): PublicCalibrationPoint[] {
  const ordered = [...invocations]
    .filter((inv) => inv.correctness && inv.correctness !== "INDETERMINATE")
    .sort((a, b) => a.invokedAt.getTime() - b.invokedAt.getTime());
  const out: PublicCalibrationPoint[] = [];
  let score = 0;
  ordered.forEach((inv, idx) => {
    if (inv.correctness === "CORRECT") score += 1;
    else if (inv.correctness === "PARTIALLY_CORRECT") score += 0.5;
    const ratio = score / (idx + 1);
    out.push({
      index: idx + 1,
      invocationId: inv.id,
      ratio: Math.round(ratio * 10000) / 10000,
      correctness: inv.correctness as PublicAlgorithmCorrectness,
      brierEquivalent: inv.brierEquivalent,
    });
  });
  return out;
}

export type ListPublicAlgorithmsParams = {
  status?: PublicAlgorithmStatus | "ALL";
  domain?: string | null;
  sourcePrincipleId?: string | null;
};

const DEFAULT_PUBLIC_STATUSES: PublicAlgorithmStatus[] = ["ACTIVE"];
const RETIRED_INCLUDED_STATUSES: PublicAlgorithmStatus[] = [
  "ACTIVE",
  "PAUSED",
  "RETIRED",
];

async function loadInvocations(algorithmIds: string[]): Promise<Map<string, InvocationDbRow[]>> {
  if (algorithmIds.length === 0) return new Map();
  const rows = (await db.algorithmInvocation.findMany({
    where: { algorithmId: { in: algorithmIds } },
    orderBy: [{ invokedAt: "desc" }],
  })) as unknown as InvocationDbRow[];
  const grouped = new Map<string, InvocationDbRow[]>();
  for (const row of rows) {
    const arr = grouped.get(row.algorithmId) ?? [];
    arr.push(row);
    grouped.set(row.algorithmId, arr);
  }
  return grouped;
}

export async function listPublicAlgorithms(
  organizationId: string,
  params: ListPublicAlgorithmsParams = {},
): Promise<PublicAlgorithmRow[]> {
  const statusFilter = params.status === "ALL"
    ? RETIRED_INCLUDED_STATUSES
    : params.status
      ? [params.status]
      : DEFAULT_PUBLIC_STATUSES;
  const rows = (await db.logicalAlgorithm.findMany({
    where: {
      organizationId,
      status: { in: statusFilter },
    },
    orderBy: [{ name: "asc" }],
  })) as unknown as AlgorithmDbRow[];

  const invocationsByAlgorithm = await loadInvocations(rows.map((r) => r.id));

  let mapped = rows.map((row) =>
    rowFromAlgorithm(row, invocationsByAlgorithm.get(row.id) ?? []),
  );
  if (params.sourcePrincipleId) {
    mapped = mapped.filter((r) =>
      r.sourcePrincipleIds.includes(params.sourcePrincipleId!),
    );
  }
  return mapped;
}

export async function getPublicAlgorithm(
  organizationId: string,
  id: string,
): Promise<PublicAlgorithmRow | null> {
  const row = (await db.logicalAlgorithm.findFirst({
    where: { id, organizationId },
  })) as unknown as AlgorithmDbRow | null;
  if (!row) return null;
  const invocations = (await db.algorithmInvocation.findMany({
    where: { algorithmId: id },
    orderBy: [{ invokedAt: "desc" }],
  })) as unknown as InvocationDbRow[];
  return rowFromAlgorithm(row, invocations);
}

export async function listInvocationsForAlgorithm(
  algorithmId: string,
  limit = 20,
): Promise<PublicInvocationRow[]> {
  const rows = (await db.algorithmInvocation.findMany({
    where: { algorithmId },
    orderBy: [{ invokedAt: "desc" }],
    take: limit,
  })) as unknown as InvocationDbRow[];
  return rows.map(rowFromInvocation);
}

export async function getInvocation(
  algorithmId: string,
  invocationId: string,
): Promise<{
  invocation: PublicInvocationRow;
  observations: PublicObservationRow[];
} | null> {
  const row = (await db.algorithmInvocation.findFirst({
    where: { id: invocationId, algorithmId },
  })) as unknown as InvocationDbRow | null;
  if (!row) return null;
  const observations = (await db.algorithmInputObservation.findMany({
    where: { invocationId },
    orderBy: [{ observedAt: "asc" }],
  })) as unknown as ObservationDbRow[];
  return {
    invocation: rowFromInvocation(row),
    observations: observations.map(rowFromObservation),
  };
}

/**
 * `manual.operator.entered` inputs land on the public surface as
 * "operator input" — the value is real, but readers should know it is
 * hand-curated rather than ingested. This predicate centralises the
 * check so the badge wording stays consistent.
 */
export function isOperatorEntered(input: AlgorithmInputRow | string): boolean {
  const source = typeof input === "string" ? input : input.observability_source;
  return source === "manual.operator.entered" || source.startsWith("manual.");
}
