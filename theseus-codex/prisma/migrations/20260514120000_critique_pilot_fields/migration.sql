-- Round-17 prompt 44: open-critique pilot fields on CritiqueSubmission.

ALTER TABLE "CritiqueSubmission"
  ADD COLUMN "pilotTag" TEXT NOT NULL DEFAULT '',
  ADD COLUMN "pilotReviewerSlug" TEXT NOT NULL DEFAULT '',
  ADD COLUMN "hallOfFameConsent" BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX "CritiqueSubmission_organizationId_pilotTag_status_idx"
  ON "CritiqueSubmission" ("organizationId", "pilotTag", "status");
