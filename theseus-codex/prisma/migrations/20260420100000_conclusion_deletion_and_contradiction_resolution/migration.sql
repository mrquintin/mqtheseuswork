-- Conclusion deletion requests (peer-to-peer delete workflow for Conclusions)
CREATE TABLE "ConclusionDeletionRequest" (
    "id" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "requesterId" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "reason" TEXT,
    "decision" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "respondedAt" TIMESTAMP(3),
    CONSTRAINT "ConclusionDeletionRequest_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "ConclusionDeletionRequest_conclusionId_idx"
    ON "ConclusionDeletionRequest"("conclusionId");
CREATE INDEX "ConclusionDeletionRequest_requesterId_idx"
    ON "ConclusionDeletionRequest"("requesterId");
CREATE INDEX "ConclusionDeletionRequest_status_idx"
    ON "ConclusionDeletionRequest"("status");
ALTER TABLE "ConclusionDeletionRequest"
    ADD CONSTRAINT "ConclusionDeletionRequest_conclusionId_fkey"
    FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ConclusionDeletionRequest"
    ADD CONSTRAINT "ConclusionDeletionRequest_requesterId_fkey"
    FOREIGN KEY ("requesterId") REFERENCES "Founder"("id")
    ON DELETE NO ACTION ON UPDATE CASCADE;

-- Dashboard dismissals (per-founder UI preference)
CREATE TABLE "DashboardDismissal" (
    "id" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DashboardDismissal_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "DashboardDismissal_founderId_conclusionId_key"
    ON "DashboardDismissal"("founderId", "conclusionId");
CREATE INDEX "DashboardDismissal_founderId_idx"
    ON "DashboardDismissal"("founderId");
CREATE INDEX "DashboardDismissal_conclusionId_idx"
    ON "DashboardDismissal"("conclusionId");
ALTER TABLE "DashboardDismissal"
    ADD CONSTRAINT "DashboardDismissal_founderId_fkey"
    FOREIGN KEY ("founderId") REFERENCES "Founder"("id")
    ON DELETE NO ACTION ON UPDATE CASCADE;
ALTER TABLE "DashboardDismissal"
    ADD CONSTRAINT "DashboardDismissal_conclusionId_fkey"
    FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;

-- Contradiction resolution tracking (prompt 09)
ALTER TABLE "Contradiction"
    ADD COLUMN "status" TEXT NOT NULL DEFAULT 'active';
ALTER TABLE "Contradiction"
    ADD COLUMN "resolution" TEXT;
ALTER TABLE "Contradiction"
    ADD COLUMN "resolvedById" TEXT;
ALTER TABLE "Contradiction"
    ADD COLUMN "resolvedAt" TIMESTAMP(3);
CREATE INDEX "Contradiction_status_idx"
    ON "Contradiction"("status");
ALTER TABLE "Contradiction"
    ADD CONSTRAINT "Contradiction_resolvedById_fkey"
    FOREIGN KEY ("resolvedById") REFERENCES "Founder"("id")
    ON DELETE NO ACTION ON UPDATE CASCADE;
