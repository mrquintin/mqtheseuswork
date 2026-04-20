import type { Prisma, PrismaClient } from "@prisma/client";

/**
 * Cascade-clean derived entities when an Upload is soft-deleted.
 *
 * The delete flow has two user-facing entry points (the owner's direct
 * `/api/upload/:id/delete` and the peer-approved
 * `/api/deletion-requests/:id` accept path), and they both need to do the
 * same downstream bookkeeping. This helper owns that logic so the two
 * routes stay in sync.
 *
 * Semantics (run AFTER the caller has already set `deletedAt` on the
 * Upload, inside the same $transaction):
 *
 *   1. Drop every `ConclusionSource` row whose `uploadId` matches the
 *      deleted upload. That's the link between the upload and any
 *      conclusions it sourced.
 *
 *   2. For each Conclusion that WAS sourced by this upload, if it now
 *      has zero remaining `ConclusionSource` rows, hard-delete it. A
 *      conclusion still supported by another upload stays — the only
 *      difference is the sources array shrinks by one.
 *
 *   3. Delete every Contradiction / OpenQuestion whose `sourceUploadId`
 *      matched this upload (they were the output of that ingestion run
 *      and no longer have any reason to exist) OR whose `claimAId` /
 *      `claimBId` now references a deleted Conclusion (the pair one
 *      side of referred to is gone, so the contradiction / question is
 *      structurally broken).
 *
 *   4. Delete every ResearchSuggestion whose `sourceUploadId` matches.
 *      Suggestions aren't de-duplicated, so a single source is all
 *      we need to check.
 *
 * Returns a counts object so the caller can log / return it for the UI.
 *
 * Implementation notes:
 *   - We use `$executeRawUnsafe` / `$executeRaw` deliberately — Prisma's
 *     query builder can't express "DELETE WHERE NOT EXISTS (...)" in a
 *     single round-trip and we care about atomicity here.
 *   - Every statement is scoped to THIS upload id; no other tenants'
 *     rows are touchable from this path.
 *   - Accepts a `PrismaClient` OR a `Prisma.TransactionClient` so the
 *     caller can chain this inside an existing `db.$transaction(async (tx) => ...)`
 *     without nesting transactions.
 */
export interface CascadeCounts {
  conclusionSourcesRemoved: number;
  conclusionsOrphanDeleted: number;
  contradictionsDeleted: number;
  openQuestionsDeleted: number;
  researchSuggestionsDeleted: number;
}

type TxClient = PrismaClient | Prisma.TransactionClient;

export async function cascadeDeleteUploadArtifacts(
  tx: TxClient,
  uploadId: string,
): Promise<CascadeCounts> {
  // ── 1. Remember which conclusions this upload sourced, so we know
  //       which ones to check for "still sourced by anyone else" after
  //       we drop the links. We fetch the ids eagerly (not a subquery
  //       inside the DELETE) so we can also report the count back.
  const sourceRows = await tx.$queryRaw<{ conclusionId: string }[]>`
    SELECT "conclusionId" FROM "ConclusionSource" WHERE "uploadId" = ${uploadId}
  `;
  const conclusionIds = sourceRows.map((r) => r.conclusionId);

  // ── 2. Drop the source links.
  const sourcesRemoved = await tx.$executeRaw`
    DELETE FROM "ConclusionSource" WHERE "uploadId" = ${uploadId}
  `;

  // ── 3. Hard-delete orphan conclusions (no ConclusionSource rows left).
  //        The NOT EXISTS subquery re-checks the live state AFTER step 2,
  //        so a conclusion that was sourced by this upload AND one other
  //        upload stays — it's sourced by the other upload only now.
  let orphansDeleted = 0;
  if (conclusionIds.length > 0) {
    orphansDeleted = await tx.$executeRaw`
      DELETE FROM "Conclusion"
      WHERE id = ANY(${conclusionIds}::text[])
        AND NOT EXISTS (
          SELECT 1 FROM "ConclusionSource"
          WHERE "ConclusionSource"."conclusionId" = "Conclusion".id
        )
    `;
  }

  // ── 4. Delete Contradictions / OpenQuestions whose source upload was
  //        this one, OR whose claim references are now dangling. Doing
  //        both predicates in one statement means we don't need a
  //        round-trip to find the orphans.
  const contradictionsDeleted = await tx.$executeRaw`
    DELETE FROM "Contradiction"
    WHERE "sourceUploadId" = ${uploadId}
       OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE "Conclusion".id = "Contradiction"."claimAId")
       OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE "Conclusion".id = "Contradiction"."claimBId")
  `;

  const openQuestionsDeleted = await tx.$executeRaw`
    DELETE FROM "OpenQuestion"
    WHERE "sourceUploadId" = ${uploadId}
       OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE "Conclusion".id = "OpenQuestion"."claimAId")
       OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE "Conclusion".id = "OpenQuestion"."claimBId")
  `;

  // ── 5. ResearchSuggestions have only the one pointer, no claim refs.
  const researchSuggestionsDeleted = await tx.$executeRaw`
    DELETE FROM "ResearchSuggestion" WHERE "sourceUploadId" = ${uploadId}
  `;

  return {
    conclusionSourcesRemoved: Number(sourcesRemoved),
    conclusionsOrphanDeleted: Number(orphansDeleted),
    contradictionsDeleted: Number(contradictionsDeleted),
    openQuestionsDeleted: Number(openQuestionsDeleted),
    researchSuggestionsDeleted: Number(researchSuggestionsDeleted),
  };
}

/**
 * Format the cascade-delete counts as an audit-log-friendly string.
 *
 * Used by the two delete routes so the `AuditEvent.detail` they write
 * surfaces exactly what went down the drain with the upload — useful
 * when a founder accidentally deletes a big upload and wants to tell
 * at a glance how much derived work was lost.
 */
export function formatCascadeCounts(counts: CascadeCounts): string {
  const parts: string[] = [];
  if (counts.conclusionSourcesRemoved > 0) {
    parts.push(`${counts.conclusionSourcesRemoved} source link(s) removed`);
  }
  if (counts.conclusionsOrphanDeleted > 0) {
    parts.push(`${counts.conclusionsOrphanDeleted} conclusion(s) orphan-deleted`);
  }
  if (counts.contradictionsDeleted > 0) {
    parts.push(`${counts.contradictionsDeleted} contradiction(s) deleted`);
  }
  if (counts.openQuestionsDeleted > 0) {
    parts.push(`${counts.openQuestionsDeleted} open question(s) deleted`);
  }
  if (counts.researchSuggestionsDeleted > 0) {
    parts.push(`${counts.researchSuggestionsDeleted} research suggestion(s) deleted`);
  }
  if (parts.length === 0) {
    return "no derived artifacts affected";
  }
  return parts.join(" · ");
}
