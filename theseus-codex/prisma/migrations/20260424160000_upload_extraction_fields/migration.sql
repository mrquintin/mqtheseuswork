-- Wave 1 / prompt 04 — surface the ingest pipeline in the Codex dashboard.
--
-- * `extractionMethod` records how the text content was obtained
--   (passthrough | faster-whisper | openai-whisper-1 | pypdf | ocrmypdf),
--   written by the noosphere dispatcher on success. Null for rows
--   created before the dispatcher landed or still in flight.
--
-- * `Upload_status_idx` — the dashboard filters by status on every
--   render ("ingested" for the main panel, counts for "failed" /
--   "pending" / "processing"). A plain btree index cuts the planner's
--   sequential scan on larger orgs. `errorMessage` was already added
--   by the init migration; nothing to do there.

ALTER TABLE "Upload"
  ADD COLUMN "extractionMethod" TEXT;

CREATE INDEX "Upload_status_idx" ON "Upload"("status");
