-- ── Conclusion source tracking + derived-entity cascade ─────────────
--
-- Before this migration, every Conclusion / Contradiction / OpenQuestion /
-- ResearchSuggestion row was an orphan of its source: there was no direct
-- back-reference to the Upload that produced it, and deleting an Upload
-- left all its derived artifacts in the database forever.
--
-- This migration introduces proper provenance so the delete path can
-- cascade correctly:
--
--   1. Conclusion gets a `normalizedText` column used as a dedup key —
--      two uploads that extract the same claim land on the same
--      Conclusion row.
--   2. A new `ConclusionSource` join table records every (conclusion,
--      upload) pair. When an upload is deleted we drop its links; a
--      conclusion with zero remaining sources is hard-deleted, a
--      conclusion still supported by other uploads stays with its
--      remaining source list.
--   3. Contradiction / OpenQuestion / ResearchSuggestion each get a
--      single `sourceUploadId` — they're each the product of exactly
--      ONE ingestion run, even if they reference claims from multiple
--      uploads. When their source upload is deleted, they go with it.
--
-- Every statement uses `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` so
-- re-running against a DB that's already been migrated is a no-op.

-- ── Conclusion.normalizedText + ConclusionSource ────────────────────

ALTER TABLE "Conclusion"
  ADD COLUMN IF NOT EXISTS "normalizedText" TEXT;

CREATE INDEX IF NOT EXISTS "Conclusion_organizationId_normalizedText_idx"
  ON "Conclusion"("organizationId", "normalizedText");

CREATE TABLE IF NOT EXISTS "ConclusionSource" (
  "conclusionId" TEXT NOT NULL,
  "uploadId"     TEXT NOT NULL,
  "createdAt"    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ConclusionSource_pkey" PRIMARY KEY ("conclusionId", "uploadId")
);

-- Cascade on HARD-delete of either side. The normal delete path in the
-- app soft-deletes Upload and hard-deletes orphaned Conclusions; this
-- is a belt-and-suspenders for org takedowns / privacy purges where a
-- row is hard-deleted directly.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ConclusionSource_conclusionId_fkey'
  ) THEN
    ALTER TABLE "ConclusionSource"
      ADD CONSTRAINT "ConclusionSource_conclusionId_fkey"
      FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ConclusionSource_uploadId_fkey'
  ) THEN
    ALTER TABLE "ConclusionSource"
      ADD CONSTRAINT "ConclusionSource_uploadId_fkey"
      FOREIGN KEY ("uploadId") REFERENCES "Upload"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS "ConclusionSource_conclusionId_idx"
  ON "ConclusionSource"("conclusionId");
CREATE INDEX IF NOT EXISTS "ConclusionSource_uploadId_idx"
  ON "ConclusionSource"("uploadId");

-- ── sourceUploadId on the three single-source entities ──────────────

ALTER TABLE "Contradiction"
  ADD COLUMN IF NOT EXISTS "sourceUploadId" TEXT;

ALTER TABLE "OpenQuestion"
  ADD COLUMN IF NOT EXISTS "sourceUploadId" TEXT;

ALTER TABLE "ResearchSuggestion"
  ADD COLUMN IF NOT EXISTS "sourceUploadId" TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'Contradiction_sourceUploadId_fkey'
  ) THEN
    ALTER TABLE "Contradiction"
      ADD CONSTRAINT "Contradiction_sourceUploadId_fkey"
      FOREIGN KEY ("sourceUploadId") REFERENCES "Upload"("id")
      ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'OpenQuestion_sourceUploadId_fkey'
  ) THEN
    ALTER TABLE "OpenQuestion"
      ADD CONSTRAINT "OpenQuestion_sourceUploadId_fkey"
      FOREIGN KEY ("sourceUploadId") REFERENCES "Upload"("id")
      ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ResearchSuggestion_sourceUploadId_fkey'
  ) THEN
    ALTER TABLE "ResearchSuggestion"
      ADD CONSTRAINT "ResearchSuggestion_sourceUploadId_fkey"
      FOREIGN KEY ("sourceUploadId") REFERENCES "Upload"("id")
      ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS "Contradiction_sourceUploadId_idx"
  ON "Contradiction"("sourceUploadId");
CREATE INDEX IF NOT EXISTS "OpenQuestion_sourceUploadId_idx"
  ON "OpenQuestion"("sourceUploadId");
CREATE INDEX IF NOT EXISTS "ResearchSuggestion_sourceUploadId_idx"
  ON "ResearchSuggestion"("sourceUploadId");

-- ── Backfill normalizedText ─────────────────────────────────────────
--
-- Every existing Conclusion gets its normalizedText computed once. The
-- formula matches the Python side in codex_bridge.py so a claim ingested
-- in the future will hash to the same key a claim ingested before this
-- migration already has.

UPDATE "Conclusion"
SET "normalizedText" = LOWER(TRIM(REGEXP_REPLACE(text, '\s+', ' ', 'g')))
WHERE "normalizedText" IS NULL
  AND text IS NOT NULL
  AND LENGTH(text) > 0;

-- ── Backfill ConclusionSource from noosphereId ──────────────────────
--
-- The ingest pipeline writes noosphereId = 'ing_<uploadId>_<idx>' for
-- every conclusion it creates. Parse the uploadId out of that and
-- insert a source row for each existing conclusion. Only runs for rows
-- where the referenced upload still exists — rows pointing at already-
-- deleted uploads would violate the FK.

INSERT INTO "ConclusionSource" ("conclusionId", "uploadId", "createdAt")
SELECT c.id,
       u.id,
       c."createdAt"
FROM "Conclusion" c
JOIN "Upload" u
  ON u.id = SUBSTRING(c."noosphereId" FROM '^ing_([^_]+)_')
WHERE c."noosphereId" LIKE 'ing\_%\_%' ESCAPE '\'
ON CONFLICT ("conclusionId", "uploadId") DO NOTHING;

-- ── Backfill sourceUploadId on OpenQuestion and ResearchSuggestion ──

UPDATE "OpenQuestion" oq
SET "sourceUploadId" = u.id
FROM "Upload" u
WHERE oq."noosphereId" LIKE 'oq\_%\_%' ESCAPE '\'
  AND u.id = SUBSTRING(oq."noosphereId" FROM '^oq_([^_]+)_')
  AND oq."sourceUploadId" IS NULL;

UPDATE "ResearchSuggestion" rs
SET "sourceUploadId" = u.id
FROM "Upload" u
WHERE rs."noosphereId" LIKE 'rs\_%\_%' ESCAPE '\'
  AND u.id = SUBSTRING(rs."noosphereId" FROM '^rs_([^_]+)_')
  AND rs."sourceUploadId" IS NULL;

-- ── Backfill sourceUploadId on Contradiction (best-effort) ─────────
--
-- Contradiction rows don't encode an upload id in their noosphereId
-- (they don't have one at all). The next best signal is claimAId →
-- the source upload of the first claim. Most contradictions are
-- within-upload pairs, so claim A and claim B come from the same
-- upload anyway; cross-upload contradictions get claimA's source,
-- which is correct (it was the ingestion that produced the
-- contradiction).

UPDATE "Contradiction" c
SET "sourceUploadId" = (
  SELECT cs."uploadId"
  FROM "ConclusionSource" cs
  WHERE cs."conclusionId" = c."claimAId"
  ORDER BY cs."createdAt" ASC
  LIMIT 1
)
WHERE c."sourceUploadId" IS NULL;
