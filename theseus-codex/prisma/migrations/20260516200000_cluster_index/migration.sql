-- Prompt 07 of Round 19 (2026-05-16): cluster index for contradiction tests.
--
-- Pre-filter for the canonical contradiction engine (prompt 06). The engine
-- remains the source of truth for verdicts; these tables decide WHICH pairs
-- the engine looks at. Solves Jacob's O(N²) cost concern: a new principle
-- is tested only against principles in the same semantic cluster, plus a
-- small cross-cluster sample to catch surprise links.
--
-- Additive only — no existing table is renamed or dropped.
--
-- Mirror: noosphere/alembic/versions/016_cluster_index.py

CREATE TABLE "PrincipleCluster" (
  "principleId"       TEXT PRIMARY KEY,
  "organizationId"    TEXT NOT NULL,
  "clusterId"         TEXT NOT NULL,
  "assignmentMethod"  TEXT NOT NULL DEFAULT 'incremental/v1',
  "assignedAt"        TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "PrincipleCluster_principleId_fkey"
    FOREIGN KEY ("principleId") REFERENCES "Principle"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "PrincipleCluster_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE INDEX "PrincipleCluster_org_cluster_idx"
  ON "PrincipleCluster" ("organizationId", "clusterId");

CREATE INDEX "PrincipleCluster_cluster_assignedAt_idx"
  ON "PrincipleCluster" ("clusterId", "assignedAt" DESC);

CREATE TABLE "PrincipleClusterCentroid" (
  "clusterId"         TEXT PRIMARY KEY,
  "organizationId"    TEXT NOT NULL,
  "centroidVec"       BYTEA NOT NULL DEFAULT ''::BYTEA,
  "dim"               INTEGER NOT NULL DEFAULT 0,
  "memberCount"       INTEGER NOT NULL DEFAULT 0,
  "assignmentMethod"  TEXT NOT NULL DEFAULT 'incremental/v1',
  "updatedAt"         TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "PrincipleClusterCentroid_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE INDEX "PrincipleClusterCentroid_org_idx"
  ON "PrincipleClusterCentroid" ("organizationId");

CREATE TABLE "ContradictionTestTask" (
  "id"                TEXT PRIMARY KEY,
  "organizationId"    TEXT NOT NULL,
  "principleAId"      TEXT NOT NULL,
  "principleBId"      TEXT NOT NULL,
  "pairKey"           TEXT NOT NULL DEFAULT '',
  "priority"          TEXT NOT NULL DEFAULT 'NORMAL',
  "status"            TEXT NOT NULL DEFAULT 'PENDING',
  "enqueuedAt"        TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "startedAt"         TIMESTAMP(3),
  "finishedAt"        TIMESTAMP(3),
  "resultId"          TEXT,
  "lastError"         TEXT,
  CONSTRAINT "ContradictionTestTask_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "ContradictionTestTask_resultId_fkey"
    FOREIGN KEY ("resultId") REFERENCES "Contradiction"("id")
    ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX "ContradictionTestTask_status_priority_enqueuedAt_idx"
  ON "ContradictionTestTask" ("status", "priority", "enqueuedAt");

CREATE INDEX "ContradictionTestTask_pairKey_enqueuedAt_idx"
  ON "ContradictionTestTask" ("pairKey", "enqueuedAt" DESC);

CREATE INDEX "ContradictionTestTask_org_status_idx"
  ON "ContradictionTestTask" ("organizationId", "status");

CREATE TABLE "ClusterReindexProposal" (
  "id"                   TEXT PRIMARY KEY,
  "organizationId"       TEXT NOT NULL,
  "proposedAt"           TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "drift"                DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  "clusterCountBefore"   INTEGER NOT NULL DEFAULT 0,
  "clusterCountAfter"    INTEGER NOT NULL DEFAULT 0,
  "summaryJson"          TEXT NOT NULL DEFAULT '{}',
  "status"               TEXT NOT NULL DEFAULT 'PENDING',
  "resolvedByFounderId"  TEXT,
  "resolvedAt"           TIMESTAMP(3),
  CONSTRAINT "ClusterReindexProposal_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "ClusterReindexProposal_resolvedByFounderId_fkey"
    FOREIGN KEY ("resolvedByFounderId") REFERENCES "Founder"("id")
    ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX "ClusterReindexProposal_org_status_idx"
  ON "ClusterReindexProposal" ("organizationId", "status");
