# Theseus Codex — Next.js standalone server with SQLite (multi-stage)
#
# DB initialization strategy: this schema has no `prisma/migrations` directory,
# so `prisma migrate deploy` is not applicable. Instead, the builder stage runs
# `prisma db push` against /tmp/seed.db to materialize the schema, then the
# runner copies that file to /app/seed.db. The entrypoint seeds the volume on
# first boot. This keeps the runtime image free of the Prisma CLI.

# ── Stage 1: install dependencies (incl. devDeps for build) ──────────────────
FROM node:20-alpine AS deps
WORKDIR /app
# Build tools for native modules (better-sqlite3)
RUN apk add --no-cache python3 make g++ libc6-compat
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

# ── Stage 2: build Next.js + generate Prisma client + seed DB ────────────────
FROM node:20-alpine AS builder
WORKDIR /app
RUN apk add --no-cache python3 make g++ libc6-compat
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npx prisma generate
RUN npm run build
# Materialize a blank schema-applied SQLite DB used as the first-boot seed.
RUN DATABASE_URL="file:/tmp/seed.db" npx prisma db push --skip-generate --accept-data-loss

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
COPY --from=builder --chown=nextjs:nodejs /app/prisma ./prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/@prisma ./node_modules/@prisma
COPY --from=builder --chown=nextjs:nodejs /tmp/seed.db /app/seed.db
COPY --chown=nextjs:nodejs scripts/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# SQLite database lives on a named volume so it survives container restarts.
RUN mkdir -p /app/data && chown nextjs:nodejs /app/data
VOLUME ["/app/data"]

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV DATABASE_URL="file:/app/data/theseus-codex.db"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["node", "server.js"]
