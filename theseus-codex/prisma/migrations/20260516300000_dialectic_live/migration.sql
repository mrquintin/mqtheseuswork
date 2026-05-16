-- Round 19 prompt 14: Dialectic live recording mode.
--
-- Adds DialecticSession, DialecticUtterance, DialecticContradictionFlag.
-- Mirrors noosphere alembic revision 023_dialectic_live. Additive only.

-- 1. DialecticSession.

CREATE TABLE "DialecticSession" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "title" TEXT NOT NULL DEFAULT '',
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "endedAt" TIMESTAMP(3),
    "participantsJson" TEXT NOT NULL DEFAULT '[]',
    "audioPath" TEXT NOT NULL DEFAULT '',
    "transcriptPath" TEXT NOT NULL DEFAULT '',
    "status" TEXT NOT NULL DEFAULT 'RECORDING',
    "visibility" TEXT NOT NULL DEFAULT 'PRIVATE',
    "liveContradictionsDetected" INTEGER NOT NULL DEFAULT 0,
    "principlesExtracted" INTEGER NOT NULL DEFAULT 0,
    "summaryMemoId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "DialecticSession_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "DialecticSession_organizationId_status_idx"
    ON "DialecticSession"("organizationId", "status");
CREATE INDEX "DialecticSession_startedAt_idx"
    ON "DialecticSession"("startedAt");

ALTER TABLE "DialecticSession"
    ADD CONSTRAINT "DialecticSession_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- 2. DialecticUtterance.

CREATE TABLE "DialecticUtterance" (
    "id" TEXT NOT NULL,
    "sessionId" TEXT NOT NULL,
    "speakerId" TEXT NOT NULL,
    "startTime" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "endTime" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "text" TEXT NOT NULL DEFAULT '',
    "extractedClaimIdsJson" TEXT NOT NULL DEFAULT '[]',
    "derivedPrincipleIdsJson" TEXT NOT NULL DEFAULT '[]',
    "liveContradictionFlagsJson" TEXT NOT NULL DEFAULT '[]',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DialecticUtterance_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "DialecticUtterance_sessionId_startTime_idx"
    ON "DialecticUtterance"("sessionId", "startTime");
CREATE INDEX "DialecticUtterance_speakerId_idx"
    ON "DialecticUtterance"("speakerId");

ALTER TABLE "DialecticUtterance"
    ADD CONSTRAINT "DialecticUtterance_sessionId_fkey"
    FOREIGN KEY ("sessionId")
    REFERENCES "DialecticSession"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;

-- 3. DialecticContradictionFlag.

CREATE TABLE "DialecticContradictionFlag" (
    "id" TEXT NOT NULL,
    "utteranceId" TEXT NOT NULL,
    "flagKind" TEXT NOT NULL DEFAULT 'INTRA_SESSION',
    "priorUtteranceId" TEXT,
    "priorPrincipleId" TEXT,
    "priorSpeakerId" TEXT,
    "contradictionScore" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "axis" TEXT,
    "humanExplanation" TEXT,
    "detectionMethod" TEXT NOT NULL DEFAULT '',
    "acknowledgedAt" TIMESTAMP(3),
    "acknowledgedBy" TEXT,
    "acknowledgmentNote" TEXT,
    "detectedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DialecticContradictionFlag_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "DialecticContradictionFlag_utteranceId_idx"
    ON "DialecticContradictionFlag"("utteranceId");
CREATE INDEX "DialecticContradictionFlag_flagKind_idx"
    ON "DialecticContradictionFlag"("flagKind");

ALTER TABLE "DialecticContradictionFlag"
    ADD CONSTRAINT "DialecticContradictionFlag_utteranceId_fkey"
    FOREIGN KEY ("utteranceId")
    REFERENCES "DialecticUtterance"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
