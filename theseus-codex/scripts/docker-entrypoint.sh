#!/bin/sh
#
# Entrypoint for the Theseus Codex container. Runs `prisma migrate deploy`
# against the Postgres URL supplied at runtime, then execs the Next.js
# standalone server.
#
# If DIRECT_URL is set (common when using Supabase/Neon behind a transaction
# pooler), migrations use it — some pooler configurations refuse DDL. The
# runtime app keeps using DATABASE_URL.

set -e

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] DATABASE_URL is not set; the app needs a Postgres URL." >&2
  echo "[entrypoint] Pass it with e.g. -e DATABASE_URL=postgresql://..." >&2
  exit 1
fi

# `prisma migrate deploy` is idempotent — it applies only unapplied migrations.
# On first boot against an empty database this materialises the schema.
echo "[entrypoint] Running prisma migrate deploy..."
if [ -n "${DIRECT_URL:-}" ]; then
  DATABASE_URL="$DIRECT_URL" npx --no-install prisma migrate deploy
else
  npx --no-install prisma migrate deploy
fi

echo "[entrypoint] Starting Next.js..."
exec "$@"
