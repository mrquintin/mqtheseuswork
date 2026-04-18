# Theseus Codex — Next.js standalone server backed by an external Postgres.
#
# History note: an earlier version of this file bundled SQLite into the image
# (`prisma db push` → /tmp/seed.db, VOLUME /app/data, DATABASE_URL=file:...).
# That stopped working when the Prisma schema was switched to
# `provider = "postgresql"` for Vercel + Supabase — `prisma db push` now
# refuses to write a Postgres schema to a SQLite URL, so every Docker build
# broke. This version expects Postgres to be supplied at runtime via
# `DATABASE_URL` (and optionally `DIRECT_URL` for migrations) and does not
# materialize a database inside the image.

# ── Stage 1: install dependencies (incl. devDeps for build) ──────────────────
FROM node:20-alpine AS deps
WORKDIR /app
# libc6-compat is still needed for Next.js's SWC binary; native build tools
# for better-sqlite3 are no longer required since we use @prisma/adapter-pg.
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

# ── Stage 2: build Next.js + generate Prisma client ──────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# Generate the Prisma client against the Postgres schema. No live DB needed.
RUN npx prisma generate
RUN npm run build

# ── Stage 3: production runner ───────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN apk add --no-cache libc6-compat \
    && addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
# Ship the schema and migrations so the entrypoint can run `prisma migrate deploy`.
COPY --from=builder --chown=nextjs:nodejs /app/prisma ./prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/@prisma ./node_modules/@prisma
# Prisma CLI is needed at runtime for `migrate deploy`; it's already in node_modules
# because we install with devDependencies above and Next standalone carries the
# runtime subset — but Prisma itself is declared as a regular dependency so it's
# present in `node_modules` carried over.
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/prisma ./node_modules/prisma

COPY --chown=nextjs:nodejs scripts/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
# DATABASE_URL (and optionally DIRECT_URL) must be provided at runtime, e.g.:
#   docker run -e DATABASE_URL=postgresql://user:pass@host:5432/theseus theseus/theseus-codex
# See theseus-codex/.env.example for the expected Postgres URL shape.

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["node", "server.js"]
