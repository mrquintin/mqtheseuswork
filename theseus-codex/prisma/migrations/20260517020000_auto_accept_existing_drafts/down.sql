-- Down migration for 20260517020000_auto_accept_existing_drafts.
--
-- The firm does not intend to roll this back. This file exists as a
-- safety net: if the auto-accept change has to be reverted, running
-- this DDL flips every accepted row back to draft and clears its
-- review/publish stamps. Prisma does not invoke this file
-- automatically; an operator must apply it by hand.

BEGIN;

UPDATE "Principle"
SET status        = 'draft',
    "publicVisible" = false,
    "reviewedAt"  = NULL,
    "publishedAt" = NULL,
    "updatedAt"   = NOW()
WHERE status = 'accepted';

COMMIT;
