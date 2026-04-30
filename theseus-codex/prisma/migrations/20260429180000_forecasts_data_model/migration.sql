-- CreateEnum
CREATE TYPE "ForecastSource" AS ENUM ('POLYMARKET', 'KALSHI');

-- CreateEnum
CREATE TYPE "ForecastMarketStatus" AS ENUM ('OPEN', 'CLOSED', 'RESOLVED', 'CANCELLED');

-- CreateEnum
CREATE TYPE "ForecastPredictionStatus" AS ENUM ('PUBLISHED', 'ABSTAINED_INSUFFICIENT_SOURCES', 'ABSTAINED_MARKET_EXPIRED', 'ABSTAINED_NEAR_DUPLICATE', 'ABSTAINED_BUDGET', 'ABSTAINED_CITATION_FABRICATION', 'ABSTAINED_REVOKED_SOURCES');

-- CreateEnum
CREATE TYPE "ForecastSupportLabel" AS ENUM ('DIRECT', 'INDIRECT', 'CONTRARY');

-- CreateEnum
CREATE TYPE "ForecastOutcome" AS ENUM ('YES', 'NO', 'CANCELLED', 'AMBIGUOUS');

-- CreateEnum
CREATE TYPE "ForecastBetMode" AS ENUM ('PAPER', 'LIVE');

-- CreateEnum
CREATE TYPE "ForecastExchange" AS ENUM ('POLYMARKET', 'KALSHI');

-- CreateEnum
CREATE TYPE "ForecastBetSide" AS ENUM ('YES', 'NO');

-- CreateEnum
CREATE TYPE "ForecastBetStatus" AS ENUM ('PENDING', 'AUTHORIZED', 'CONFIRMED', 'SUBMITTED', 'FILLED', 'CANCELLED', 'SETTLED', 'FAILED');

-- CreateEnum
CREATE TYPE "ForecastFollowUpRole" AS ENUM ('USER', 'ASSISTANT');

-- CreateTable
CREATE TABLE "ForecastMarket" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "source" "ForecastSource" NOT NULL,
    "externalId" TEXT NOT NULL,
    "title" VARCHAR(280) NOT NULL,
    "description" TEXT,
    "resolutionCriteria" TEXT,
    "category" TEXT,
    "currentYesPrice" DECIMAL(8,6),
    "currentNoPrice" DECIMAL(8,6),
    "volume" DECIMAL(18,4),
    "openTime" TIMESTAMP(3),
    "closeTime" TIMESTAMP(3),
    "resolvedAt" TIMESTAMP(3),
    "resolvedOutcome" "ForecastOutcome",
    "rawPayload" JSONB NOT NULL,
    "status" "ForecastMarketStatus" NOT NULL DEFAULT 'OPEN',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ForecastMarket_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ForecastPrediction" (
    "id" TEXT NOT NULL,
    "marketId" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "probabilityYes" DECIMAL(8,6),
    "confidenceLow" DECIMAL(8,6),
    "confidenceHigh" DECIMAL(8,6),
    "headline" VARCHAR(140) NOT NULL,
    "reasoning" TEXT NOT NULL,
    "status" "ForecastPredictionStatus" NOT NULL,
    "abstentionReason" TEXT,
    "topicHint" TEXT,
    "modelName" TEXT NOT NULL,
    "promptTokens" INTEGER NOT NULL DEFAULT 0,
    "completionTokens" INTEGER NOT NULL DEFAULT 0,
    "liveAuthorizedAt" TIMESTAMP(3),
    "liveAuthorizedBy" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ForecastPrediction_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ForecastCitation" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "sourceType" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "quotedSpan" TEXT NOT NULL,
    "supportLabel" "ForecastSupportLabel" NOT NULL,
    "retrievalScore" DOUBLE PRECISION,
    "isRevoked" BOOLEAN NOT NULL DEFAULT false,
    "revokedReason" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ForecastCitation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ForecastResolution" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "marketOutcome" "ForecastOutcome" NOT NULL,
    "brierScore" DOUBLE PRECISION,
    "logLoss" DOUBLE PRECISION,
    "calibrationBucket" DECIMAL(3,1),
    "resolvedAt" TIMESTAMP(3) NOT NULL,
    "justification" TEXT NOT NULL,
    "rawSettlement" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ForecastResolution_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ForecastBet" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "mode" "ForecastBetMode" NOT NULL DEFAULT 'PAPER',
    "exchange" "ForecastExchange" NOT NULL,
    "side" "ForecastBetSide" NOT NULL,
    "stakeUsd" DECIMAL(12,2) NOT NULL,
    "entryPrice" DECIMAL(8,6) NOT NULL,
    "exitPrice" DECIMAL(8,6),
    "status" "ForecastBetStatus" NOT NULL,
    "externalOrderId" TEXT,
    "clientOrderId" TEXT,
    "settlementPnlUsd" DECIMAL(12,2),
    "liveAuthorizedAt" TIMESTAMP(3),
    "confirmedAt" TIMESTAMP(3),
    "submittedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "settledAt" TIMESTAMP(3),

    CONSTRAINT "ForecastBet_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ForecastBet_live_requires_authorizedAt_check" CHECK ("mode" != 'LIVE' OR "liveAuthorizedAt" IS NOT NULL)
);

