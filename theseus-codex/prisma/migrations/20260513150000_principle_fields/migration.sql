-- Prompt 56 (2026-05-13): principle-shape contract on Conclusion.
--
-- The new extractor (noosphere.claim_extractor.PrincipleExtractor)
-- emits decision rules with structured shape fields. Legacy rows
-- pre-date the contract; they remain in the table with NULL principle
-- fields and are surfaced in the founder-confirmable re-extraction
-- queue (/extractor/re-extract) instead of being auto-rewritten.
--
-- Mirror: noosphere/alembic/versions/008_principle_fields.py

ALTER TABLE "Conclusion"
  ADD COLUMN IF NOT EXISTS "principleKind"          TEXT,
  ADD COLUMN IF NOT EXISTS "domainOfApplicability"  TEXT,
  ADD COLUMN IF NOT EXISTS "quantifiableProxies"    TEXT NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS "decisionExamples"       TEXT NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS "sourceSpan"             TEXT;

-- Optional partial index for the re-extraction queue: only rows that
-- still need re-shaping. Cheap because legacy conclusions are a
-- shrinking set as re-extraction lands.
CREATE INDEX IF NOT EXISTS "Conclusion_principleKind_null_idx"
  ON "Conclusion" ("organizationId")
  WHERE "principleKind" IS NULL;
