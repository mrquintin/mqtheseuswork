# Ingest worker: Node (Prisma + processUpload) + Python (Noosphere CLI)
# Build from monorepo root: docker build -f deploy/docker/ingest-worker/Dockerfile .
FROM node:22-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
  && rm -rf /var/lib/apt/lists/*
COPY noosphere /opt/noosphere
WORKDIR /opt/noosphere
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt || pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY founder-portal/package.json founder-portal/package-lock.json* ./
RUN npm ci --legacy-peer-deps
COPY founder-portal/ ./
RUN npx prisma generate

ENV NOOSPHERE_SRC_ROOT=/opt/noosphere
ENV PYTHONPATH=/opt/noosphere
ENV NOOSPHERE_PYTHON=python3

CMD ["npm", "run", "worker:ingest"]
