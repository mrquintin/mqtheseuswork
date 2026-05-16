-- Prompt 05 of Round 19 (2026-05-16): Algorithm calibration loop.
--
-- An algorithm should earn its life. Each invocation eventually
-- resolves; the resolution updates the algorithm's track record;
-- bad algorithms retire; good ones get promoted to higher-confidence
-- weighting in the synthesizer.
--
-- Adds:
--   * weightingMultiplier column on LogicalAlgorithm (default 1.0,
--     bounded [0.0, 2.0] by check constraint).
--   * AlgorithmCalibrationSnapshot — append-only per-tick snapshot.
--   * AlgorithmTriageRecommendation — operator-visible PENDING /
--     ACCEPTED / REJECTED / DEFERRED queue rows.
--
-- Mirror: noosphere/alembic/versions/014_algorithm_calibration.py

ALTER TABLE "LogicalAlgorithm"
  ADD COLUMN "weightingMultiplier" DOUBLE PRECISION NOT NULL DEFAULT 1.0;

ALTER TABLE "LogicalAlgorithm"
  ADD CONSTRAINT "LogicalAlgorithm_weightingMultiplier_range_check"
  CHECK ("weightingMultiplier" >= 0.0 AND "weightingMultiplier" <= 2.0);

CREATE TYPE "AlgorithmTriageAction" AS ENUM (
  'NONE',
  'RETIRE',
  'PROMOTE'
);

CREATE TYPE "AlgorithmTriageStatus" AS ENUM (
  'PENDING',
  'ACCEPTED',
  'REJECTED',
  'DEFERRED'
);

CREATE TABLE "AlgorithmCalibrationSnapshot" (
  "id"                          TEXT PRIMARY KEY,
  "algorithmId"                 TEXT NOT NULL,
  "organizationId"              TEXT NOT NULL,
  "snapshotAt"                  TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "totalInvocations"            INTEGER NOT NULL DEFAULT 0,
  "resolvedInvocations"         INTEGER NOT NULL DEFAULT 0,
  "accuracy"                    DOUBLE PRECISION,
  "meanBrier"                   DOUBLE PRECISION,
  "meanHorizonError"            DOUBLE PRECISION,
  "directionalAccuracy"         DOUBLE PRECISION,
  "confidenceCalibrationDrift"  DOUBLE PRECISION,
  "last30dAccuracy"             DOUBLE PRECISION,
  "last30dResolved"             INTEGER NOT NULL DEFAULT 0,
  "probabilisticResolved"       INTEGER NOT NULL DEFAULT 0,
  "directionalResolved"         INTEGER NOT NULL DEFAULT 0,
  "confidenceBandResolved"      INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT "AlgorithmCalibrationSnapshot_algorithmId_fkey"
    FOREIGN KEY ("algorithmId") REFERENCES "LogicalAlgorithm"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "AlgorithmCalibrationSnapshot_algorithm_at_idx"
  ON "AlgorithmCalibrationSnapshot" ("algorithmId", "snapshotAt" DESC);
CREATE INDEX "AlgorithmCalibrationSnapshot_org_at_idx"
  ON "AlgorithmCalibrationSnapshot" ("organizationId", "snapshotAt" DESC);

CREATE TABLE "AlgorithmTriageRecommendation" (
  "id"                     TEXT PRIMARY KEY,
  "algorithmId"            TEXT NOT NULL,
  "organizationId"         TEXT NOT NULL,
  "recommendedAt"          TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "recommendedAction"      "AlgorithmTriageAction" NOT NULL DEFAULT 'NONE',
  "triggerReasonsJson"     TEXT NOT NULL DEFAULT '[]',
  "recommendedMultiplier"  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  "narrative"              TEXT NOT NULL DEFAULT '',
  "status"                 "AlgorithmTriageStatus" NOT NULL DEFAULT 'PENDING',
  "resolvedBy"             TEXT,
  "resolvedAt"             TIMESTAMP(3),
  "resolutionNote"         TEXT,
  CONSTRAINT "AlgorithmTriageRecommendation_algorithmId_fkey"
    FOREIGN KEY ("algorithmId") REFERENCES "LogicalAlgorithm"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "AlgorithmTriageRecommendation_org_status_idx"
  ON "AlgorithmTriageRecommendation" ("organizationId", "status");
CREATE INDEX "AlgorithmTriageRecommendation_algorithm_at_idx"
  ON "AlgorithmTriageRecommendation" ("algorithmId", "recommendedAt" DESC);
