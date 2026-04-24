-- ── Audio playback fields on Upload ──────────────────────────────────
-- `audioUrl` is the public CDN URL of an uploaded audio file (Supabase
-- Storage when configured). When set, /post/[slug] renders an <audio
-- controls> player alongside the transcript so a published podcast
-- episode plays back directly on the blog.
--
-- `audioDurationSec` is optional metadata — nice for the cards on the
-- blog index. Client-side upload code fills it from the browser's
-- HTMLMediaElement.duration on the original file before upload.
--
-- Both columns are nullable so every existing row keeps its current
-- behaviour. No back-fill needed.
ALTER TABLE "Upload"
  ADD COLUMN IF NOT EXISTS "audioUrl" TEXT,
  ADD COLUMN IF NOT EXISTS "audioDurationSec" INTEGER;
