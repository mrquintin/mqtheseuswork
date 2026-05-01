-- Held outbound social posts. The default system posture remains inert:
-- rows are created as draft/rejected/failed until an operator explicitly
-- approves, and the live client still requires env gates before sending.
CREATE TABLE IF NOT EXISTS "SocialPost" (
  "id" TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "source" TEXT NOT NULL,
  "sourceId" TEXT,
  "platform" TEXT NOT NULL,
  "body" TEXT NOT NULL,
  "media" JSONB,
  "status" TEXT NOT NULL,
  "approvedBy" TEXT,
  "approvedAt" TIMESTAMP(3),
  "postedAt" TIMESTAMP(3),
  "externalId" TEXT,
  "failureReason" TEXT,

  CONSTRAINT "SocialPost_pkey" PRIMARY KEY ("id")
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'SocialPost_organizationId_fkey'
  ) THEN
    ALTER TABLE "SocialPost"
      ADD CONSTRAINT "SocialPost_organizationId_fkey"
      FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS "SocialPost_organizationId_status_createdAt_idx"
  ON "SocialPost"("organizationId", "status", "createdAt");
CREATE INDEX IF NOT EXISTS "SocialPost_platform_status_postedAt_idx"
  ON "SocialPost"("platform", "status", "postedAt");
CREATE INDEX IF NOT EXISTS "SocialPost_source_sourceId_idx"
  ON "SocialPost"("source", "sourceId");

-- Generic operator override state. `theseus.x_kill` is the current X key:
-- if its value has {"disabled": true}, social posting is disabled even when
-- THESEUS_X_POSTING_ENABLED=true.
CREATE TABLE IF NOT EXISTS "OperatorState" (
  "id" TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "key" TEXT NOT NULL,
  "value" JSONB NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,

  CONSTRAINT "OperatorState_pkey" PRIMARY KEY ("id")
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'OperatorState_organizationId_fkey'
  ) THEN
    ALTER TABLE "OperatorState"
      ADD CONSTRAINT "OperatorState_organizationId_fkey"
      FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS "OperatorState_organizationId_key_key"
  ON "OperatorState"("organizationId", "key");
CREATE INDEX IF NOT EXISTS "OperatorState_key_idx"
  ON "OperatorState"("key");
