import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";

/**
 * Prisma 7+ requires a driver adapter at runtime. Local dev uses better-sqlite3 (via adapter).
 * Postgres: extend with `@prisma/adapter-pg` + `pg` (see Operations manual).
 */
export function createSqlAdapter() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error("DATABASE_URL is not set");
  }
  if (url.startsWith("postgres:") || url.startsWith("postgresql:")) {
    throw new Error(
      "DATABASE_URL is Postgres but the pg adapter is not wired in this build. " +
        "Use SQLite (file:./dev.db) for local dev, or extend src/lib/prismaAdapter.ts for @prisma/adapter-pg.",
    );
  }
  return new PrismaBetterSqlite3({ url });
}
