-- Prompt 63 runner (2026-05-15): quantitative test-result rows.
--
-- One row per QuantitativeRunner pass. The full Pydantic payload is
-- held in `payloadJson`; `formalisationId`, `principleId`, `runStamp`
-- and `status` are duplicated into indexed columns because the public
-- surface and the founder triage queue both read on them.
--
-- Mirror: noosphere/alembic/versions/011_quantitative_test_results.py

CREATE TABLE IF NOT EXISTS "QuantitativeTestResult" (
  "id"                TEXT PRIMARY KEY,
  "organizationId"    TEXT NOT NULL,
  "formalisationId"   TEXT NOT NULL,
  "principleId"       TEXT NOT NULL DEFAULT '',
  "runStamp"          TEXT NOT NULL,
  "status"            TEXT NOT NULL DEFAULT 'RAN',
  "metricValuesJson"  TEXT NOT NULL DEFAULT '{}',
  "testOutputsJson"   TEXT NOT NULL DEFAULT '[]',
  "decisionSummary"   TEXT NOT NULL DEFAULT '',
  "artifactsPath"     TEXT NOT NULL DEFAULT '',
  "thresholdCrossingsJson" TEXT NOT NULL DEFAULT '[]',
  "error"             TEXT,
  "payloadJson"       TEXT NOT NULL DEFAULT '{}',
  "createdAt"         TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS "QuantitativeTestResult_formalisationId_idx"
  ON "QuantitativeTestResult" ("formalisationId");

CREATE INDEX IF NOT EXISTS "QuantitativeTestResult_principleId_idx"
  ON "QuantitativeTestResult" ("principleId");

CREATE UNIQUE INDEX IF NOT EXISTS "QuantitativeTestResult_formalisation_run_uq"
  ON "QuantitativeTestResult" ("formalisationId", "runStamp");

ALTER TABLE "QuantitativeTestResult"
  ADD CONSTRAINT "QuantitativeTestResult_organization_fk"
  FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
  ON DELETE RESTRICT;

ALTER TABLE "QuantitativeTestResult"
  ADD CONSTRAINT "QuantitativeTestResult_formalisation_fk"
  FOREIGN KEY ("formalisationId") REFERENCES "QuantitativeFormalisation"("id")
  ON DELETE CASCADE;


-- Founder triage queue for threshold-crossing events. Same
-- founder-confirmable pattern as elsewhere — the runner recommends,
-- the founder accepts before any conviction-score change lands.
CREATE TABLE IF NOT EXISTS "PrincipleConvictionUpdateQueue" (
  "id"                TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  "organizationId"    TEXT,
  "principleId"       TEXT NOT NULL,
  "formalisationId"   TEXT NOT NULL,
  "runStamp"          TEXT NOT NULL,
  "crossingsJson"     TEXT NOT NULL DEFAULT '[]',
  "summary"           TEXT NOT NULL DEFAULT '',
  "status"            TEXT NOT NULL DEFAULT 'PENDING',
  "resolvedByFounderId" TEXT,
  "resolvedAt"        TIMESTAMP(3),
  "createdAt"         TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS "PrincipleConvictionUpdateQueue_principleId_idx"
  ON "PrincipleConvictionUpdateQueue" ("principleId");

CREATE INDEX IF NOT EXISTS "PrincipleConvictionUpdateQueue_status_idx"
  ON "PrincipleConvictionUpdateQueue" ("status");
