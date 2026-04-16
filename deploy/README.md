# Cloud / Kubernetes layout (SP06 scaffold)

- **Docker** — `deploy/docker/founder-portal/Dockerfile` (Next standalone), `deploy/docker/ingest-worker/Dockerfile` (Node + Python for `processUpload`).
- **Compose** — `deploy/compose/docker-compose.yml` for Postgres, Redis, MinIO locally.
- **Helm** — `deploy/helm/theseus/` skeleton (wire secrets, ingress, and migrations in your cluster).
- **RLS** — `deploy/sql/postgres_rls_example.sql` documents row-level security once Prisma uses PostgreSQL.

Build portal image from repo root:

```bash
docker build -f deploy/docker/founder-portal/Dockerfile -t theseus/founder-portal:dev .
docker build -f deploy/docker/ingest-worker/Dockerfile -t theseus/ingest-worker:dev .
```

See `docs/Operations_Manual.md` for cloud operations, backups, and tenant export.
