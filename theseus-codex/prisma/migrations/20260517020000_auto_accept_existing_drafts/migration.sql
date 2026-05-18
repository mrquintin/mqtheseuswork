-- Auto-accept any existing draft Principle rows.
--
-- Per founder direction (2026-05-17): principles and conclusions are
-- auto-accepted into noosphere; there is no user-approval gate. Rows
-- that landed as draft under the previous triage flow now collapse to
-- accepted + publicVisible. Rejected rows are left untouched so a
-- positively-set rejection still hides the principle.
--
-- This migration is idempotent: re-running it on an already-migrated
-- table is a no-op (the WHERE clause matches nothing).

BEGIN;

UPDATE "Principle"
SET status        = 'accepted',
    "publicVisible" = true,
    "reviewedAt"  = COALESCE("reviewedAt", "createdAt"),
    "publishedAt" = COALESCE("publishedAt", "createdAt"),
    "updatedAt"   = NOW()
WHERE status = 'draft';

COMMIT;
