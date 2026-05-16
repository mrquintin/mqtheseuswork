-- Round 19 prompt 12: PortfolioAgent + MemoDispatch.
--
-- Adds the two new entity tables, four supporting enums, and the
-- additive sourceMemoId column on ForecastBet / EquityPosition.
-- Mirrors the noosphere-side alembic revision
-- 021_portfolio_agent. Additive only — no existing rows are touched.

-- 1. Enums.

CREATE TYPE "PortfolioAgentKind" AS ENUM (
    'HUMAN',
    'AUTO_PAPER',
    'AUTO_LIVE'
);

CREATE TYPE "PortfolioAgentStatus" AS ENUM (
    'ACTIVE',
    'PAUSED',
    'RETIRED'
);

CREATE TYPE "MemoDispatchOutcome" AS ENUM (
    'PENDING',
    'ACCEPTED_AND_BET',
    'ACCEPTED_NO_BET',
    'REJECTED',
    'DEFERRED',
    'AUTO_PAPERED',
    'AUTO_LIVE_QUEUED',
    'DISPATCH_FAILED'
);

CREATE TYPE "MemoDispatchBetKind" AS ENUM (
    'FORECAST_BET',
    'EQUITY_POSITION'
);

-- 2. PortfolioAgent table.

CREATE TABLE "PortfolioAgent" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL DEFAULT '',
    "kind" "PortfolioAgentKind" NOT NULL DEFAULT 'HUMAN',
    "status" "PortfolioAgentStatus" NOT NULL DEFAULT 'ACTIVE',
    "defaultBetCeilingUsd" DOUBLE PRECISION NOT NULL DEFAULT 50.0,
    "subscriptionsJson" TEXT NOT NULL DEFAULT '[]',
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "PortfolioAgent_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "PortfolioAgent_organizationId_status_idx"
    ON "PortfolioAgent"("organizationId", "status");

CREATE INDEX "PortfolioAgent_organizationId_kind_idx"
    ON "PortfolioAgent"("organizationId", "kind");

ALTER TABLE "PortfolioAgent"
    ADD CONSTRAINT "PortfolioAgent_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- 3. MemoDispatch table.

CREATE TABLE "MemoDispatch" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "memoId" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "dispatchedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "outcomeAction" "MemoDispatchOutcome" NOT NULL DEFAULT 'PENDING',
    "betLink" TEXT,
    "betLinkKind" "MemoDispatchBetKind",
    "acknowledgedBy" TEXT NOT NULL DEFAULT '',
    "acknowledgedAt" TIMESTAMP(3),
    "rationale" TEXT NOT NULL DEFAULT '',
    "deferredUntil" TIMESTAMP(3),
    "failureReason" TEXT NOT NULL DEFAULT '',
    "eightGateStatusJson" TEXT NOT NULL DEFAULT '{}',
    "payloadJson" TEXT NOT NULL DEFAULT '{}',

    CONSTRAINT "MemoDispatch_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "MemoDispatch_agentId_outcomeAction_idx"
    ON "MemoDispatch"("agentId", "outcomeAction");

CREATE INDEX "MemoDispatch_organizationId_dispatchedAt_idx"
    ON "MemoDispatch"("organizationId", "dispatchedAt" DESC);

CREATE INDEX "MemoDispatch_memoId_idx"
    ON "MemoDispatch"("memoId");

ALTER TABLE "MemoDispatch"
    ADD CONSTRAINT "MemoDispatch_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "MemoDispatch"
    ADD CONSTRAINT "MemoDispatch_agentId_fkey"
    FOREIGN KEY ("agentId")
    REFERENCES "PortfolioAgent"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;

-- 4. sourceMemoId on ForecastBet + EquityPosition. Additive only —
-- nullable so pre-prompt-12 bets remain valid.

ALTER TABLE "ForecastBet"
    ADD COLUMN "sourceMemoId" TEXT;

CREATE INDEX "ForecastBet_sourceMemoId_idx"
    ON "ForecastBet"("sourceMemoId");

ALTER TABLE "EquityPosition"
    ADD COLUMN "sourceMemoId" TEXT;

CREATE INDEX "EquityPosition_sourceMemoId_idx"
    ON "EquityPosition"("sourceMemoId");
