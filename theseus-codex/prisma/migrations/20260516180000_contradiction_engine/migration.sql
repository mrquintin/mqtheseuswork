-- Prompt 06 of Round 19 (2026-05-16): Canonical contradiction engine.
--
-- Replaces the six-heuristic vote with one geometric detector
-- (Householder reflection + Hoyer sparsity of difference). The new
-- engine writes additional columns on Contradiction so analyses can
-- group by detection method version, and a ContradictionDispute table
-- records founder disputes for calibration review.
--
-- Additive only — existing heuristic rows remain with score/axis/etc.
-- null until the deletion pass (prompt 16) removes the legacy path.
--
-- Mirror: noosphere/alembic/versions/015_contradiction_engine.py

ALTER TABLE "Contradiction"
  ADD COLUMN "score"             DOUBLE PRECISION,
  ADD COLUMN "confidenceLow"     DOUBLE PRECISION,
  ADD COLUMN "confidenceHigh"    DOUBLE PRECISION,
  ADD COLUMN "axis"              TEXT,
  ADD COLUMN "humanExplanation"  TEXT,
  ADD COLUMN "detectionMethod"   TEXT NOT NULL DEFAULT '',
  ADD COLUMN "disputeCount"      INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "lastDisputeAt"     TIMESTAMP(3);

CREATE INDEX "Contradiction_detectionMethod_idx"
  ON "Contradiction" ("detectionMethod");

CREATE TABLE "ContradictionDispute" (
  "id"               TEXT PRIMARY KEY,
  "contradictionId"  TEXT NOT NULL,
  "organizationId"   TEXT NOT NULL,
  "detectionMethod"  TEXT NOT NULL DEFAULT '',
  "disputedById"     TEXT,
  "reason"           TEXT NOT NULL DEFAULT '',
  "createdAt"        TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ContradictionDispute_contradictionId_fkey"
    FOREIGN KEY ("contradictionId") REFERENCES "Contradiction"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "ContradictionDispute_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "ContradictionDispute_disputedById_fkey"
    FOREIGN KEY ("disputedById") REFERENCES "Founder"("id")
    ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX "ContradictionDispute_contradictionId_idx"
  ON "ContradictionDispute" ("contradictionId");

CREATE INDEX "ContradictionDispute_org_createdAt_idx"
  ON "ContradictionDispute" ("organizationId", "createdAt" DESC);

CREATE INDEX "ContradictionDispute_method_createdAt_idx"
  ON "ContradictionDispute" ("detectionMethod", "createdAt" DESC);
