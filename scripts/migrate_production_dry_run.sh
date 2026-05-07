#!/usr/bin/env bash
# Print the guarded Prisma + Alembic production migration plan without running
# prisma migrate deploy or alembic upgrade head.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/migrate_production.sh" --dry-run "$@"
