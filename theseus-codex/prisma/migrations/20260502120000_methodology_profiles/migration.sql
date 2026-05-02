-- Store how Theseus reaches conclusions, not only the conclusions themselves.
CREATE TABLE "MethodologyProfile" (
  "id" TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "uploadId" TEXT,
  "conclusionId" TEXT,
  "sourceKind" TEXT NOT NULL DEFAULT 'UPLOAD',
  "patternType" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "summary" TEXT NOT NULL,
  "reasoningMoves" JSONB NOT NULL,
  "transferTargets" JSONB NOT NULL,
  "assumptions" JSONB NOT NULL,
  "failureModes" JSONB NOT NULL,
  "evidenceAnchors" JSONB NOT NULL,
  "confidence" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  "dedupeKey" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "MethodologyProfile_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "MethodologyProfile_organizationId_dedupeKey_key"
  ON "MethodologyProfile"("organizationId", "dedupeKey");

CREATE INDEX "MethodologyProfile_organizationId_createdAt_idx"
  ON "MethodologyProfile"("organizationId", "createdAt");

CREATE INDEX "MethodologyProfile_organizationId_patternType_idx"
  ON "MethodologyProfile"("organizationId", "patternType");

CREATE INDEX "MethodologyProfile_uploadId_idx"
  ON "MethodologyProfile"("uploadId");

CREATE INDEX "MethodologyProfile_conclusionId_idx"
  ON "MethodologyProfile"("conclusionId");

ALTER TABLE "MethodologyProfile"
  ADD CONSTRAINT "MethodologyProfile_organizationId_fkey"
  FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "MethodologyProfile"
  ADD CONSTRAINT "MethodologyProfile_uploadId_fkey"
  FOREIGN KEY ("uploadId") REFERENCES "Upload"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "MethodologyProfile"
  ADD CONSTRAINT "MethodologyProfile_conclusionId_fkey"
  FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;
