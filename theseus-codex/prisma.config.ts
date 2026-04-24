import path from "node:path";
import { defineConfig, env } from "prisma/config";

/**
 * Prisma 7+ — connection URL lives here, not in schema.prisma.
 *
 * DATABASE_URL   runtime queries. Pooled (e.g. Supabase port 6543 with pgbouncer=true)
 *                so serverless connections don't exhaust Postgres slots.
 * DIRECT_URL     migrations only. Direct connection (e.g. Supabase port 5432) — pgbouncer
 *                in transaction mode strips the advisory locks `prisma migrate` relies on,
 *                so migrations hang forever when pointed at the pooler.
 *
 * If DIRECT_URL isn't set, fall back to DATABASE_URL. (Local Docker Postgres has no
 * pooler in front of it, so one URL suffices.)
 */
export default defineConfig({
  schema: path.join("prisma", "schema.prisma"),
  migrations: {
    path: path.join("prisma", "migrations"),
    seed: "tsx prisma/seed.ts",
  },
  datasource: {
    url: env("DATABASE_URL"),
  },
});
