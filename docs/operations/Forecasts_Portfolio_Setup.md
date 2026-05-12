# Forecasts Portfolio Setup — Founder-Alpha

Date: 2026-05-12
Status: Active. This document is the canonical setup runbook for the
prediction-market portfolio side of Theseus / Noosphere. It is the
companion to `docs/operations/Forecasts_Scheduler.md` (which covers the
standing scheduler) and to `docs/architecture/Algorithmized_Decision_Making.md`
(which covers the decision contract).

The companion UI surface is at `/forecasts/setup` in Theseus Codex. That
page reads server configuration only — it never fetches, displays, or
stores key material — and reports the same readiness verdicts described
here.

## 0. The principle

Live capital deployment is a *staircase*, not a switch. Each step
removes one degree of "this might still misbehave":

```
exchange credentials configured
   ↓
scheduler ingesting & monitoring
   ↓
risk caps configured (max stake, max daily loss)
   ↓
FORECASTS_LIVE_TRADING_ENABLED=true
   ↓
per-prediction live authorization (operator UI)
   ↓
per-bet live confirmation     (operator UI)
   ↓
kill switch clear at submit time
   ↓
exchange order submitted
```

The setup page covers the first four steps. The operator console covers
the rest. **None of these steps auto-advances based on the previous
ones.**

## 1. Required environment variables

These are read by the API process and the scheduler container at
start. Restart both after changing them.

### 1.1 Polymarket

| Variable                    | Required | Purpose                                                            |
|-----------------------------|----------|--------------------------------------------------------------------|
| `POLYMARKET_PRIVATE_KEY`    | **yes**  | EVM private key for the Polymarket CLOB wallet (live submission).  |
| `POLYMARKET_CLOB_BASE`      | no       | Override the CLOB base URL (default `https://clob.polymarket.com`).|
| `POLYMARKET_CHAIN_ID`       | no       | Defaults to `137` (Polygon).                                       |
| `POLYMARKET_SIGNATURE_TYPE` | no       | Polymarket SDK signature type, defaults to `0`.                    |
| `POLYMARKET_FUNDER_ADDRESS` | no       | Set if trading from a proxy wallet (Polymarket "funder" pattern).  |
| `POLYMARKET_DEFAULT_TICK_SIZE` | no    | Defaults to `0.01`.                                                |
| `POLYMARKET_DEFAULT_NEG_RISK`  | no    | `true`/`false`; controls neg-risk markets default flag.            |
| `FORECASTS_POLYMARKET_CATEGORIES` | no | Comma-separated category allow-list for ingestion.                  |

The private key controls actual funds. Treat it as such — see §5.

### 1.2 Kalshi

| Variable                    | Required | Purpose                                                              |
|-----------------------------|----------|----------------------------------------------------------------------|
| `KALSHI_API_KEY_ID`         | **yes**  | Kalshi-issued API key id (the public part).                          |
| `KALSHI_API_PRIVATE_KEY`    | **yes**  | RSA PEM body. One-line env files: encode newlines as literal `\n`.   |
| `KALSHI_PRIVATE_KEY_PEM`    | (alt)    | Legacy name for the same field — accepted as a fallback.             |
| `KALSHI_API_BASE`           | no       | Override base URL (default `https://api.elections.kalshi.com/...`).  |
| `FORECASTS_KALSHI_CATEGORIES` | no     | Comma-separated category allow-list for ingestion.                    |

The Kalshi PEM body is sensitive. Never paste it into chat, screenshots,
support threads, or shared docs.

### 1.3 Risk caps and live flag

| Variable                              | Required for live | Purpose                                              |
|---------------------------------------|-------------------|------------------------------------------------------|
| `FORECASTS_LIVE_TRADING_ENABLED`      | yes (`true`)      | Master gate. Without this, the live path refuses.    |
| `FORECASTS_MAX_STAKE_USD`             | yes (> 0)         | Per-bet stake ceiling enforced by safety gates.      |
| `FORECASTS_MAX_DAILY_LOSS_USD`        | yes (> 0)         | Daily loss ceiling enforced by safety gates.         |
| `FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD` | no            | Auto-engages the kill switch at this daily loss.     |

`FORECASTS_LIVE_TRADING_ENABLED` is intentionally last. Set risk caps
*before* flipping it.

### 1.4 Scheduler & API plumbing

| Variable                              | Purpose                                                                 |
|---------------------------------------|-------------------------------------------------------------------------|
| `FORECASTS_INGEST_ORG_ID`             | Organization id for ingested markets and predictions.                   |
| `FORECASTS_STATUS_PATH`               | Override scheduler status file location.                                |
| `FORECASTS_STATUS_MAX_AGE_SECONDS`    | Freshness threshold for "Monitoring active" (default `1800`).           |
| `FORECASTS_OPERATOR_SECRET`           | HMAC shared secret between Codex and the operator API.                  |
| `FORECASTS_OPERATOR_CSRF_TOKEN`       | Optional pinned CSRF token (defaults to a founder-scoped value).        |
| `FORECASTS_API_URL` / `CURRENTS_API_URL` | Base URL of the FastAPI service the Codex proxy talks to.            |

