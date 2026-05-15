# Migration Runbook

This runbook describes how to bring **dev**, **staging**, and **prod**
Postgres environments to the same schema state using the repository's
Prisma + Alembic migration tooling. It supersedes the apply-only notes in
[`PRODUCTION_MIGRATION.md`](./PRODUCTION_MIGRATION.md) -- that document
still describes the apply runner in isolation; this runbook is the
end-to-end procedure.

The migration tail from Round 17 plus prompt 01 introduced enough schema
changes that an unguarded apply against a non-empty database is no longer
acceptable. The procedure below adds a **linearity check**, a
**structure-only snapshot**, a **diff-aware dry run**, and an explicit
**rollback path** so that all three environments can be advanced without
data loss.

## Tooling

| Script | Purpose |
| --- | --- |
| `scripts/check_migration_linearity.py` | Static check that no two Prisma migrations contradict each other (double-create, double-add, etc.). Pure file scan; no DB required. |
| `scripts/snapshot_production_schema.sh` | `pg_dump --schema-only` of `$DATABASE_URL`. Writes to `docs/architecture/snapshots/<UTC>.sql`. |
| `scripts/migrate_production_dry_run.sh` | Linearity check + destructive-op justification scan + live plan against `$DATABASE_URL`. Refuses if the diff is empty (already-applied) or if a pending migration contains an unjustified `DROP COLUMN` / `DROP TABLE`. |
| `scripts/migrate_production.sh` | Apply path. Takes a snapshot, runs Prisma then Alembic, prints rollback SQL if either fails. |

## Procedure

The procedure runs identically against dev, staging, and prod. The only
differences are the value of `$DATABASE_URL` and how aggressive the
operator confirmation step is.

### 1. Pre-flight (off the production host)

```bash
python scripts/check_migration_linearity.py
```

If this fails, **stop**. Fix the migration history in version control
before touching any environment. A failure here usually means two
migration files were created on different branches and merged without
resolving their interaction.

### 2. Dry-run against the target environment

```bash
DATABASE_URL='postgresql://...' scripts/migrate_production_dry_run.sh
```

The dry-run performs three checks in order:

1. **Linearity** (same script as step 1).
2. **Destructive-op justification.** Every `DROP COLUMN` and
   `DROP TABLE` in any migration file must be accompanied by a comment
   containing `JUSTIFY:` (case-insensitive) in the same migration file.
   Migrations without justification are reported and the dry-run
   refuses to continue.
3. **Live plan** -- delegates to `migrate_production.sh --dry-run`,
   which validates `DATABASE_URL`, requires the operator to type the
   target hostname, and lists pending Prisma + Alembic migrations.

The dry-run exits **non-zero** when:

- the linearity check finds a contradiction;
- a destructive op is missing a `JUSTIFY:` comment;
- **the live plan reports zero pending migrations** -- treated as a
  signal that the migration is already applied; running the deploy
  here would be a no-op that masks drift.

### 3. Snapshot the target environment

Done automatically by `migrate_production.sh` (see step 4). If you want
an ad-hoc snapshot before a non-migration change:

```bash
DATABASE_URL='postgresql://...' scripts/snapshot_production_schema.sh
```

Snapshots land in `docs/architecture/snapshots/<UTC-timestamp>.sql`.
They are committed weekly by the existing scheduler; ad-hoc snapshots
should also be committed if they reflect the current state of a real
environment.

### 4. Apply

```bash
DATABASE_URL='postgresql://...' scripts/migrate_production.sh
```

This wrapper:

1. Validates `$DATABASE_URL`, refuses local hosts unless
   `--allow-localhost`, requires hostname confirmation.
2. Lists Prisma and Alembic pending work, requires a literal `yes`.
3. **Takes a pre-migration structure-only snapshot** to
   `docs/architecture/snapshots/<UTC>.pre-migrate.sql`.
4. Runs `prisma migrate deploy` from `theseus-codex/`. Each Prisma
   migration runs in its own transaction (Prisma's default for
   transactional DDL); a single migration that contains non-transactional
   DDL is the only case where partial application can occur, and Prisma
   marks the row as failed in `_prisma_migrations`.
