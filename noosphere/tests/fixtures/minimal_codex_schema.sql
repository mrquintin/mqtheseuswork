-- Minimal Codex schema for SQLite-backed ingest tests.
--
-- Mirrors the subset of columns in theseus-codex/prisma/schema.prisma that
-- the ingest pipeline (noosphere/codex_bridge.py) actually reads or writes.
-- Quoted camelCase identifiers match Prisma's generated column names so the
-- pipeline SQL runs verbatim under both Postgres (prod) and SQLite (tests).
--
-- Kept deliberately lean: no multi-tenant RLS, no soft-delete fields that
-- the ingest path does not touch, no triggers beyond the status-transition
-- log used by tests. If the prod schema adds a column that ingest reads,
-- mirror it here too — otherwise the Postgres pipeline will succeed while
-- the SQLite test suite silently passes with stale fields.

CREATE TABLE "Organization" (
  "id" TEXT PRIMARY KEY,
  "slug" TEXT UNIQUE NOT NULL,
  "name" TEXT NOT NULL
);

CREATE TABLE "Upload" (
  "id" TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "founderId" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "description" TEXT,
  "sourceType" TEXT NOT NULL DEFAULT 'written',
  "originalName" TEXT NOT NULL DEFAULT '',
  "mimeType" TEXT NOT NULL DEFAULT '',
  "filePath" TEXT,
  "fileSize" INTEGER NOT NULL DEFAULT 0,
  "textContent" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "processLog" TEXT NOT NULL DEFAULT '',
  "claimsCount" INTEGER,
  "errorMessage" TEXT,
  "extractionMethod" TEXT,
  "createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE "Conclusion" (
  "id" TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "noosphereId" TEXT UNIQUE,
  "text" TEXT NOT NULL,
  "normalizedText" TEXT,
  "confidenceTier" TEXT NOT NULL,
  "rationale" TEXT NOT NULL DEFAULT '',
  "supportingPrincipleIds" TEXT NOT NULL DEFAULT '[]',
  "evidenceChainClaimIds" TEXT NOT NULL DEFAULT '[]',
  "dissentClaimIds" TEXT NOT NULL DEFAULT '[]',
  "confidence" REAL NOT NULL DEFAULT 0,
  "topicHint" TEXT NOT NULL DEFAULT '',
  "createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX "Conclusion_org_norm_idx"
  ON "Conclusion" ("organizationId", "normalizedText");

CREATE TABLE "ConclusionSource" (
  "conclusionId" TEXT NOT NULL,
  "uploadId" TEXT NOT NULL,
  "createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("conclusionId", "uploadId")
);

CREATE TABLE "Contradiction" (
  "id" TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "claimAId" TEXT NOT NULL,
  "claimBId" TEXT NOT NULL,
  "severity" REAL NOT NULL,
  "sixLayerJson" TEXT,
  "narrative" TEXT NOT NULL DEFAULT '',
  "sourceUploadId" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE "OpenQuestion" (
  "id" TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "noosphereId" TEXT UNIQUE,
  "summary" TEXT NOT NULL,
  "claimAId" TEXT NOT NULL,
  "claimBId" TEXT NOT NULL,
  "unresolvedReason" TEXT NOT NULL DEFAULT '',
  "layerDisagreementSummary" TEXT NOT NULL DEFAULT '',
  "sourceUploadId" TEXT,
  "createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE "ResearchSuggestion" (
  "id" TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "noosphereId" TEXT UNIQUE,
  "title" TEXT NOT NULL,
  "summary" TEXT NOT NULL DEFAULT '',
  "rationale" TEXT NOT NULL DEFAULT '',
  "readingUris" TEXT NOT NULL DEFAULT '[]',
  "sessionLabel" TEXT NOT NULL DEFAULT '',
  "suggestedForFounderId" TEXT,
  "sourceUploadId" TEXT,
  "createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE "AuditEvent" (
  "id" TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "founderId" TEXT NOT NULL,
  "uploadId" TEXT,
  "action" TEXT NOT NULL,
  "detail" TEXT,
  "createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Status-transition log. Populated by the trigger below so the ingest tests
-- can assert the ordered sequence (pending → extracting → awaiting_ingest →
-- processing → ingested) without instrumenting the pipeline itself.
CREATE TABLE "UploadStatusHistory" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "upload_id" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "ts" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER "upload_status_log"
AFTER UPDATE OF "status" ON "Upload"
FOR EACH ROW
BEGIN
  INSERT INTO "UploadStatusHistory" ("upload_id", "status")
  VALUES (NEW."id", NEW."status");
END;
