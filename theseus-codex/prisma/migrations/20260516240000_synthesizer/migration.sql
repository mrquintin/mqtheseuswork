-- Round 19 prompt 10: synthesizer engine.
--
-- Adds two new tables (SynthesizerTask + SynthesizerMemo) and two
-- supporting enums. Also wires the LogicalAlgorithm row to the
-- synthesizer trigger flag (defaults to false so an existing algorithm
-- is not retroactively wired to the synthesizer — the founder flips
-- the flag in the triage UI).

-- 1. Enums.
CREATE TYPE "SynthesizerTaskTrigger" AS ENUM (
    'OPERATOR',
    'ALGORITHM',
    'CURRENT'
);

CREATE TYPE "SynthesizerTaskStatus" AS ENUM (
    'PENDING',
    'RUNNING',
    'DONE',
    'FAILED'
);

-- 2. Algorithm trigger flag.
ALTER TABLE "LogicalAlgorithm"
    ADD COLUMN "triggersSynthesis" BOOLEAN NOT NULL DEFAULT false;

-- 3. Task queue.
CREATE TABLE "SynthesizerTask" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "trigger" "SynthesizerTaskTrigger" NOT NULL DEFAULT 'OPERATOR',
    "status" "SynthesizerTaskStatus" NOT NULL DEFAULT 'PENDING',
    "enqueuedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "startedAt" TIMESTAMP(3),
    "finishedAt" TIMESTAMP(3),
    "invocationId" TEXT,
    "algorithmId" TEXT,
    "currentEventId" TEXT,
    "memoId" TEXT,
    "outcome" TEXT,
    "reasoning" TEXT,
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    CONSTRAINT "SynthesizerTask_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "SynthesizerTask_org_status_idx"
    ON "SynthesizerTask"("organizationId", "status");

CREATE INDEX "SynthesizerTask_status_enqueuedAt_idx"
    ON "SynthesizerTask"("status", "enqueuedAt");

CREATE INDEX "SynthesizerTask_invocationId_idx"
    ON "SynthesizerTask"("invocationId");

CREATE INDEX "SynthesizerTask_currentEventId_idx"
    ON "SynthesizerTask"("currentEventId");

ALTER TABLE "SynthesizerTask"
    ADD CONSTRAINT "SynthesizerTask_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "SynthesizerTask"
    ADD CONSTRAINT "SynthesizerTask_invocationId_fkey"
    FOREIGN KEY ("invocationId")
    REFERENCES "AlgorithmInvocation"("id")
    ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "SynthesizerTask"
    ADD CONSTRAINT "SynthesizerTask_algorithmId_fkey"
    FOREIGN KEY ("algorithmId")
    REFERENCES "LogicalAlgorithm"("id")
    ON DELETE SET NULL ON UPDATE CASCADE;

-- 4. Memo persistence.
CREATE TABLE "SynthesizerMemo" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "synthesizerVersion" TEXT NOT NULL DEFAULT 'synthesizer/v1',
    "question" TEXT NOT NULL DEFAULT '',
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    CONSTRAINT "SynthesizerMemo_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "SynthesizerMemo_org_createdAt_idx"
    ON "SynthesizerMemo"("organizationId", "createdAt" DESC);

CREATE INDEX "SynthesizerMemo_synthesizerVersion_idx"
    ON "SynthesizerMemo"("synthesizerVersion");

ALTER TABLE "SynthesizerMemo"
    ADD CONSTRAINT "SynthesizerMemo_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;