5. Runs `alembic upgrade head` from `noosphere/` with
   `THESEUS_DATABASE_URL` set. Each Alembic migration runs in its own
   transaction.
6. Re-runs both status checks and refuses success if either still
   reports pending work.
7. Prints row counts for the canary tables.

If step 4 or 5 fails, the script prints the rollback SQL the operator
must run and exits non-zero with the failure stage encoded in the exit
code.

### 5. Verify

After a clean apply, confirm parity by re-running the dry-run -- it
should now refuse with "schema already matches migrations on disk",
which is the expected post-apply state.

```bash
DATABASE_URL='postgresql://...' scripts/migrate_production_dry_run.sh
# exits non-zero with: "live plan reports 0 pending migrations"
```

## Constraints

- **No destructive operations without explicit operator confirmation.**
  The apply runner requires `yes` at the final prompt, and the dry-run
  refuses any unjustified `DROP COLUMN` / `DROP TABLE`.
- **Foreign-key changes must use drop-FK / alter / recreate-FK** rather
  than `ALTER COLUMN ... CASCADE` patterns that hold table-level locks
  on Supabase. New migrations that change FK columns must spell out the
  three-step pattern in their `migration.sql`.
- **Postgres only.** The migration scripts assume Postgres; there is no
  SQLite branch. Local rehearsals must use a Postgres container.

## Failure-mode table

| Exit code | Stage | Cause | Operator action |
| --- | --- | --- | --- |
| 1 | pre-flight (dry-run) | Linearity contradiction detected. | Fix migration history in VCS; do not apply. |
| 1 | pre-flight (dry-run) | Pending migration has unjustified `DROP COLUMN` / `DROP TABLE`. | Add a `JUSTIFY: <reason>` comment to the migration file and re-run. |
| 1 | pre-flight (dry-run) | Live plan reports 0 pending migrations. | Already applied; no action needed. Investigate if you expected new migrations. |
| 1 | pre-flight (apply) | `DATABASE_URL` missing/malformed, hostname mismatch, missing CLI, or rejected final `yes`. | Fix the cause; no migration was attempted. |
| 1 | pre-flight (apply) | Pre-migration snapshot failed. | Restore `pg_dump` access; rerun. No migration was attempted. |
| 2 | prisma | `prisma migrate deploy` failed. | Read printed rollback SQL. Inspect `_prisma_migrations` for the failed row; restore from snapshot if DDL was partially applied. |
| 2 | post-prisma | Prisma deploy returned 0 but `prisma migrate status` still reports pending work. | Re-run dry-run; do not retry apply blindly. |
| 3 | alembic | `alembic upgrade head` failed after Prisma succeeded. | Read printed rollback SQL. `alembic current` and `alembic downgrade -1` from `noosphere/` to back out the last step. Prisma changes remain applied. |
| 3 | post-alembic | Alembic returned 0 but still reports pending. | Re-run dry-run; investigate `alembic_version` table. |

## Rollback path

The apply runner prints a concrete rollback playbook on failure
(including the snapshot file path). The general shape:

1. **`alembic downgrade -1`** if the failure stage was `alembic` and the
   failed migration is reversible.
2. **`UPDATE _prisma_migrations SET rolled_back_at = NOW()`** for the
   failing Prisma row, after confirming via the Prisma output above
   which migration failed.
3. **Restore from the pre-migration snapshot** with
   `psql -f docs/architecture/snapshots/<UTC>.pre-migrate.sql` only if
   the DDL was partially applied. This is destructive -- it drops and
   recreates objects -- and must be done with a fresh data backup.

After any rollback, re-run `scripts/migrate_production_dry_run.sh`
before retrying the apply.

## Tests

`tests/migration/test_migration_linearity.py` exercises the linearity
check against synthetic migration directories and (when a Postgres
container is reachable via `MIGRATION_TEST_DATABASE_URL`) verifies that:

- the dry-run reports the exact set of pending operations against an
  empty database;
- the apply runner is idempotent -- running it twice against the same
  database produces the same final schema.

See the test file for invocation details.
