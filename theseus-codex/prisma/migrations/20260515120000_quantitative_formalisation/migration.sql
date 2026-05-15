-- Prompt 63 (2026-05-15): quantitative formalisation spec layer.
--
-- One row per QuantitativeFormalisation. The full Pydantic payload is
-- held as JSON in `payloadJson`; `principleId` and `status` are
-- duplicated into indexed columns because the founder triage queue
-- and the public-surface read both filter on them.
--
-- Mirror: noosphere/alembic/versions/009_quantitative_formalisation.py

CREATE TABLE IF NOT EXISTS "QuantitativeFormalisation" (
  "id"                    TEXT PRIMARY KEY,
  "organizationId"        TEXT NOT NULL,
  "principleId"           TEXT NOT NULL,
  "status"                TEXT NOT NULL DEFAULT 'DRAFT',
  "nullHypothesis"        TEXT NOT NULL DEFAULT '',
  "metricsJson"           TEXT NOT NULL DEFAULT '[]',
  "testsJson"             TEXT NOT NULL DEFAULT '[]',
  "dataSourcesJson"       TEXT NOT NULL DEFAULT '[]',
  "decisionThresholdsJson" TEXT NOT NULL DEFAULT '[]',
  "unformalisableReason"  TEXT,
  "drafterModel"          TEXT NOT NULL DEFAULT '',
  "drafterNotes"          TEXT NOT NULL DEFAULT '',
  "payloadJson"           TEXT NOT NULL DEFAULT '{}',
  "reviewedByFounderId"   TEXT,
  "reviewedAt"            TIMESTAMP(3),
  "createdAt"             TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"             TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS "QuantitativeFormalisation_principleId_idx"
  ON "QuantitativeFormalisation" ("principleId");

CREATE INDEX IF NOT EXISTS "QuantitativeFormalisation_organizationId_status_idx"
  ON "QuantitativeFormalisation" ("organizationId", "status");

ALTER TABLE "QuantitativeFormalisation"
  ADD CONSTRAINT "QuantitativeFormalisation_organization_fk"
  FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
  ON DELETE RESTRICT;

ALTER TABLE "QuantitativeFormalisation"
  ADD CONSTRAINT "QuantitativeFormalisation_principle_fk"
  FOREIGN KEY ("principleId") REFERENCES "Principle"("id")
  ON DELETE CASCADE;
