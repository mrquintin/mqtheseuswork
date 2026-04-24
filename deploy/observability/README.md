# Observability (SP06 targets)

Wire these in Kubernetes or your PaaS; nothing in this folder runs automatically.

| Signal | Tooling |
|--------|---------|
| Errors | [Sentry](https://sentry.io) — DSN via secret; enable Next + Node worker + Python SDK in Noosphere. |
| Metrics | Prometheus scrape `/api/health` (add) + worker queue depth gauge from Redis `LLEN`. |
| Dashboards | Grafana — import starter dashboards for HTTP p95, job latency, LLM token counters. |
| Logs | Loki / Datadog / CloudWatch — ship JSON logs from portal + structlog from Noosphere. |
| Traces | OpenTelemetry — instrument Next.js server, worker `processUpload`, and `python -m noosphere` subprocess spans. |

**Alert ideas:** Redis queue age &gt; 30 minutes; synthesis failure rate &gt; 5%; daily embedding spend vs budget.
