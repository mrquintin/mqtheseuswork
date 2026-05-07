# Production Migration Runner

Use `scripts/migrate_production.sh` when production needs the repository's
Prisma and Alembic migrations applied to the same Postgres database. The script
is intentionally interactive because an unguarded `prisma migrate deploy` can
apply irreversible DDL to the wrong database.

## Required Environment

Set `DATABASE_URL` to the production Postgres URL before running either script.
The runner accepts only `postgresql://` and `postgres://` URLs. It prints only
the parsed host, port, and database name; it never prints the username,
password, or query string.

Required commands:

- `psql`
- `npx`
- `alembic`

The runner invokes Prisma from `theseus-codex/` and Alembic from `noosphere/`.
That matches the repository layout: Prisma 7 reads `DATABASE_URL` through
`theseus-codex/prisma.config.ts`, while Alembic's `script_location` is relative
to `noosphere/alembic.ini`. The runner sets `THESEUS_DATABASE_URL` from
`DATABASE_URL` for Alembic because `noosphere/alembic/env.py` reads the
Noosphere settings object, not bare `DATABASE_URL`.

## Dry Run

Run:

```bash
DATABASE_URL='postgresql://...' scripts/migrate_production_dry_run.sh
```

The dry run performs the same URL validation, command checks, host confirmation,
and plan listing as the production runner. It does not run
`npx prisma migrate deploy` or `alembic upgrade head`.

Dry-run exit behavior:

- `0`: both migrators report no pending migrations.
- `1`: pre-flight failed, confirmation failed, a migrator status command could
  not be trusted, or pending migrations were found.

For a local rehearsal database, pass `--allow-localhost`:

```bash
printf 'localhost\n' | DATABASE_URL='postgresql://postgres:postgres@localhost:5432/theseus' \
  scripts/migrate_production_dry_run.sh --allow-localhost
```

## Production Apply

Take a managed Postgres snapshot before applying migrations to a non-empty
production database.

Run:

```bash
DATABASE_URL='postgresql://...' scripts/migrate_production.sh
```

The script:

1. Refuses missing, malformed, non-Postgres, or accidental local URLs.
2. Prints only `host:port + db`.
3. Requires the operator to type the hostname exactly.
4. Lists Prisma pending work with `npx prisma migrate status`.
5. Lists Alembic state with `alembic current` and
   `alembic history --indicate-current`.
6. Requires a final literal `yes` at `apply N pending migrations? (yes/no)`.
7. Runs `npx prisma migrate deploy`.
8. Runs `alembic upgrade head`.
9. Re-runs both status checks and refuses success if either still reports
   pending work.
10. Prints row counts for the requested production tables.

## Failure Modes

Exit code `1` means no migration was intentionally applied. Typical causes are
a missing `DATABASE_URL`, a malformed URL, a local host without
`--allow-localhost`, a missing CLI dependency, a hostname typo, a rejected final
confirmation, or a dry run that found pending work.

Exit code `2` means Prisma failed or still reported pending work after deploy.
Alembic is not attempted when Prisma deploy itself fails.

Exit code `3` means Prisma already ran, but Alembic failed or still reported
pending work after `upgrade head`. Treat this as a partially migrated database.

## Recovery Playbook

If Prisma fails before Alembic starts, inspect the Prisma output and fix the
database connectivity, permissions, or migration file problem before retrying.
No Alembic migration has been attempted in that path.

If Prisma succeeds and Alembic fails, record the exact Alembic error and current
revision:

```bash
cd noosphere
alembic current
alembic history --indicate-current
```

If the Alembic migration must be reverted, use Alembic's explicit downgrade path
to the previous known-good revision:

```bash
cd noosphere
alembic downgrade <prev>
```

Prisma deploy mode has no symmetric downgrade. If a Prisma migration must be
reverted after it has applied in production, restore the database from the
pre-migration snapshot, then repair the migration history in version control
before trying again.
