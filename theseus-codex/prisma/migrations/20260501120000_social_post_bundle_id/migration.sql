-- Link draft rows created from the same "publish to both" operator action.
ALTER TABLE "SocialPost"
  ADD COLUMN IF NOT EXISTS "bundleId" UUID;

CREATE INDEX IF NOT EXISTS "SocialPost_bundleId_idx"
  ON "SocialPost"("bundleId");
