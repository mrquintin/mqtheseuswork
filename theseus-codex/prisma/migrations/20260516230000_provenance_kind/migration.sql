-- Round 19 prompt 09: ProvenanceKind demarcation on Upload.
--
-- Adds the four-kind provenance enum and two columns to the Upload
-- table. PROPRIETARY is the default — every existing row backfills to
-- it via the column default, and the founder reviews via the
-- `/library/triage` flow.
--
-- `visibility` (who-can-read) is unchanged and intentionally distinct
-- from `provenance` (who-authored). They answer different questions
-- and must not be conflated.

-- 1. The enum.
CREATE TYPE "ProvenanceKind" AS ENUM (
    'PROPRIETARY',
    'ENDORSED_EXTERNAL',
    'STUDIED_EXTERNAL',
    'OPPOSING_EXTERNAL'
);

-- 2. Columns on Upload. Existing rows backfill to PROPRIETARY via the
--    column default; the founder retags external sources via triage.
ALTER TABLE "Upload"
    ADD COLUMN "provenance" "ProvenanceKind" NOT NULL DEFAULT 'PROPRIETARY';

ALTER TABLE "Upload"
    ADD COLUMN "provenanceRationale" TEXT;

-- 3. Hot index for the Oracle / synthesis filter and the library page.
--    `organizationId` is the leading column so per-tenant scans stay
--    cheap; provenance narrows to one bucket; createdAt sort:Desc lets
--    the planner walk the index in order and stop at LIMIT N.
CREATE INDEX "Upload_org_provenance_createdAt_idx"
    ON "Upload"("organizationId", "provenance", "createdAt" DESC);
