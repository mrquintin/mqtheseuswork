DROP INDEX IF EXISTS "ContactSubmission_email_idx";

ALTER TABLE "ContactSubmission"
RENAME COLUMN "email" TO "fromEmail";

ALTER TABLE "ContactSubmission"
RENAME COLUMN "message" TO "body";

ALTER TABLE "ContactSubmission"
RENAME COLUMN "name" TO "fromName";

ALTER TABLE "ContactSubmission"
ADD COLUMN "organizationId" TEXT,
ADD COLUMN "ipHash" TEXT,
ADD COLUMN "userAgent" TEXT,
ADD COLUMN "triagedAt" TIMESTAMP(3),
ADD COLUMN "triagedBy" TEXT,
ADD COLUMN "notes" TEXT;

UPDATE "ContactSubmission"
SET
  "fromName" = COALESCE(NULLIF(BTRIM("fromName"), ''), 'Unknown'),
  "ipHash" = 'legacy';

ALTER TABLE "ContactSubmission"
ALTER COLUMN "fromName" SET NOT NULL,
ALTER COLUMN "ipHash" SET NOT NULL;

ALTER TABLE "ContactSubmission"
DROP COLUMN "sourcePath";

CREATE INDEX "ContactSubmission_fromEmail_idx" ON "ContactSubmission"("fromEmail");
CREATE INDEX "ContactSubmission_ipHash_createdAt_idx" ON "ContactSubmission"("ipHash", "createdAt");
CREATE INDEX "ContactSubmission_triagedAt_createdAt_idx" ON "ContactSubmission"("triagedAt", "createdAt");
