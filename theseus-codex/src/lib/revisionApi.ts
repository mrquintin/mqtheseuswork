/**
 * Belief-revision client/server contract.
 *
 * The Python-side engine (`noosphere/cascade/revision.py`) is the source
 * of truth for the propagation algorithm; this module is the TS-side
 * boundary between the operator UI and the audit ledger row in
 * `RevisionEvent`.
 *
 * Why no direct call into Python here: the preview render is interactive
 * and needs to be safe to run on every keystroke; spawning a Python
 * subprocess per keystroke is prohibitive. Instead the preview computes
 * a *projected* impact from the cached cascade snapshot stored on the
 * conclusion (good enough for the modal), and the actual commit is
 * routed through the noosphere CLI for the canonical RevisionPlan +
 * RevisionEvent insertion.
 */

import { db } from "@/lib/db";

/** UI-facing thresholds — must match `noosphere/cascade/revision.py`. */
export const REVISION_DELTA = 0.05;
export const REVISION_THETA = 0.30;
export const REVISION_MAX_AUTOCOMMIT = 12;

export interface RevisionInputDTO {
  /** Cascade-graph node id of the targeted claim. */
  claimId: string;
  /** Free-text description of the new evidence. */
  newEvidence: string;
  /** Signed weight in [-1, 1]. +1 = corroborates, -1 = contradicts. */
  weight: number;
}

export type ShiftClassification =
  | "changed"
  | "newly_contradicted"
  | "newly_supported"
  | "stable";

export interface ConfidenceShiftDTO {
  conclusionId: string;
  before: number;
  after: number;
  delta: number;
  classification: ShiftClassification;
}

export interface RevisionPlanDTO {
  planId: string;
  inputs: RevisionInputDTO[];
  changed: ConfidenceShiftDTO[];
  newlyContradicted: ConfidenceShiftDTO[];
  newlySupported: ConfidenceShiftDTO[];
  stableCount: number;
  consultedEdgeIds: string[];
  delta: number;
  theta: number;
}

export interface RevisionEventDTO {
  id: string;
  organizationId: string;
  founderId: string;
  planId: string;
  inputs: RevisionInputDTO[];
  plan: RevisionPlanDTO;
  preConfidenceSnapshot: Record<string, number>;
  affectedConclusionIds: string[];
  typedConfirmation: boolean;
  createdAt: string;
  revertedAt: string | null;
}

export function affectedCount(plan: RevisionPlanDTO): number {
  return (
    plan.changed.length +
    plan.newlyContradicted.length +
    plan.newlySupported.length
  );
}

/** True when the founder must type a confirmation phrase. Mirrors the
 * Python `RevisionPlan.requires_typed_confirmation`. */
export function requiresTypedConfirmation(
  plan: RevisionPlanDTO,
  k: number = REVISION_MAX_AUTOCOMMIT,
): boolean {
  return affectedCount(plan) > k;
}

// ── Persistence ─────────────────────────────────────────────────────────

/** Append a RevisionEvent row and return the DTO. Caller is responsible
 * for having computed the plan via the noosphere engine. */
export async function commitRevisionEvent(input: {
  organizationId: string;
  founderId: string;
  plan: RevisionPlanDTO;
  typedConfirmation: boolean;
}): Promise<RevisionEventDTO> {
  const { organizationId, founderId, plan, typedConfirmation } = input;

  const affected = [
    ...plan.changed.map((s) => s.conclusionId),
    ...plan.newlyContradicted.map((s) => s.conclusionId),
    ...plan.newlySupported.map((s) => s.conclusionId),
  ];

  const preSnapshot: Record<string, number> = {};
  for (const s of [
    ...plan.changed,
    ...plan.newlyContradicted,
    ...plan.newlySupported,
  ]) {
    preSnapshot[s.conclusionId] = s.before;
  }

  if (requiresTypedConfirmation(plan) && !typedConfirmation) {
    throw new Error(
      `Revision affects ${affectedCount(plan)} conclusions (> K=${REVISION_MAX_AUTOCOMMIT}); typed confirmation required.`,
    );
  }

  const row = await db.revisionEvent.create({
    data: {
      organizationId,
      founderId,
      planId: plan.planId,
      inputsJson: JSON.stringify(plan.inputs),
      planJson: JSON.stringify(plan),
      preConfidenceSnapshot: JSON.stringify(preSnapshot),
      affectedConclusionIds: JSON.stringify(affected),
      typedConfirmation,
    },
  });

  return rowToDTO(row);
}

