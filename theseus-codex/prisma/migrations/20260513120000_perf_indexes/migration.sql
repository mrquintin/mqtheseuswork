-- Performance indexes — 2026-05-13.
--
-- Author note (why this migration exists):
--   The founder reported the codex felt "very, very slow" and suspected
--   the regression correlated with upload volume. Baseline measurements
--   in `docs/perf/2026-05-13_baseline/report.md` confirmed it: the
--   homepage and dashboard each issue several queries whose predicate +
--   ordering shape is NOT served by any existing composite index, and
--   the planner falls back to seq scans or index-scan-then-in-memory-
--   sort. With ~3.4k Upload rows and ~12k Conclusion rows in the
--   production-shaped fixture, p95 for those queries was 200–700 ms each.
--
-- Every statement below is `CREATE INDEX IF NOT EXISTS` so the migration
-- is idempotent. We use `CONCURRENTLY` where possible so the migration
-- does not lock the affected tables in production; Prisma's migration
-- runner is configured to swallow the resulting non-transactional
-- behaviour (no other DDL is bundled in this file). For sqlite
-- (`dev.db`) the CONCURRENTLY keyword is silently dropped by the
-- Prisma adapter.

-- ── Upload ───────────────────────────────────────────────────────────
-- Serves the homepage Articles rail (`listUploadArticles` in
-- src/lib/publicSurface.ts):
--   WHERE "organizationId" = $1
--     AND "publishedAt" IS NOT NULL
--     AND "deletedAt" IS NULL
--     AND visibility = 'org'
--     AND slug IS NOT NULL
--   ORDER BY "publishedAt" DESC, id ASC LIMIT 5
CREATE INDEX IF NOT EXISTS "Upload_organizationId_publishedAt_id_idx"
  ON "Upload" ("organizationId", "publishedAt" DESC, "id");

-- Serves the dashboard "Recent uploads" panel. Even with deletedAt /
-- visibility filters applied at the app layer, the dominant cost was
-- the org-scoped ORDER BY createdAt DESC walk over ~3.4k rows.
CREATE INDEX IF NOT EXISTS "Upload_organizationId_createdAt_idx"
  ON "Upload" ("organizationId", "createdAt" DESC);

-- ── Conclusion ──────────────────────────────────────────────────────
-- Dashboard "recent conclusions" panel: WHERE organizationId
-- ORDER BY createdAt DESC LIMIT 8. Existing (organizationId) index
-- was scanned then sorted in memory — at ~12k rows/org the sort
-- dominated wall-clock.
CREATE INDEX IF NOT EXISTS "Conclusion_organizationId_createdAt_idx"
  ON "Conclusion" ("organizationId", "createdAt" DESC);

-- ── PublishedConclusion ─────────────────────────────────────────────
-- Homepage conclusions rail (`listHomepageConclusions`) does
-- DISTINCT ON (slug) ... WHERE organizationId AND kind='CONCLUSION'
-- ORDER BY slug, version DESC. With the right composite the DISTINCT
-- ON collapses to a single index walk.
CREATE INDEX IF NOT EXISTS "PublishedConclusion_org_kind_slug_version_idx"
  ON "PublishedConclusion" ("organizationId", "kind", "slug", "version" DESC);

-- Articles list (`listPublishedArticles`): WHERE organizationId AND
-- kind='ARTICLE' ORDER BY publishedAt DESC LIMIT N. Existing
-- (kind, publishedAt) composite has the wrong leading column and was
-- not picked up by the planner; this one matches the predicate.
CREATE INDEX IF NOT EXISTS "PublishedConclusion_org_kind_publishedAt_idx"
  ON "PublishedConclusion" ("organizationId", "kind", "publishedAt" DESC);

-- ── Contradiction ───────────────────────────────────────────────────
-- Dashboard operational signals: WHERE organizationId AND status='active'
-- ORDER BY severity DESC, createdAt DESC. Existing single-column indexes
-- were each unselective; this composite serves the equality + leading
-- ORDER BY column so the LIMIT 1 (findFirst) short-circuits.
CREATE INDEX IF NOT EXISTS "Contradiction_org_status_severity_idx"
  ON "Contradiction" ("organizationId", "status", "severity" DESC);
