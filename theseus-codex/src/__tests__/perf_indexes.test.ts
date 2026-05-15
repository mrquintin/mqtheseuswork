/**
 * Verifies that every join/order column on the homepage-critical
 * query path is backed by a real database index — introspected via
 * `pg_indexes`, NOT by reading `schema.prisma`.
 *
 * Why pg_indexes and not the schema file:
 *   The schema file is what we INTENDED to declare; pg_indexes is what
 *   the running DB actually has. Migrations can drift, an `IF NOT
 *   EXISTS` can swallow a typo, or a hand-rolled DROP INDEX can run in
 *   prod without anyone updating the schema. The test asserts the
 *   production state, which is the state the founder's queries are
 *   subject to.
 *
 * Connection: the test requires a Postgres `DATABASE_URL` whose schema
 * already includes the 2026-05-13 `perf_indexes` migration. In CI this
 * is the standard test DB; locally, run
 * `npm exec prisma migrate deploy` before invoking
 * `npm test -- perf_indexes`. When `DATABASE_URL` points at sqlite (the
 * dev.db case) the test skips itself rather than asserting against a
 * different catalog — sqlite's index introspection lives in
 * `sqlite_master`, and the index-DDL itself differs (no DESC support).
 */

import { describe, expect, it } from "vitest";

// Index name → required columns IN ORDER. The names match the
// `CREATE INDEX` statements in
// `prisma/migrations/20260513120000_perf_indexes/migration.sql`; if a
// migration renames an index the test should fail loudly (you want the
// rename to be a deliberate code change).
const REQUIRED_INDEXES: ReadonlyArray<{
  index: string;
  table: string;
  columns: readonly string[];
}> = [
  {
    index: "Upload_organizationId_publishedAt_id_idx",
    table: "Upload",
    columns: ["organizationId", "publishedAt", "id"],
  },
  {
    index: "Upload_organizationId_createdAt_idx",
    table: "Upload",
    columns: ["organizationId", "createdAt"],
  },
  {
    index: "Conclusion_organizationId_createdAt_idx",
    table: "Conclusion",
    columns: ["organizationId", "createdAt"],
  },
  {
    index: "PublishedConclusion_org_kind_slug_version_idx",
    table: "PublishedConclusion",
    columns: ["organizationId", "kind", "slug", "version"],
  },
  {
    index: "PublishedConclusion_org_kind_publishedAt_idx",
    table: "PublishedConclusion",
    columns: ["organizationId", "kind", "publishedAt"],
  },
  {
    index: "Contradiction_org_status_severity_idx",
    table: "Contradiction",
    columns: ["organizationId", "status", "severity"],
  },
];

function isPostgresUrl(url: string | undefined): boolean {
  if (!url) return false;
  return url.startsWith("postgres://") || url.startsWith("postgresql://");
}

describe("homepage-critical index coverage", () => {
  const databaseUrl = process.env.DATABASE_URL;
  if (!isPostgresUrl(databaseUrl)) {
    // Surface the skip reason in the test runner output. Returning
    // here keeps the suite green on sqlite-backed dev runs while
    // making it obvious that no production-shape assertion fired.
    it.skip("requires a Postgres DATABASE_URL (skipped on sqlite/dev)", () => {});
    return;
  }

  // Import Prisma lazily so the sqlite branch above never opens a
  // pg connection. The relative path mirrors how the rest of the
  // codex imports `db` — going through the alias keeps the test
  // honest about what the runtime sees.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { db } = require("@/lib/db") as { db: PrismaClientLike };

  for (const expected of REQUIRED_INDEXES) {
    it(`${expected.index} exists on ${expected.table} and covers ${expected.columns.join(", ")}`, async () => {
      const rows = await db.$queryRawUnsafe<DbIndexColumn[]>(
        `SELECT
           a.attname     AS column_name,
           array_position(ix.indkey::int[], a.attnum) AS ordinal
         FROM pg_class c
         JOIN pg_namespace n ON n.oid = c.relnamespace
         JOIN pg_index ix    ON ix.indexrelid = c.oid
         JOIN pg_class t     ON t.oid = ix.indrelid
         JOIN pg_attribute a ON a.attrelid = t.oid
                            AND a.attnum = ANY(ix.indkey)
         WHERE c.relname = $1
           AND t.relname = $2
           AND n.nspname = ANY(current_schemas(false))
         ORDER BY ordinal`,
        expected.index,
        expected.table,
      );

      // Empty result = the named index simply doesn't exist on the
      // table. Distinguish that from "exists but wrong columns" so a
      // future migration mis-spelling the table is debuggable.
      expect(rows.length, `index ${expected.index} not found on ${expected.table}`).toBeGreaterThan(0);

      const ordered = rows
        .slice()
        .sort((a, b) => (a.ordinal ?? 0) - (b.ordinal ?? 0))
        .map((r) => r.column_name);

      // pg_index includes EVERY column, including the optional INCLUDE
      // columns; we only assert the LEADING columns match in order.
      // That way a future migration appending INCLUDE columns for a
      // covering index doesn't break the test.
      const head = ordered.slice(0, expected.columns.length);
      expect(head).toEqual(expected.columns);
    });
  }
});

type DbIndexColumn = { column_name: string; ordinal: number | null };

interface PrismaClientLike {
  $queryRawUnsafe<T = unknown>(query: string, ...values: unknown[]): Promise<T>;
}
