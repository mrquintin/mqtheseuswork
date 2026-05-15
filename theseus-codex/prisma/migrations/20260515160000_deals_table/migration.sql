-- Prompt 69 (2026-05-15): VC firm preset — deals + principle-alignment.
--
-- A Deal models an investment opportunity. DealPrincipleAlignment is
-- the denormalised, idempotent verdict table written by the
-- noosphere alignment runner (one row per (deal, principle), upsert
-- on the unique pair). DealNote is the append-only partner-meeting
-- log.
--
-- Mirror: noosphere/alembic/versions/012_deals_table.py

CREATE TYPE "DealDecisionStatus" AS ENUM (
  'EXPLORING',
  'NEXT_MEETING',
  'COMMITTED',
  'PASSED',
  'EXITED'
);

CREATE TYPE "PrincipleAlignmentVerdict" AS ENUM (
  'MATCH',
  'CONFLICT',
  'UNCLEAR'
);

CREATE TABLE "Deal" (
  "id"                    TEXT PRIMARY KEY,
  "organizationId"        TEXT NOT NULL,
  "name"                  TEXT NOT NULL,
  "description"           TEXT NOT NULL DEFAULT '',
  "stage"                 TEXT NOT NULL DEFAULT '',
  "sector"                TEXT NOT NULL DEFAULT '',
  "geo"                   TEXT NOT NULL DEFAULT '',
  "decisionStatus"        "DealDecisionStatus" NOT NULL DEFAULT 'EXPLORING',
  "sourceDocumentsJson"   TEXT NOT NULL DEFAULT '[]',
  "memoDraft"             TEXT NOT NULL DEFAULT '',
  "memoFinal"             TEXT NOT NULL DEFAULT '',
  "memoSignedAt"          TIMESTAMP(3),
  "memoSignedByFounderId" TEXT,
  "createdAt"             TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"             TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Deal_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE INDEX "Deal_organizationId_idx" ON "Deal" ("organizationId");
CREATE INDEX "Deal_organizationId_decisionStatus_idx"
  ON "Deal" ("organizationId", "decisionStatus");
CREATE INDEX "Deal_organizationId_sector_idx"
  ON "Deal" ("organizationId", "sector");

CREATE TABLE "DealPrincipleAlignment" (
  "id"             TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "dealId"         TEXT NOT NULL,
  "principleId"    TEXT NOT NULL,
  "verdict"        "PrincipleAlignmentVerdict" NOT NULL,
  "rationale"      TEXT NOT NULL DEFAULT '',
  "citationsJson"  TEXT NOT NULL DEFAULT '[]',
  "confidence"     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  "runId"          TEXT NOT NULL,
  "createdAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"      TIMESTAMP(3) NOT NULL,
  CONSTRAINT "DealPrincipleAlignment_dealId_fkey"
    FOREIGN KEY ("dealId") REFERENCES "Deal"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "DealPrincipleAlignment_dealId_principleId_key"
  ON "DealPrincipleAlignment" ("dealId", "principleId");
CREATE INDEX "DealPrincipleAlignment_organizationId_dealId_idx"
  ON "DealPrincipleAlignment" ("organizationId", "dealId");
CREATE INDEX "DealPrincipleAlignment_organizationId_principleId_idx"
  ON "DealPrincipleAlignment" ("organizationId", "principleId");

CREATE TABLE "DealNote" (
  "id"                     TEXT PRIMARY KEY,
  "organizationId"         TEXT NOT NULL,
  "dealId"                 TEXT NOT NULL,
  "authorFounderId"        TEXT NOT NULL,
  "body"                   TEXT NOT NULL DEFAULT '',
  "citedPrincipleIdsJson"  TEXT NOT NULL DEFAULT '[]',
  "supersedesId"           TEXT,
  "createdAt"              TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "DealNote_dealId_fkey"
    FOREIGN KEY ("dealId") REFERENCES "Deal"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "DealNote_org_deal_createdAt_idx"
  ON "DealNote" ("organizationId", "dealId", "createdAt");