## 2. Local development

1. Copy the variables above into a `.env` file at the repo root.
   `.env` is gitignored — `git status` should never list it.
2. Start the API: `uvicorn current_events_api.app:create_app --factory --reload`.
3. Start the scheduler:
   `NOOSPHERE_DATA_DIR=$PWD/noosphere_data ./scripts/run-forecast-scheduler.sh loop`.
4. Open `http://localhost:3000/forecasts/setup` in Theseus Codex.
   All three readiness tiles should report what the server actually sees.

The setup page in dev will say "NOT READY" for live orders until you
fill in the risk caps and set `FORECASTS_LIVE_TRADING_ENABLED=true`.
That is correct.

## 3. Production deployment

Theseus deployment uses Docker Compose by default
(`docker-compose.yml`). The `api` and `scheduler` services both read
their environment from the host. Where to place keys depends on your
operator:

- **Self-hosted / single-host**: place them in `/etc/theseus/.env`
  (root-owned, `0600`) and reference from compose via `env_file:`.
- **Managed secret store** (recommended for multi-host): mount the
  secret into the container at start using your platform's secret
  manager (AWS Secrets Manager, GCP Secret Manager, 1Password Connect,
  Doppler, etc.). Do not bake keys into the image.
- **CI builders**: never. CI does not need live keys; the build image
  must not contain `POLYMARKET_PRIVATE_KEY` or `KALSHI_API_PRIVATE_KEY`.

Restart the `api` and `scheduler` services after rotating any value.

## 4. Verifying readiness

The `/forecasts/setup` page exposes three readiness tiles. Their truth
table is intentionally narrow:

| Tile                          | True when                                                                                                                       |
|-------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| Monitoring active             | Scheduler status file exists and `last_ingest_ts` is within `FORECASTS_STATUS_MAX_AGE_SECONDS`.                                |
| Ready for live candidates     | Monitoring active AND at least one exchange configured AND kill switch clear.                                                  |
| Ready for live orders         | Ready for live candidates AND `FORECASTS_LIVE_TRADING_ENABLED=true` AND `FORECASTS_MAX_STAKE_USD>0` AND `FORECASTS_MAX_DAILY_LOSS_USD>0`. |

"Ready for live orders" does **not** mean the next bet will execute —
per-prediction authorization and per-bet operator confirmation still
gate every submission, and the kill switch can engage between this page
load and the next gate evaluation.

To verify connectivity end-to-end you can:

1. Watch the scheduler ingest a market batch in logs
   (`forecast_polymarket_ingest_ok` / `forecast_kalshi_ingest_ok`).
2. Confirm `last_ingest_ts` advances on the setup page.
3. Authorize a single low-stake prediction via the operator console and
   confirm a paper-mode bet from end to end first; only then flip live
   trading on.

## 5. What not to do with keys

- Do not paste a private key into a public Slack channel, an email
  thread, a screenshot, a Loom recording, or a GitHub issue. If a key
  is ever exposed by accident, rotate it on the exchange before doing
  anything else.
- Do not commit a key to any branch, including a private one. `.env`
  must stay gitignored.
- Do not store keys in the Theseus Codex database. The application is
  designed around environment-only secrets; there is no encrypted
  secrets table and adding one is out of scope for founder-alpha.
- Do not echo `$POLYMARKET_PRIVATE_KEY` in a shell with shell history
  enabled. Use `set +o history` or a secrets manager CLI.
- Do not log a key — the codebase intentionally never logs key
  material, and the setup-status endpoint never returns key material.
  Do not introduce code that breaks this rule.

## 6. Adding a credentials ingestion endpoint (deferred)

Founder-alpha intentionally has no in-app credential entry form. If a
future iteration wants one, the rule is non-negotiable:

- Keys must be encrypted before write — envelope encryption with a
  managed KMS key (AWS KMS, GCP KMS, or HashiCorp Vault transit), not
  application-layer secrets in the DB.
- Decryption happens only inside the live-trading process, only for the
  duration of the request, and is never logged.
- The endpoint must be founder-only and CSRF-protected, on the same
  HMAC channel as the rest of the operator API.

Until that is built and reviewed, the only supported path is
environment variables in the deployment environment.

## 7. References

- `noosphere/noosphere/forecasts/safety.py` — gate context, kill
  switch, `current_trading_mode()`.
- `noosphere/noosphere/forecasts/config.py` — `PolymarketConfig`,
  `KalshiConfig` env loaders.
- `noosphere/noosphere/forecasts/status.py` — scheduler status file
  format and freshness contract.
- `current_events_api/current_events_api/routes/operator.py` —
  `/v1/operator/setup-status` (this page's data source).
- `theseus-codex/src/app/(authed)/forecasts/setup/page.tsx` — the UI.
- `docs/operations/Forecasts_Scheduler.md` — scheduler lifecycle.
- `docs/operations/Forecasts_Founder_Alpha_Runbook.md` — end-to-end
  founder runbook (paper → live, kill switch, stop-all).
- `docs/architecture/Algorithmized_Decision_Making.md` — the decision
  contract whose live-output side this setup gates.
