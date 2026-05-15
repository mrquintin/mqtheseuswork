-- CreateEnum
CREATE TYPE "EquityAssetClass" AS ENUM ('STOCK', 'ETF', 'ADR');

-- CreateEnum
CREATE TYPE "EquityPriceSource" AS ENUM ('ALPACA', 'ROBINHOOD', 'YFINANCE', 'MANUAL');

-- CreateEnum
CREATE TYPE "EquitySignalDirection" AS ENUM ('BULLISH', 'BEARISH', 'NEUTRAL', 'ABSTAINED');

-- CreateEnum
CREATE TYPE "EquitySignalStatus" AS ENUM ('PUBLISHED', 'ABSTAINED', 'REVOKED');

-- CreateEnum
CREATE TYPE "EquityPositionMode" AS ENUM ('PAPER', 'LIVE');

-- CreateEnum
CREATE TYPE "EquityPositionSide" AS ENUM ('LONG', 'SHORT', 'CASH_RESERVE');

-- CreateEnum
CREATE TYPE "EquityPositionStatus" AS ENUM ('PENDING', 'OPEN', 'CLOSED', 'CANCELLED', 'FAILED');

-- CreateTable
CREATE TABLE "EquityInstrument" (
    "id" TEXT NOT NULL,
    "symbol" VARCHAR(16) NOT NULL,
    "exchange" VARCHAR(16) NOT NULL,
    "assetClass" "EquityAssetClass" NOT NULL,
    "name" VARCHAR(280) NOT NULL,
    "cusip" VARCHAR(16),
    "figi" VARCHAR(16),
    "isTradable" BOOLEAN NOT NULL DEFAULT true,
    "lastPrice" DECIMAL(18,6),
    "lastPriceAt" TIMESTAMP(3),
    "currency" VARCHAR(8) NOT NULL DEFAULT 'USD',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EquityInstrument_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EquityPriceTick" (
    "id" TEXT NOT NULL,
    "instrumentId" TEXT NOT NULL,
    "ts" TIMESTAMP(3) NOT NULL,
    "open" DECIMAL(18,6) NOT NULL,
    "high" DECIMAL(18,6) NOT NULL,
    "low" DECIMAL(18,6) NOT NULL,
    "close" DECIMAL(18,6) NOT NULL,
    "volume" DECIMAL(20,4) NOT NULL,
    "source" "EquityPriceSource" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "EquityPriceTick_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EquitySignal" (
    "id" TEXT NOT NULL,
    "instrumentId" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "direction" "EquitySignalDirection" NOT NULL,
    "confidenceLow" DECIMAL(8,6) NOT NULL,
    "confidenceHigh" DECIMAL(8,6) NOT NULL,
    "targetPriceLow" DECIMAL(18,6),
    "targetPriceHigh" DECIMAL(18,6),
    "horizonDays" INTEGER NOT NULL,
    "headline" VARCHAR(140) NOT NULL,
    "reasoning" TEXT NOT NULL,
    "modelName" TEXT NOT NULL,
    "promptTokens" INTEGER NOT NULL DEFAULT 0,
    "completionTokens" INTEGER NOT NULL DEFAULT 0,
    "status" "EquitySignalStatus" NOT NULL,
    "abstentionReason" TEXT,
    "liveAuthorizedAt" TIMESTAMP(3),
    "liveAuthorizedBy" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EquitySignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EquitySignalCitation" (
    "id" TEXT NOT NULL,
    "signalId" TEXT NOT NULL,
    "sourceType" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "quotedSpan" TEXT NOT NULL,
    "supportLabel" "ForecastSupportLabel" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "EquitySignalCitation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EquityPosition" (
    "id" TEXT NOT NULL,
    "signalId" TEXT NOT NULL,
    "instrumentId" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "mode" "EquityPositionMode" NOT NULL DEFAULT 'PAPER',
    "side" "EquityPositionSide" NOT NULL,
    "qty" DECIMAL(20,6) NOT NULL,
    "entryPrice" DECIMAL(18,6) NOT NULL,
    "entryAt" TIMESTAMP(3) NOT NULL,
    "exitPrice" DECIMAL(18,6),
    "exitAt" TIMESTAMP(3),
    "status" "EquityPositionStatus" NOT NULL,
    "externalOrderId" TEXT,
    "realizedPnlUsd" DECIMAL(14,4),
    "unrealizedPnlUsd" DECIMAL(14,4),
    "liveAuthorizedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EquityPosition_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "EquityPosition_live_requires_authorizedAt_check" CHECK ("mode" != 'LIVE' OR "liveAuthorizedAt" IS NOT NULL)
);

-- CreateTable
CREATE TABLE "EquityPortfolioState" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "paperBalanceUsd" DECIMAL(14,2) NOT NULL,
    "liveBalanceUsd" DECIMAL(14,2),
    "dailyLossUsd" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "dailyLossWindowResetAt" TIMESTAMP(3) NOT NULL,
    "killSwitchEngaged" BOOLEAN NOT NULL DEFAULT false,
    "killSwitchReason" TEXT,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EquityPortfolioState_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "EquityInstrument_symbol_exchange_key" ON "EquityInstrument"("symbol", "exchange");

-- CreateIndex
CREATE INDEX "EquityInstrument_assetClass_idx" ON "EquityInstrument"("assetClass");

-- CreateIndex
CREATE INDEX "EquityInstrument_updatedAt_idx" ON "EquityInstrument"("updatedAt");

-- CreateIndex
CREATE INDEX "EquityPriceTick_instrumentId_ts_idx" ON "EquityPriceTick"("instrumentId", "ts" DESC);

-- CreateIndex
CREATE INDEX "EquityPriceTick_source_idx" ON "EquityPriceTick"("source");

-- CreateIndex
CREATE INDEX "EquitySignal_organizationId_status_createdAt_idx" ON "EquitySignal"("organizationId", "status", "createdAt");

-- CreateIndex
CREATE INDEX "EquitySignal_instrumentId_createdAt_idx" ON "EquitySignal"("instrumentId", "createdAt");

-- CreateIndex
CREATE INDEX "EquitySignal_liveAuthorizedAt_idx" ON "EquitySignal"("liveAuthorizedAt");

-- CreateIndex
CREATE INDEX "EquitySignalCitation_signalId_idx" ON "EquitySignalCitation"("signalId");

-- CreateIndex
CREATE INDEX "EquitySignalCitation_sourceType_sourceId_idx" ON "EquitySignalCitation"("sourceType", "sourceId");

-- CreateIndex
CREATE INDEX "EquityPosition_signalId_idx" ON "EquityPosition"("signalId");

-- CreateIndex
CREATE INDEX "EquityPosition_instrumentId_status_idx" ON "EquityPosition"("instrumentId", "status");

-- CreateIndex
CREATE INDEX "EquityPosition_externalOrderId_idx" ON "EquityPosition"("externalOrderId");

-- CreateIndex
CREATE UNIQUE INDEX "EquityPortfolioState_organizationId_key" ON "EquityPortfolioState"("organizationId");

-- AddForeignKey
ALTER TABLE "EquityPriceTick" ADD CONSTRAINT "EquityPriceTick_instrumentId_fkey" FOREIGN KEY ("instrumentId") REFERENCES "EquityInstrument"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EquitySignal" ADD CONSTRAINT "EquitySignal_instrumentId_fkey" FOREIGN KEY ("instrumentId") REFERENCES "EquityInstrument"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EquitySignal" ADD CONSTRAINT "EquitySignal_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EquitySignalCitation" ADD CONSTRAINT "EquitySignalCitation_signalId_fkey" FOREIGN KEY ("signalId") REFERENCES "EquitySignal"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EquityPosition" ADD CONSTRAINT "EquityPosition_signalId_fkey" FOREIGN KEY ("signalId") REFERENCES "EquitySignal"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EquityPosition" ADD CONSTRAINT "EquityPosition_instrumentId_fkey" FOREIGN KEY ("instrumentId") REFERENCES "EquityInstrument"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EquityPosition" ADD CONSTRAINT "EquityPosition_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EquityPortfolioState" ADD CONSTRAINT "EquityPortfolioState_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
