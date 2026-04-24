-- Example Postgres RLS (apply after Prisma migrate to PostgreSQL).
-- Application sets: SET LOCAL app.current_org_id = '<cuid>';
-- Prisma table names follow the model names below (adjust @@map if you rename).

-- ALTER TABLE "Organization" ENABLE ROW LEVEL SECURITY;
-- (Usually org directory is server-side only; tenant rows live on child tables.)

ALTER TABLE "Founder" ENABLE ROW LEVEL SECURITY;
CREATE POLICY founder_tenant_isolation ON "Founder"
  USING ("organizationId" = current_setting('app.current_org_id', true));

ALTER TABLE "Upload" ENABLE ROW LEVEL SECURITY;
CREATE POLICY upload_tenant_isolation ON "Upload"
  USING ("organizationId" = current_setting('app.current_org_id', true));

ALTER TABLE "Conclusion" ENABLE ROW LEVEL SECURITY;
CREATE POLICY conclusion_tenant_isolation ON "Conclusion"
  USING ("organizationId" = current_setting('app.current_org_id', true));

-- Repeat for Contradiction, DriftEvent, ResearchSuggestion, ReviewItem, OpenQuestion, AuditEvent, Session.
-- Noosphere-native tables (artifact, claim, …) need their own organization_id columns + migrations before RLS.
