-- Transcript explorer: durable blurb + line/chunk anchors.
ALTER TABLE "Upload"
  ADD COLUMN IF NOT EXISTS "blurb" TEXT;

CREATE TABLE IF NOT EXISTS "UploadChunk" (
  "id" TEXT NOT NULL,
  "uploadId" TEXT NOT NULL,
  "index" INTEGER NOT NULL,
  "text" TEXT NOT NULL,
  "startMs" INTEGER,
  "endMs" INTEGER,
  "speakerLabel" TEXT,
  "headingHint" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "UploadChunk_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "UploadChunk_uploadId_fkey"
    FOREIGN KEY ("uploadId") REFERENCES "Upload"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS "UploadChunk_uploadId_index_key"
  ON "UploadChunk"("uploadId", "index");

CREATE INDEX IF NOT EXISTS "UploadChunk_uploadId_idx"
  ON "UploadChunk"("uploadId");

-- Backfill existing uploads into paragraph chunks so old rows are
-- immediately addressable. Future ingestion preserves ids by upserting
-- unchanged chunks at the same zero-based index.
INSERT INTO "UploadChunk" ("id", "uploadId", "index", "text", "createdAt", "updatedAt")
SELECT
  'c' || substr(md5(u.id || ':' || (parts.ordinality - 1)::text || ':' || btrim(parts.chunk_text)), 1, 24),
  u.id,
  (parts.ordinality - 1)::integer,
  btrim(parts.chunk_text),
  CURRENT_TIMESTAMP,
  CURRENT_TIMESTAMP
FROM "Upload" u
CROSS JOIN LATERAL regexp_split_to_table(COALESCE(u."textContent", ''), E'\\n\\s*\\n+') WITH ORDINALITY AS parts(chunk_text, ordinality)
WHERE btrim(parts.chunk_text) <> ''
ON CONFLICT ("uploadId", "index") DO NOTHING;
