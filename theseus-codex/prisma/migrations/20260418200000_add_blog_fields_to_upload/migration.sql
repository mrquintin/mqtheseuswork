-- ── Blog/public fields on Upload ─────────────────────────────────────
-- Additive only: every column is NULL-defaulted so existing rows remain
-- valid and stay "private" (publishedAt IS NULL). No data-loss risk.
ALTER TABLE "Upload"
  ADD COLUMN IF NOT EXISTS "publishedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "slug"         TEXT,
  ADD COLUMN IF NOT EXISTS "blogExcerpt"  TEXT,
  ADD COLUMN IF NOT EXISTS "authorBio"    TEXT;

-- `slug` must be globally unique across the whole blog surface so that
-- /post/:slug is unambiguous. NULL values are allowed because private
-- uploads don't have a slug yet.
CREATE UNIQUE INDEX IF NOT EXISTS "Upload_slug_key" ON "Upload"("slug");

-- Secondary index to keep /post index queries snappy as the blog grows.
CREATE INDEX IF NOT EXISTS "Upload_publishedAt_idx" ON "Upload"("publishedAt");
