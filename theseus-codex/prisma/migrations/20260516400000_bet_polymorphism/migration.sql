-- Round 19 prompt 15: polymorphic bet abstraction.
--
-- Adds two tables (bet_spec, bet_resolution), three enums (BetKind,
-- BetStatus, BetOutcome), and two nullable betSpecId columns on
-- ForecastBet and EquityPosition. Additive only — pre-prompt-15 rows
-- carry NULL and continue to work.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'BetKind') THEN
        CREATE TYPE "BetKind" AS ENUM ('MARKET_BET', 'ADVISORY_BET', 'STRATEGIC_BET', 'SCIENTIFIC_BET');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'BetStatus') THEN
        CREATE TYPE "BetStatus" AS ENUM ('PROPOSED', 'AUTHORIZED', 'OPEN', 'RESOLVED', 'CANCELLED', 'EXPIRED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'BetOutcome') THEN
        CREATE TYPE "BetOutcome" AS ENUM ('CORRECT', 'INCORRECT', 'PARTIALLY_CORRECT', 'UNDETERMINED');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS "bet_spec" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL DEFAULT '',
    "kind" "BetKind" NOT NULL DEFAULT 'MARKET_BET',
    "status" "BetStatus" NOT NULL DEFAULT 'PROPOSED',
    "proposition" TEXT NOT NULL DEFAULT '',
    "resolutionCriterion" TEXT NOT NULL DEFAULT '',
    "horizonAt" TIMESTAMP(3) NOT NULL,
    "createdByMemoId" TEXT,
    "originatingAlgorithmId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "resolvedAt" TIMESTAMP(3),
    "outcome" "BetOutcome",
    "outcomeNote" TEXT,
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    CONSTRAINT "bet_spec_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "bet_spec_organizationId_kind_status_idx"
    ON "bet_spec" ("organizationId", "kind", "status");
CREATE INDEX IF NOT EXISTS "bet_spec_horizonAt_idx"
    ON "bet_spec" ("horizonAt");
CREATE INDEX IF NOT EXISTS "bet_spec_createdByMemoId_idx"
    ON "bet_spec" ("createdByMemoId");

CREATE TABLE IF NOT EXISTS "bet_resolution" (
    "id" TEXT NOT NULL,
    "betSpecId" TEXT NOT NULL,
    "resolvedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "outcome" "BetOutcome" NOT NULL DEFAULT 'UNDETERMINED',
    "evidenceNote" TEXT NOT NULL DEFAULT '',
    "resolvedBy" TEXT NOT NULL DEFAULT 'agent',
    "pnlUsd" DOUBLE PRECISION,
    "costRealized" DOUBLE PRECISION,
    "accuracyScore" DOUBLE PRECISION,
    "audienceResponse" TEXT,
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    CONSTRAINT "bet_resolution_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "bet_resolution_betSpecId_fkey"
        FOREIGN KEY ("betSpecId") REFERENCES "bet_spec"("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "bet_resolution_betSpecId_idx"
    ON "bet_resolution" ("betSpecId");
CREATE INDEX IF NOT EXISTS "bet_resolution_resolvedAt_idx"
    ON "bet_resolution" ("resolvedAt");

ALTER TABLE "ForecastBet"
    ADD COLUMN IF NOT EXISTS "betSpecId" TEXT;
CREATE INDEX IF NOT EXISTS "ForecastBet_betSpecId_idx"
    ON "ForecastBet" ("betSpecId");

ALTER TABLE "EquityPosition"
    ADD COLUMN IF NOT EXISTS "betSpecId" TEXT;
CREATE INDEX IF NOT EXISTS "EquityPosition_betSpecId_idx"
    ON "EquityPosition" ("betSpecId");