export async function revertRevisionEvent(
  eventId: string,
): Promise<RevisionEventDTO | null> {
  const row = await db.revisionEvent.update({
    where: { id: eventId },
    data: { revertedAt: new Date() },
  });
  return rowToDTO(row);
}

export async function getRevisionEvent(
  eventId: string,
): Promise<RevisionEventDTO | null> {
  const row = await db.revisionEvent.findUnique({ where: { id: eventId } });
  return row ? rowToDTO(row) : null;
}

/** Most recent non-reverted event that touched a given conclusion.
 * Used by the public-article "updated" pill to decide whether to render
 * and where to link. */
export async function latestEventForConclusion(
  organizationId: string,
  conclusionId: string,
): Promise<RevisionEventDTO | null> {
  const candidates = await db.revisionEvent.findMany({
    where: {
      organizationId,
      revertedAt: null,
    },
    orderBy: { createdAt: "desc" },
    take: 50,
  });
  for (const row of candidates) {
    const ids = safeJsonArray(row.affectedConclusionIds) as string[];
    if (ids.includes(conclusionId)) {
      return rowToDTO(row);
    }
  }
  return null;
}

// ── Plain-prose diff renderer for /revisions/<id> ───────────────────────

/** Render the public diff prose used on `/revisions/<event-id>`.
 * Deliberately blunt: we don't editorialize; we report numbers and
 * classification labels. */
export function renderRevisionProse(
  event: RevisionEventDTO,
  conclusionTexts: Record<string, string>,
): string[] {
  const lines: string[] = [];
  for (const shift of event.plan.newlyContradicted) {
    const text = conclusionTexts[shift.conclusionId] ?? shift.conclusionId;
    lines.push(
      `We previously concluded "${text}" with confidence ${shift.before.toFixed(
        2,
      )}; new evidence has lowered our confidence to ${shift.after.toFixed(
        2,
      )} and we no longer hold this view.`,
    );
  }
  for (const shift of event.plan.newlySupported) {
    const text = conclusionTexts[shift.conclusionId] ?? shift.conclusionId;
    lines.push(
      `New evidence has raised our confidence in "${text}" from ${shift.before.toFixed(
        2,
      )} to ${shift.after.toFixed(2)}.`,
    );
  }
  for (const shift of event.plan.changed) {
    const text = conclusionTexts[shift.conclusionId] ?? shift.conclusionId;
    const direction = shift.delta < 0 ? "lowered" : "raised";
    lines.push(
      `Confidence in "${text}" was ${direction} from ${shift.before.toFixed(
        2,
      )} to ${shift.after.toFixed(2)}.`,
    );
  }
  return lines;
}

// ── internals ───────────────────────────────────────────────────────────

interface RevisionEventRow {
  id: string;
  organizationId: string;
  founderId: string;
  planId: string;
  inputsJson: string;
  planJson: string;
  preConfidenceSnapshot: string;
  affectedConclusionIds: string;
  typedConfirmation: boolean;
  createdAt: Date;
  revertedAt: Date | null;
}

function rowToDTO(row: RevisionEventRow): RevisionEventDTO {
  return {
    id: row.id,
    organizationId: row.organizationId,
    founderId: row.founderId,
    planId: row.planId,
    inputs: safeJsonArray(row.inputsJson) as unknown as RevisionInputDTO[],
    plan: safeJsonObject(row.planJson) as unknown as RevisionPlanDTO,
    preConfidenceSnapshot: safeJsonObject(
      row.preConfidenceSnapshot,
    ) as unknown as Record<string, number>,
    affectedConclusionIds: safeJsonArray(
      row.affectedConclusionIds,
    ) as unknown as string[],
    typedConfirmation: row.typedConfirmation,
    createdAt: row.createdAt.toISOString(),
    revertedAt: row.revertedAt ? row.revertedAt.toISOString() : null,
  };
}

function safeJsonArray(raw: string): unknown[] {
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function safeJsonObject(raw: string): Record<string, unknown> {
  try {
    const v = JSON.parse(raw);
    return v && typeof v === "object" && !Array.isArray(v)
      ? (v as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}
