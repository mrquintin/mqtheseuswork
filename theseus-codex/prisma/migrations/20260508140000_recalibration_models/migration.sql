-- Recalibration: per-domain isotonic mapping (raw → calibrated)
-- and a founder-set per-conclusion opt-out.

CREATE TABLE "CalibrationModel" (
  "id"             TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "domain"         TEXT NOT NULL,
  "version"        INTEGER NOT NULL,
  "fitAt"          TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "sampleSize"     INTEGER NOT NULL,
  "resolutionHash" TEXT NOT NULL,
  "knots"          JSONB NOT NULL,
  "active"         BOOLEAN NOT NULL DEFAULT TRUE,
  "createdAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "CalibrationModel_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "CalibrationModel_organizationId_domain_version_key"
  ON "CalibrationModel"("organizationId", "domain", "version");

CREATE INDEX "CalibrationModel_organizationId_domain_active_idx"
  ON "CalibrationModel"("organizationId", "domain", "active");

CREATE INDEX "CalibrationModel_organizationId_domain_fitAt_idx"
  ON "CalibrationModel"("organizationId", "domain", "fitAt");

ALTER TABLE "CalibrationModel"
  ADD CONSTRAINT "CalibrationModel_organizationId_fkey"
  FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;


CREATE TABLE "RecalibrationOverride" (
  "id"             TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "conclusionId"   TEXT NOT NULL,
  "founderId"      TEXT NOT NULL,
  "reason"         TEXT NOT NULL DEFAULT '',
  "createdAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "RecalibrationOverride_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "RecalibrationOverride_conclusionId_key"
  ON "RecalibrationOverride"("conclusionId");

CREATE INDEX "RecalibrationOverride_organizationId_idx"
  ON "RecalibrationOverride"("organizationId");

CREATE INDEX "RecalibrationOverride_founderId_idx"
  ON "RecalibrationOverride"("founderId");

ALTER TABLE "RecalibrationOverride"
  ADD CONSTRAINT "RecalibrationOverride_organizationId_fkey"
  FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "RecalibrationOverride"
  ADD CONSTRAINT "RecalibrationOverride_conclusionId_fkey"
  FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "RecalibrationOverride"
  ADD CONSTRAINT "RecalibrationOverride_founderId_fkey"
  FOREIGN KEY ("founderId") REFERENCES "Founder"("id")
  ON DELETE NO ACTION ON UPDATE CASCADE;
