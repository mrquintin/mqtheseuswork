import { PrismaPg } from "@prisma/adapter-pg";

/**
 * Prisma 7+ driver adapter. We're on Postgres everywhere (Supabase / Neon /
 * local Docker), so this just constructs a pg pool from `DATABASE_URL`.
 *
 * Expected URLs:
 *   - Supabase pooler:  postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres?pgbouncer=true
 *   - Supabase direct:  postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres
 *   - Neon:             postgresql://<user>:<pw>@<project>-pooler.<region>.aws.neon.tech/<db>?sslmode=require
 *   - Local Docker:     postgresql://theseus:theseus@localhost:5432/theseus
 *
 * For serverless (Vercel), prefer the pooled/pgbouncer URL so connection
 * churn doesn't exhaust Postgres slots.
 */
export function createSqlAdapter() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error("DATABASE_URL is not set (see theseus-codex/.env.example)");
  }
  if (!url.startsWith("postgres:") && !url.startsWith("postgresql:")) {
    throw new Error(
      `DATABASE_URL must be a Postgres URL (got ${url.slice(0, 16)}…). ` +
        "SQLite support was dropped when the Codex moved to cloud hosting — " +
        "see docs/Operations_Manual.md for local-dev Postgres setup.",
    );
  }
  return new PrismaPg({ connectionString: url });
}
