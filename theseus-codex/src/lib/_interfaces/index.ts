/**
 * Shared type-only contracts for the theseus-codex ``lib/`` perimeter.
 *
 * Why this file exists
 * --------------------
 *
 * Round 17 found two pairs of modules tugging on each other in the
 * TypeScript graph: lineage <-> revision events, and methodTrackRecord <->
 * MQS-reading consumers. The current snapshot of the import graph is
 * acyclic (the cyclic-import detector reports zero size-2-or-larger SCCs
 * for ``src/lib/``), but the *shape* of the handoffs is still defined
 * inline in each side, so a future edit could easily reintroduce a cycle.
 *
 * This module is the type-only seam where those shapes live. Consumers
 * import them with ``import type`` so the references erase at compile time
 * and contribute no runtime edge:
 *
 *   import type { LineageReader, TrackRecordRow } from "@/lib/_interfaces";
 *
 * Rules
 * -----
 * 1. **Type-only.** No runtime values. No classes with bodies, no
 *    enums-with-values, no const arrays. Only ``type``, ``interface``,
 *    and re-exports of other type-only modules.
 * 2. **No upward imports.** Never import from another ``lib/`` module
 *    here — that would re-create the cycle this file exists to prevent.
 * 3. **One shape per concern.** If two modules need a shared shape, put
 *    it here and have them both ``import type`` it. Don't duplicate.
 */

// ── Lineage / revision events ──────────────────────────────────────────────

export type RevisionEventLike = {
  conclusionId: string;
  revisedAt: string; // ISO-8601
  actor: string;
  rationale: string;
};

export type LineageNodeLike = {
  id: string;
  conclusionId: string;
  revisedAt: string;
  publicVisible: boolean;
};

export interface LineageReader {
  getLineage(conclusionId: string): Promise<LineageNodeLike[]>;
}

// ── Method track record / MQS surfacing ────────────────────────────────────

export type TrackRecordRow = {
  methodName: string;
  methodVersion: string;
  domain: string;
  sampleSize: number;
  calibrationSlope: number | null;
  calibrationSlopeCiLow: number | null;
  calibrationSlopeCiHigh: number | null;
  severityPassRate: number | null;
};

export interface TrackRecordReader {
  getTrackRecord(
    methodName: string,
    methodVersion: string,
    domain?: string,
  ): Promise<TrackRecordRow | null>;
}

export interface MqsScorer {
  score(input: {
    methodName: string;
    methodVersion: string;
    domain?: string;
  }): Promise<number>;
}

// ── Generic narrow readers (so callers can avoid hauling in a full store) ──

export interface ConclusionReader {
  getConclusion(conclusionId: string): Promise<unknown>;
}

export interface ReviewerLike {
  readonly name: string;
  review(conclusion: unknown, context?: Record<string, unknown>): Promise<unknown>;
}
