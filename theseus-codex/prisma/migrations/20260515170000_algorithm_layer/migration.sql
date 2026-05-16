-- Prompt 01 of Round 19 (2026-05-15): Logical Algorithm layer.
--
-- An algorithm is a logical function — named inputs, named output,
-- with a structured reasoning body that invokes one or more
-- principles to derive the output. The algorithm layer sits above
-- principles the way principles sit above conclusions.
--
-- Three tables: LogicalAlgorithm, AlgorithmInvocation,
-- AlgorithmInputObservation. The full Pydantic payload round-trips
-- through ``payloadJson`` per row so the schema can evolve without
-- per-field migrations; duplicated columns power the indexed reads
-- the founder triage queue and runtime depend on.
--
-- Mirror: noosphere/alembic/versions/013_algorithm_layer.py

CREATE TYPE "AlgorithmStatus" AS ENUM (
  'DRAFT',
  'UNDER_REVIEW',
  'ACTIVE',
  'PAUSED',
  'RETIRED'
);

CREATE TYPE "AlgorithmCorrectness" AS ENUM (
  'CORRECT',
  'INCORRECT',
  'PARTIALLY_CORRECT',
  'INDETERMINATE'
);

CREATE TABLE "LogicalAlgorithm" (
  "id"                     TEXT PRIMARY KEY,
  "organizationId"         TEXT NOT NULL,
  "name"                   TEXT NOT NULL,
  "description"            TEXT NOT NULL DEFAULT '',
  "sourcePrincipleIdsJson" TEXT NOT NULL DEFAULT '[]',
  "inputsJson"             TEXT NOT NULL DEFAULT '[]',
  "outputJson"             TEXT NOT NULL DEFAULT '{}',
  "reasoningChainJson"     TEXT NOT NULL DEFAULT '[]',
  "triggerPredicate"       TEXT NOT NULL DEFAULT '',
  "status"                 "AlgorithmStatus" NOT NULL DEFAULT 'DRAFT',
  "retiredReason"          TEXT,
  "payloadJson"            TEXT NOT NULL DEFAULT '{}',
  "createdAt"              TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"              TIMESTAMP(3) NOT NULL,
  "lastInvokedAt"          TIMESTAMP(3),
  CONSTRAINT "LogicalAlgorithm_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "LogicalAlgorithm_organizationId_name_key"
  ON "LogicalAlgorithm" ("organizationId", "name");
CREATE INDEX "LogicalAlgorithm_organizationId_idx"
  ON "LogicalAlgorithm" ("organizationId");
CREATE INDEX "LogicalAlgorithm_organizationId_status_idx"
  ON "LogicalAlgorithm" ("organizationId", "status");

CREATE TABLE "AlgorithmInvocation" (
  "id"                  TEXT PRIMARY KEY,
  "organizationId"      TEXT NOT NULL,
  "algorithmId"         TEXT NOT NULL,
  "invokedAt"           TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "triggerInputsJson"   TEXT NOT NULL DEFAULT '{}',
  "derivedOutputJson"   TEXT NOT NULL DEFAULT '{}',
  "reasoningTraceJson"  TEXT NOT NULL DEFAULT '[]',
  "confidenceLow"       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  "confidenceHigh"      DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  "predictedHorizon"    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  "betImpliedJson"      TEXT,
  "resolvedAt"          TIMESTAMP(3),
  "actualOutcomeJson"   TEXT,
  "correctness"         "AlgorithmCorrectness",
  "brierEquivalent"     DOUBLE PRECISION,
  "payloadJson"         TEXT NOT NULL DEFAULT '{}',
  CONSTRAINT "AlgorithmInvocation_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "AlgorithmInvocation_algorithmId_fkey"
    FOREIGN KEY ("algorithmId") REFERENCES "LogicalAlgorithm"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "AlgorithmInvocation_algorithmId_invokedAt_idx"
  ON "AlgorithmInvocation" ("algorithmId", "invokedAt" DESC);
CREATE INDEX "AlgorithmInvocation_organizationId_invokedAt_idx"
  ON "AlgorithmInvocation" ("organizationId", "invokedAt" DESC);

CREATE TABLE "AlgorithmInputObservation" (
  "id"               TEXT PRIMARY KEY,
  "invocationId"     TEXT NOT NULL,
  "inputName"        TEXT NOT NULL,
  "valueJson"        TEXT NOT NULL DEFAULT '',
  "observedAt"       TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "sourceArtifactId" TEXT,
  "sourceUrl"        TEXT,
  CONSTRAINT "AlgorithmInputObservation_invocationId_fkey"
    FOREIGN KEY ("invocationId") REFERENCES "AlgorithmInvocation"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "AlgorithmInputObservation_invocationId_idx"
  ON "AlgorithmInputObservation" ("invocationId");
CREATE INDEX "AlgorithmInputObservation_inputName_idx"
  ON "AlgorithmInputObservation" ("inputName");
CREATE INDEX "AlgorithmInputObservation_sourceArtifactId_idx"
  ON "AlgorithmInputObservation" ("sourceArtifactId");
