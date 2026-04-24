-- ── Soft-delete column on Upload ─────────────────────────────────────
-- Additive + nullable. Every existing row has `deletedAt = NULL` → still
-- visible exactly as before. Hiding is done at query time by filtering
-- `deletedAt IS NULL`; nothing is physically removed.
ALTER TABLE "Upload"
  ADD COLUMN IF NOT EXISTS "deletedAt" TIMESTAMP(3);

CREATE INDEX IF NOT EXISTS "Upload_deletedAt_idx" ON "Upload"("deletedAt");

-- ── DeletionRequest table ────────────────────────────────────────────
-- Peer-to-peer "please delete" workflow. Owner-only acceptance flips
-- Upload.deletedAt; decline keeps the upload intact with a decision
-- note. Requester may cancel their own pending request at any time.
CREATE TABLE IF NOT EXISTS "DeletionRequest" (
  "id"           TEXT PRIMARY KEY,
  "uploadId"     TEXT NOT NULL,
  "requesterId"  TEXT NOT NULL,
  "status"       TEXT NOT NULL DEFAULT 'pending',
  "reason"       TEXT,
  "decision"     TEXT,
  "createdAt"    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "respondedAt"  TIMESTAMP(3),
  CONSTRAINT "DeletionRequest_upload_fkey"
    FOREIGN KEY ("uploadId") REFERENCES "Upload"("id") ON DELETE CASCADE,
  CONSTRAINT "DeletionRequest_requester_fkey"
    FOREIGN KEY ("requesterId") REFERENCES "Founder"("id")
);

CREATE INDEX IF NOT EXISTS "DeletionRequest_uploadId_idx"
  ON "DeletionRequest"("uploadId");
CREATE INDEX IF NOT EXISTS "DeletionRequest_requesterId_idx"
  ON "DeletionRequest"("requesterId");
CREATE INDEX IF NOT EXISTS "DeletionRequest_status_idx"
  ON "DeletionRequest"("status");

-- At most one ACTIVE (status = 'pending') request per (upload, requester).
-- Enforced as a partial unique index so accepted/declined/cancelled
-- rows don't block a future new request on the same upload.
CREATE UNIQUE INDEX IF NOT EXISTS "DeletionRequest_active_unique"
  ON "DeletionRequest"("uploadId", "requesterId")
  WHERE "status" = 'pending';
