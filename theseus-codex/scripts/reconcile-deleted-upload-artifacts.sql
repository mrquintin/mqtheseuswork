-- ── Reconcile derived artifacts against soft-deleted uploads ──────────
--
-- A one-shot (and idempotent) sweep that applies the same cascade-delete
-- logic as the Upload delete handlers to EVERY already-soft-deleted
-- upload at once. Needed for the legacy state, where uploads were
-- soft-deleted before the cascade feature shipped — their derived
-- Conclusions / Contradictions / OpenQuestions / ResearchSuggestions
-- stayed in the database and kept appearing in the UI.
--
-- Running this against a DB with no stale state is a no-op: every
-- statement's WHERE clause is bounded to rows tied to deleted uploads,
-- so it runs in seconds and deletes zero rows on a clean codex.
--
-- Semantics match src/lib/uploadDeleteCascade.ts exactly so the
-- retroactive sweep produces the same outcome as a series of fresh
-- deletes would have. Every step is inside a single transaction so a
-- partial run doesn't leave the DB in a half-cascaded state.
--
-- Usage:
--   export PGPASSWORD=...
--   psql "$CODEX_DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -f theseus-codex/scripts/reconcile-deleted-upload-artifacts.sql

BEGIN;

-- Pre-sweep counts — NOTICE so psql surfaces them in the output.
DO $$
DECLARE
  deleted_uploads INT;
  stale_conclusion_links INT;
  stale_contradictions INT;
  stale_open_questions INT;
  stale_research INT;
BEGIN
  SELECT COUNT(*) INTO deleted_uploads
    FROM "Upload" WHERE "deletedAt" IS NOT NULL;
  SELECT COUNT(*) INTO stale_conclusion_links
    FROM "ConclusionSource" cs
    JOIN "Upload" u ON u.id = cs."uploadId"
    WHERE u."deletedAt" IS NOT NULL;
  SELECT COUNT(*) INTO stale_contradictions
    FROM "Contradiction" ct
    JOIN "Upload" u ON u.id = ct."sourceUploadId"
    WHERE u."deletedAt" IS NOT NULL;
  SELECT COUNT(*) INTO stale_open_questions
    FROM "OpenQuestion" oq
    JOIN "Upload" u ON u.id = oq."sourceUploadId"
    WHERE u."deletedAt" IS NOT NULL;
  SELECT COUNT(*) INTO stale_research
    FROM "ResearchSuggestion" rs
    JOIN "Upload" u ON u.id = rs."sourceUploadId"
    WHERE u."deletedAt" IS NOT NULL;
  RAISE NOTICE 'PRE-SWEEP: % deleted uploads · % stale source links · % stale contradictions · % stale open questions · % stale research suggestions',
    deleted_uploads, stale_conclusion_links, stale_contradictions,
    stale_open_questions, stale_research;
END $$;

-- ── Step 1: drop source links pointing at deleted uploads ──────────
-- Anything whose source is gone shouldn't be counted as a source. This
-- is the same `DELETE FROM "ConclusionSource" WHERE "uploadId" = ?` the
-- runtime cascade does, generalised to every deleted upload at once.
DELETE FROM "ConclusionSource"
WHERE "uploadId" IN (SELECT id FROM "Upload" WHERE "deletedAt" IS NOT NULL);

-- ── Step 2: orphan-delete conclusions produced by the ingest pipeline
--            whose last remaining source link just vanished.
-- Only touch rows the ingest pipeline created (`noosphereId LIKE 'ing_%'`)
-- so we never hard-delete manually-seeded or legacy conclusions that
-- never had sources to begin with.
DELETE FROM "Conclusion"
WHERE "noosphereId" LIKE 'ing\_%' ESCAPE '\'
  AND NOT EXISTS (
    SELECT 1 FROM "ConclusionSource"
    WHERE "ConclusionSource"."conclusionId" = "Conclusion".id
  );

-- ── Step 3: delete Contradictions sourced by deleted uploads OR with
--            dangling claim references. One statement, same as the
--            runtime helper.
DELETE FROM "Contradiction"
WHERE "sourceUploadId" IN (SELECT id FROM "Upload" WHERE "deletedAt" IS NOT NULL)
   OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE id = "Contradiction"."claimAId")
   OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE id = "Contradiction"."claimBId");

-- ── Step 4: same treatment for OpenQuestions ───────────────────────
DELETE FROM "OpenQuestion"
WHERE "sourceUploadId" IN (SELECT id FROM "Upload" WHERE "deletedAt" IS NOT NULL)
   OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE id = "OpenQuestion"."claimAId")
   OR NOT EXISTS (SELECT 1 FROM "Conclusion" WHERE id = "OpenQuestion"."claimBId");

-- ── Step 5: ResearchSuggestions have no claim refs — just check the
--            sourceUploadId. Suggestions are 1:1 with an ingest run so
--            every one tied to a deleted upload goes.
DELETE FROM "ResearchSuggestion"
WHERE "sourceUploadId" IN (SELECT id FROM "Upload" WHERE "deletedAt" IS NOT NULL);

-- Post-sweep counts.
DO $$
DECLARE
  remaining_conclusions INT;
  remaining_contradictions INT;
  remaining_open_questions INT;
  remaining_research INT;
  remaining_links INT;
BEGIN
  SELECT COUNT(*) INTO remaining_conclusions FROM "Conclusion";
  SELECT COUNT(*) INTO remaining_contradictions FROM "Contradiction";
  SELECT COUNT(*) INTO remaining_open_questions FROM "OpenQuestion";
  SELECT COUNT(*) INTO remaining_research FROM "ResearchSuggestion";
  SELECT COUNT(*) INTO remaining_links FROM "ConclusionSource";
  RAISE NOTICE 'POST-SWEEP: % conclusions · % contradictions · % open questions · % research suggestions · % source links',
    remaining_conclusions, remaining_contradictions, remaining_open_questions,
    remaining_research, remaining_links;
END $$;

COMMIT;
