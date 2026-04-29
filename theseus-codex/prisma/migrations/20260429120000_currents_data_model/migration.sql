-- CreateEnum
CREATE TYPE "CurrentEventStatus" AS ENUM ('OBSERVED', 'ENRICHED', 'OPINED', 'ABSTAINED', 'REVOKED');

-- CreateEnum
CREATE TYPE "CurrentEventSource" AS ENUM ('X_TWITTER', 'RSS', 'MANUAL');

-- CreateEnum
CREATE TYPE "OpinionStance" AS ENUM ('AGREES', 'DISAGREES', 'COMPLICATES', 'ABSTAINED');

-- CreateEnum
CREATE TYPE "AbstentionReason" AS ENUM ('INSUFFICIENT_SOURCES', 'NEAR_DUPLICATE', 'BUDGET', 'CITATION_FABRICATION', 'REVOKED_SOURCES');

-- CreateEnum
CREATE TYPE "FollowUpRole" AS ENUM ('USER', 'ASSISTANT');

-- CreateTable
CREATE TABLE "CurrentEvent" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "source" "CurrentEventSource" NOT NULL,
    "externalId" TEXT NOT NULL,
    "authorHandle" TEXT,
    "text" TEXT NOT NULL,
    "url" TEXT,
    "capturedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "observedAt" TIMESTAMP(3) NOT NULL,
    "topicHint" TEXT,
    "isNearDuplicate" BOOLEAN NOT NULL DEFAULT false,
    "embedding" BYTEA,
    "status" "CurrentEventStatus" NOT NULL DEFAULT 'OBSERVED',
    "dedupeHash" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "CurrentEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EventOpinion" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "eventId" TEXT NOT NULL,
    "stance" "OpinionStance" NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "headline" VARCHAR(140) NOT NULL,
    "bodyMarkdown" TEXT NOT NULL,
    "uncertaintyNotes" TEXT[],
    "topicHint" TEXT,
    "modelName" TEXT NOT NULL,
    "promptTokens" INTEGER NOT NULL DEFAULT 0,
    "completionTokens" INTEGER NOT NULL DEFAULT 0,
    "abstentionReason" "AbstentionReason",
    "generatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "revokedAt" TIMESTAMP(3),
    "revokedReason" TEXT,

    CONSTRAINT "EventOpinion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "OpinionCitation" (
    "id" TEXT NOT NULL,
    "opinionId" TEXT NOT NULL,
    "sourceKind" TEXT NOT NULL,
    "conclusionId" TEXT,
    "claimId" TEXT,
    "quotedSpan" TEXT NOT NULL,
    "retrievalScore" DOUBLE PRECISION NOT NULL,
    "isRevoked" BOOLEAN NOT NULL DEFAULT false,
    "revokedReason" TEXT,

    CONSTRAINT "OpinionCitation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FollowUpSession" (
    "id" TEXT NOT NULL,
    "opinionId" TEXT NOT NULL,
    "clientFingerprint" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lastActivityAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "FollowUpSession_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FollowUpMessage" (
    "id" TEXT NOT NULL,
    "sessionId" TEXT NOT NULL,
    "role" "FollowUpRole" NOT NULL,
    "content" TEXT NOT NULL,
    "citations" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "FollowUpMessage_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "CurrentEvent_dedupeHash_key" ON "CurrentEvent"("dedupeHash");

-- CreateIndex
CREATE INDEX "CurrentEvent_organizationId_observedAt_idx" ON "CurrentEvent"("organizationId", "observedAt");

-- CreateIndex
CREATE INDEX "CurrentEvent_organizationId_status_idx" ON "CurrentEvent"("organizationId", "status");

-- CreateIndex
CREATE INDEX "EventOpinion_organizationId_generatedAt_idx" ON "EventOpinion"("organizationId", "generatedAt");

-- CreateIndex
CREATE INDEX "EventOpinion_eventId_idx" ON "EventOpinion"("eventId");

-- CreateIndex
CREATE INDEX "OpinionCitation_opinionId_idx" ON "OpinionCitation"("opinionId");

-- CreateIndex
CREATE INDEX "OpinionCitation_conclusionId_idx" ON "OpinionCitation"("conclusionId");

-- CreateIndex
CREATE INDEX "OpinionCitation_claimId_idx" ON "OpinionCitation"("claimId");

-- CreateIndex
CREATE INDEX "FollowUpSession_opinionId_lastActivityAt_idx" ON "FollowUpSession"("opinionId", "lastActivityAt");

-- CreateIndex
CREATE INDEX "FollowUpSession_clientFingerprint_createdAt_idx" ON "FollowUpSession"("clientFingerprint", "createdAt");

-- CreateIndex
CREATE INDEX "FollowUpMessage_sessionId_createdAt_idx" ON "FollowUpMessage"("sessionId", "createdAt");

-- AddForeignKey
ALTER TABLE "CurrentEvent" ADD CONSTRAINT "CurrentEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EventOpinion" ADD CONSTRAINT "EventOpinion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EventOpinion" ADD CONSTRAINT "EventOpinion_eventId_fkey" FOREIGN KEY ("eventId") REFERENCES "CurrentEvent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "OpinionCitation" ADD CONSTRAINT "OpinionCitation_opinionId_fkey" FOREIGN KEY ("opinionId") REFERENCES "EventOpinion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FollowUpSession" ADD CONSTRAINT "FollowUpSession_opinionId_fkey" FOREIGN KEY ("opinionId") REFERENCES "EventOpinion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FollowUpMessage" ADD CONSTRAINT "FollowUpMessage_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES "FollowUpSession"("id") ON DELETE CASCADE ON UPDATE CASCADE;
