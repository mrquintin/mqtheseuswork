-- Phase-2 follow-up: Prisma now owns LogicalAlgorithm and the noosphere
-- ORM was rewritten to write to it. noosphere's StoredLogicalAlgorithm
-- carries a `provenance` column (default "PROPRIETARY") inherited from
-- prompt 09's ProvenanceKind. The Prisma schema didn't have this field
-- yet — without this migration, the first noosphere write would fail
-- with `column "provenance" does not exist`.
--
-- The migration mirrors `20260516230000_provenance_kind` (which added
-- the same column to Upload): NOT NULL with a PROPRIETARY default so
-- existing rows backfill cleanly without operator intervention.

ALTER TABLE "LogicalAlgorithm"
    ADD COLUMN "provenance" "ProvenanceKind" NOT NULL DEFAULT 'PROPRIETARY';

-- Hot index for the Oracle / synthesis filter, mirroring the matching
-- compound index on Upload. organizationId leads so per-tenant scans
-- stay cheap; provenance narrows to one bucket.
CREATE INDEX "LogicalAlgorithm_organizationId_provenance_idx"
    ON "LogicalAlgorithm"("organizationId", "provenance");
