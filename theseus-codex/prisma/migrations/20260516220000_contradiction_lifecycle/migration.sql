-- Round 19 prompt 19: Source-driven contradiction lifecycle.
--
-- The manual "resolve" pattern is gone. A contradiction is no longer
-- closed by an operator clicking a button — it persists as a first-class
-- entity and transitions through DETECTED / STANDING / WEAKENED /
-- RESOLVED_BY_SOURCE / DISPUTED_AS_ERROR / SUBSUMED_BY_SYNTHESIS in
-- response to source ingestion. The "events_json" column is the
-- append-only event log; the denormalised currentStatus /
-- lastTransitionAt mirror its tail.

CREATE TABLE "ContradictionLifecycle" (
    "id" TEXT NOT NULL,
    "contradictionId" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "currentStatus" TEXT NOT NULL DEFAULT 'DETECTED',
    "lastTransitionAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "eventsJson" TEXT NOT NULL DEFAULT '[]',
    "supportedPrincipleId" TEXT,
    "subsumingPrincipleId" TEXT,
    "pendingSubsumptionPrincipleId" TEXT,

    CONSTRAINT "ContradictionLifecycle_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ContradictionLifecycle_contradictionId_key"
    ON "ContradictionLifecycle"("contradictionId");

CREATE INDEX "ContradictionLifecycle_org_status_at_idx"
    ON "ContradictionLifecycle"(
        "organizationId",
        "currentStatus",
        "lastTransitionAt" DESC
    );

CREATE INDEX "ContradictionLifecycle_currentStatus_idx"
    ON "ContradictionLifecycle"("currentStatus");

CREATE INDEX "ContradictionLifecycle_pending_subsumption_idx"
    ON "ContradictionLifecycle"("pendingSubsumptionPrincipleId");

ALTER TABLE "ContradictionLifecycle"
    ADD CONSTRAINT "ContradictionLifecycle_contradictionId_fkey"
    FOREIGN KEY ("contradictionId") REFERENCES "Contradiction"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "ContradictionLifecycle"
    ADD CONSTRAINT "ContradictionLifecycle_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;