-- CreateTable
CREATE TABLE "ForecastPortfolioState" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "paperBalanceUsd" DECIMAL(12,2) NOT NULL,
    "liveBalanceUsd" DECIMAL(12,2),
    "dailyLossUsd" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "dailyLossResetAt" TIMESTAMP(3) NOT NULL,
    "killSwitchEngaged" BOOLEAN NOT NULL DEFAULT false,
    "killSwitchReason" TEXT,
    "totalResolved" INTEGER NOT NULL DEFAULT 0,
    "meanBrier90d" DOUBLE PRECISION,
    "meanLogLoss90d" DOUBLE PRECISION,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ForecastPortfolioState_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ForecastFollowUpSession" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "clientFingerprint" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lastActivityAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ForecastFollowUpSession_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ForecastFollowUpMessage" (
    "id" TEXT NOT NULL,
    "sessionId" TEXT NOT NULL,
    "role" "ForecastFollowUpRole" NOT NULL,
    "content" TEXT NOT NULL,
    "citations" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ForecastFollowUpMessage_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ForecastMarket_organizationId_status_closeTime_idx" ON "ForecastMarket"("organizationId", "status", "closeTime");

-- CreateIndex
CREATE INDEX "ForecastMarket_source_category_idx" ON "ForecastMarket"("source", "category");

-- CreateIndex
CREATE INDEX "ForecastMarket_updatedAt_idx" ON "ForecastMarket"("updatedAt");

-- CreateIndex
CREATE UNIQUE INDEX "ForecastMarket_source_externalId_key" ON "ForecastMarket"("source", "externalId");

-- CreateIndex
CREATE INDEX "ForecastPrediction_organizationId_status_createdAt_idx" ON "ForecastPrediction"("organizationId", "status", "createdAt");

-- CreateIndex
CREATE INDEX "ForecastPrediction_marketId_createdAt_idx" ON "ForecastPrediction"("marketId", "createdAt");

-- CreateIndex
CREATE INDEX "ForecastPrediction_liveAuthorizedAt_idx" ON "ForecastPrediction"("liveAuthorizedAt");

-- CreateIndex
CREATE INDEX "ForecastCitation_predictionId_idx" ON "ForecastCitation"("predictionId");

-- CreateIndex
CREATE INDEX "ForecastCitation_sourceType_sourceId_idx" ON "ForecastCitation"("sourceType", "sourceId");

-- CreateIndex
CREATE UNIQUE INDEX "ForecastResolution_predictionId_key" ON "ForecastResolution"("predictionId");

-- CreateIndex
CREATE INDEX "ForecastResolution_resolvedAt_idx" ON "ForecastResolution"("resolvedAt");

-- CreateIndex
CREATE INDEX "ForecastResolution_calibrationBucket_idx" ON "ForecastResolution"("calibrationBucket");

-- CreateIndex
CREATE INDEX "ForecastBet_organizationId_mode_createdAt_idx" ON "ForecastBet"("organizationId", "mode", "createdAt");

-- CreateIndex
CREATE INDEX "ForecastBet_predictionId_status_idx" ON "ForecastBet"("predictionId", "status");

-- CreateIndex
CREATE INDEX "ForecastBet_externalOrderId_idx" ON "ForecastBet"("externalOrderId");

-- CreateIndex
CREATE INDEX "ForecastBet_clientOrderId_idx" ON "ForecastBet"("clientOrderId");

-- CreateIndex
CREATE UNIQUE INDEX "ForecastPortfolioState_organizationId_key" ON "ForecastPortfolioState"("organizationId");

-- CreateIndex
CREATE INDEX "ForecastFollowUpSession_predictionId_lastActivityAt_idx" ON "ForecastFollowUpSession"("predictionId", "lastActivityAt");

-- CreateIndex
CREATE INDEX "ForecastFollowUpSession_clientFingerprint_createdAt_idx" ON "ForecastFollowUpSession"("clientFingerprint", "createdAt");

-- CreateIndex
CREATE INDEX "ForecastFollowUpMessage_sessionId_createdAt_idx" ON "ForecastFollowUpMessage"("sessionId", "createdAt");

-- AddForeignKey
ALTER TABLE "ForecastMarket" ADD CONSTRAINT "ForecastMarket_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastPrediction" ADD CONSTRAINT "ForecastPrediction_marketId_fkey" FOREIGN KEY ("marketId") REFERENCES "ForecastMarket"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastPrediction" ADD CONSTRAINT "ForecastPrediction_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastCitation" ADD CONSTRAINT "ForecastCitation_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "ForecastPrediction"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastResolution" ADD CONSTRAINT "ForecastResolution_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "ForecastPrediction"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastBet" ADD CONSTRAINT "ForecastBet_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "ForecastPrediction"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastBet" ADD CONSTRAINT "ForecastBet_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastPortfolioState" ADD CONSTRAINT "ForecastPortfolioState_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastFollowUpSession" ADD CONSTRAINT "ForecastFollowUpSession_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "ForecastPrediction"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ForecastFollowUpMessage" ADD CONSTRAINT "ForecastFollowUpMessage_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES "ForecastFollowUpSession"("id") ON DELETE CASCADE ON UPDATE CASCADE;
