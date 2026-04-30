-- Add a discriminator for generated longform articles sharing /c/[slug].
ALTER TABLE "PublishedConclusion"
ADD COLUMN "kind" TEXT NOT NULL DEFAULT 'CONCLUSION';

CREATE INDEX "PublishedConclusion_kind_publishedAt_idx"
ON "PublishedConclusion"("kind", "publishedAt");
