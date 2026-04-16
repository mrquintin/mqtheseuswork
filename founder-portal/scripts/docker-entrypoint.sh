#!/bin/sh
set -e

# On first boot, seed the SQLite database from the schema-applied template
# baked into the image. Subsequent boots leave the volume's DB untouched.
if [ ! -f /app/data/founder-portal.db ]; then
  cp /app/seed.db /app/data/founder-portal.db
fi

exec "$@"
