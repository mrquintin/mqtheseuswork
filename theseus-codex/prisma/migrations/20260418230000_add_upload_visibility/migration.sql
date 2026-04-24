-- ── Upload visibility (org vs private) ────────────────────────────────
-- Additive + default "org", so every existing row keeps its current
-- behaviour (visible to the whole firm in /library). Only rows the
-- uploader explicitly flips to "private" are hidden from peers. The
-- column is NOT NULL with a default so we don't have to back-fill.
ALTER TABLE "Upload"
  ADD COLUMN IF NOT EXISTS "visibility" TEXT NOT NULL DEFAULT 'org';

CREATE INDEX IF NOT EXISTS "Upload_visibility_idx"
  ON "Upload"("visibility");
