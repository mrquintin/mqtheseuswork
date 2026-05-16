import { db } from "@/lib/db";

/**
 * Read/write surface for the LogicalAlgorithm triage queue.
 *
 * Algorithm rows are produced by the noosphere AlgorithmDrafter (see
 * noosphere/noosphere/algorithms/drafter.py) and land as `DRAFT` —
 * the founder accepts, edits, rejects, or merges in the queue UI.
 * The agent never auto-promotes to `ACTIVE`; that path lives here.
 *
 * The Prisma schema persists the canonical Pydantic payload as
 * `payloadJson` so the schema can evolve without per-field
 * migrations.  The helpers below parse that JSON into TS shapes the
 * UI renders without losing the field-level columns the Postgres
 * indexes hit hardest.
 */
import { Prisma } from "@prisma/client";

export type AlgorithmQueueStatus =
  | "DRAFT"
  | "UNDER_REVIEW"
  | "ACTIVE"
  | "PAUSED"
  | "RETIRED";

export type AlgorithmInputRow = {
  name: string;
  type: string;
  description: string;
  observability_source: string;
  enum_values: string[];
  units: string | null;
};

export type AlgorithmOutputRow = {
  name: string;
  type: string;
  description: string;
  units: string | null;
  range: [number, number] | null;
  fields: Array<{ name: string; type?: string }>;
};

export type AlgorithmReasoningStep = {
  step_kind: "DETECT" | "APPLY_PRINCIPLE" | "SYNTHESIZE" | "OUTPUT";
  principle_id: string | null;
  predicate: string | null;
  derived_fact: string | null;
};

export type AlgorithmRow = {
  id: string;
  name: string;
  description: string;
  status: AlgorithmQueueStatus;
  sourcePrincipleIds: string[];
  inputs: AlgorithmInputRow[];
  output: AlgorithmOutputRow;
  reasoningChain: AlgorithmReasoningStep[];
  triggerPredicate: string;
  confidenceNote: string;
  createdAt: Date;
  updatedAt: Date;
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
  const obj = (raw && typeof raw === "object" ? raw : {}) as Record<
    string,
    unknown
  >;
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
  const obj = (raw && typeof raw === "object" ? raw : {}) as Record<
    string,
    unknown
  >;
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
  const fields = fieldsRaw
    .filter((f): f is Record<string, unknown> => Boolean(f && typeof f === "object"))
    .map((f) => ({
      name: asString(f.name),
      type: typeof f.type === "string" ? f.type : undefined,
    }));
  return {
    name: asString(obj.name),
    type: asString(obj.type),
    description: asString(obj.description),
    units: typeof obj.units === "string" ? obj.units : null,
    range,
    fields,
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
        principle_id:
          typeof s.principle_id === "string" ? s.principle_id : null,
        predicate: typeof s.predicate === "string" ? s.predicate : null,
        derived_fact:
          typeof s.derived_fact === "string" ? s.derived_fact : null,
      };
    });
}

function rowFromPrisma(row: {
  id: string;
  name: string;
  description: string;
  status: string;
  sourcePrincipleIdsJson: string;
  inputsJson: string;
  outputJson: string;
  reasoningChainJson: string;
  triggerPredicate: string;
  payloadJson: string;
  createdAt: Date;
  updatedAt: Date;
}): AlgorithmRow {
  const payload = (safeParseJson(row.payloadJson) ?? {}) as Record<
    string,
    unknown
  >;
  const inputsRaw = safeParseJson(row.inputsJson);
  const outputRaw = safeParseJson(row.outputJson);
  const chainRaw = safeParseJson(row.reasoningChainJson);
  const sourceIds = asStringArray(safeParseJson(row.sourcePrincipleIdsJson));

  // confidenceNote lives only in payloadJson — the schema does not
  // index it. Fall back to empty when absent.
  const confidenceNote = asString(payload.confidence_note);
  // Strip the drafter-model stamp from the description for display so
  // the row reads cleanly, but keep the original in the JSON payload
  // for provenance.
  const rawDescription = row.description ?? "";
  const description = rawDescription.replace(/\s*\[drafter:[^\]]+\]\s*$/, "");

  return {
    id: row.id,
    name: row.name,
    description,
    status: (row.status as AlgorithmQueueStatus) ?? "DRAFT",
    sourcePrincipleIds: sourceIds.length
      ? sourceIds
      : asStringArray(payload.source_principle_ids),
    inputs: Array.isArray(inputsRaw)
      ? inputsRaw.map(parseInput)
      : asStringArray(payload.inputs).map(() => parseInput({})),
    output: parseOutput(outputRaw ?? payload.output),
    reasoningChain: parseChain(chainRaw ?? payload.reasoning_chain),
    triggerPredicate: row.triggerPredicate ?? "",
    confidenceNote,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  };
}

