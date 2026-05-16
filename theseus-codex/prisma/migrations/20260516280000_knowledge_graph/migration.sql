-- Round 19 prompt 13: knowledge graph.
--
-- Adds the GraphSnapshot table (append-only history of one org's
-- knowledge-graph projection) and the GraphEdgeReasoning table
-- (cached agent reasoning per edge so public clicks are instant).
-- Mirrors noosphere alembic revision 022_knowledge_graph. Additive
-- only — no existing rows are touched.

-- 1. GraphSnapshot.

CREATE TABLE "GraphSnapshot" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "snapshotAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "version" TEXT NOT NULL DEFAULT 'kg/v1',
    "nodesJson" TEXT NOT NULL DEFAULT '[]',
    "edgesJson" TEXT NOT NULL DEFAULT '[]',
    "nodeCount" INTEGER NOT NULL DEFAULT 0,
    "edgeCount" INTEGER NOT NULL DEFAULT 0,
    "notes" TEXT NOT NULL DEFAULT '',

    CONSTRAINT "GraphSnapshot_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "GraphSnapshot_organizationId_snapshotAt_idx"
    ON "GraphSnapshot"("organizationId", "snapshotAt" DESC);

ALTER TABLE "GraphSnapshot"
    ADD CONSTRAINT "GraphSnapshot_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- 2. GraphEdgeReasoning.

CREATE TABLE "GraphEdgeReasoning" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "src" TEXT NOT NULL,
    "dst" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    "generatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "GraphEdgeReasoning_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "GraphEdgeReasoning_organizationId_src_dst_kind_idx"
    ON "GraphEdgeReasoning"("organizationId", "src", "dst", "kind");

ALTER TABLE "GraphEdgeReasoning"
    ADD CONSTRAINT "GraphEdgeReasoning_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;
