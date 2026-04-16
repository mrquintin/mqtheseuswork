# Theseus Researcher API — FastAPI (SP07)
FROM python:3.12-slim-bookworm AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/noosphere \
    THESEUS_REPO_ROOT=/app

ARG THESEUS_GIT_SHA=unknown
ENV THESEUS_GIT_SHA=${THESEUS_GIT_SHA}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Engine (path-imported; not always a pip package)
COPY noosphere/ /app/noosphere/

# API service
COPY researcher_api/pyproject.toml researcher_api/README.md /app/researcher_api/
COPY researcher_api/researcher_api/ /app/researcher_api/researcher_api/
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir /app/researcher_api

# Method notes served by GET /v1/methods/{name}; SECURITY.md for GET /security
COPY docs/api-methods/ /app/docs/api-methods/
COPY docs/researcher-api/SECURITY.md /app/docs/researcher-api/SECURITY.md

EXPOSE 8080
CMD ["uvicorn", "researcher_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