/**
 * Founder triage queue: DRAFT + UNDER_REVIEW rows, oldest first.
 *
 * Algorithms surface in creation order so the founder works through
 * the backlog rather than chasing the latest churn — the runtime
 * (prompt 03) decides invocation order separately.
 */
export async function listQueuedAlgorithms(
  organizationId: string,
): Promise<AlgorithmRow[]> {
  const rows = await db.logicalAlgorithm.findMany({
    where: {
      organizationId,
      status: { in: ["DRAFT", "UNDER_REVIEW"] },
    },
    orderBy: [{ createdAt: "asc" }],
  });
  return rows.map(rowFromPrisma);
}

export async function listAlgorithmsByStatus(
  organizationId: string,
  status: AlgorithmQueueStatus,
): Promise<AlgorithmRow[]> {
  const rows = await db.logicalAlgorithm.findMany({
    where: { organizationId, status },
    orderBy: [{ createdAt: "asc" }],
  });
  return rows.map(rowFromPrisma);
}

export async function getAlgorithm(
  organizationId: string,
  id: string,
): Promise<AlgorithmRow | null> {
  const row = await db.logicalAlgorithm.findFirst({
    where: { id, organizationId },
  });
  return row ? rowFromPrisma(row) : null;
}

export type AcceptAlgorithmInput = {
  name?: string;
  description?: string;
  triggerPredicate?: string;
};

/**
 * Accept a DRAFT or UNDER_REVIEW row and promote it to ACTIVE.
 *
 * Optionally carries founder edits — the noosphere validator stack
 * runs on the Python side at promotion time, so we update fields
 * defensively here and let the next noosphere sync re-validate.  A
 * production deployment threads the edits through an HTTP boundary
 * back to noosphere; this thin Codex-side helper exists so the queue
 * UI can round-trip an edit in the founder review flow.
 */
export async function acceptAlgorithm(
  organizationId: string,
  id: string,
  input: AcceptAlgorithmInput = {},
): Promise<void> {
  const patch: Prisma.LogicalAlgorithmUpdateInput = {
    status: "ACTIVE",
  };
  if (input.name !== undefined) patch.name = input.name.trim();
  if (input.description !== undefined)
    patch.description = input.description.trim();
  if (input.triggerPredicate !== undefined)
    patch.triggerPredicate = input.triggerPredicate.trim();
  await db.logicalAlgorithm.updateMany({
    where: { id, organizationId },
    data: patch,
  });
}

export async function rejectAlgorithm(
  organizationId: string,
  id: string,
  reason: string,
): Promise<void> {
  await db.logicalAlgorithm.updateMany({
    where: { id, organizationId },
    data: {
      status: "RETIRED",
      retiredReason: reason.trim() || "founder rejected at triage",
    },
  });
}

/**
 * Operator-only: flip an ACTIVE algorithm to PAUSED, or vice-versa.
 *
 * The status transition validators that the noosphere store enforces
 * are mirrored loosely here — Codex is the operator-side surface, not
 * the source of truth, so we only refuse the obvious illegal jumps
 * (DRAFT → PAUSED, RETIRED → anything) and let noosphere have the
 * final say on the next sync.
 */
export async function setAlgorithmStatus(
  organizationId: string,
  id: string,
  next: "ACTIVE" | "PAUSED",
): Promise<void> {
  await db.logicalAlgorithm.updateMany({
    where: { id, organizationId, status: { in: ["ACTIVE", "PAUSED"] } },
    data: { status: next },
  });
}

/**
 * Operator-only: retire an algorithm with a reason. RETIRED is
 * terminal — the row stays in the database for audit and historical
 * `/algorithms?status=ALL` views, but the runtime no longer fires it.
 */
export async function retireAlgorithm(
  organizationId: string,
  id: string,
  reason: string,
): Promise<void> {
  const trimmed = reason.trim();
  if (!trimmed) {
    throw new Error("retire requires a reason");
  }
  await db.logicalAlgorithm.updateMany({
    where: { id, organizationId },
    data: {
      status: "RETIRED",
      retiredReason: trimmed,
    },
  });
}

export async function mergeAlgorithm(
  organizationId: string,
  id: string,
  intoId: string,
): Promise<void> {
  if (id === intoId) {
    throw new Error("Cannot merge an algorithm into itself");
  }
  const target = await db.logicalAlgorithm.findFirst({
    where: { id: intoId, organizationId },
  });
  if (!target) {
    throw new Error("Merge target not found in this organization");
  }
  await db.logicalAlgorithm.updateMany({
    where: { id, organizationId },
    data: {
      status: "RETIRED",
      retiredReason: `merged into ${intoId}`,
    },
  });
}
