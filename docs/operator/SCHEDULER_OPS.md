# Forecasts scheduler — operator runbook

The Forecasts scheduler runs the standing ingest → generate → metric-scan
→ resolve → paper-drain → live-orders → articles → public-calibration →
recalibration pipeline. The entrypoint is
`python -m noosphere.forecasts.scheduler run`, and it expects to be
supervised by something that re-launches it on exit (systemd, k8s
`restartPolicy: Always`, Procfile, etc.).

The scheduler is designed to **run continuously for 24h+ without
intervention**. If it cannot, that is a bug — restart-the-process is
not a substitute for a fix.

## Run a scheduler

```bash
python -m noosphere.forecasts.scheduler run         # standing loop
python -m noosphere.forecasts.scheduler once        # one full pass
python -m noosphere.forecasts.scheduler tick --loop ingest --loop generate
python -m noosphere.forecasts.scheduler metric-scan # decision-metric only
python -m noosphere.forecasts.scheduler status-only # refresh status file
```

Use `tick --loop NAME` (repeatable) to fire a single sub-loop for
operator debugging. Valid loop names: `ingest`, `generate`,
`metric_scan`, `resolve`, `paper_drain`, `live_orders`, `articles`,
`public_calibration`, `recalibration`.

## Environment

The scheduler is fully env-driven. The variables operators most often
touch:

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` / `THESEUS_DATABASE_URL` | settings.database_url | Required in prod. |
| `NOOSPHERE_DATA_DIR` | unset | If set, status/budget files default under here. |
| `FORECASTS_STATUS_PATH` | `/var/lib/theseus/forecasts_status.json` | On-disk heartbeat/status. |
| `FORECASTS_BUDGET_PATH` | `/var/lib/theseus/forecasts_budget.json` | Hourly token budget. |
| `FORECASTS_INGEST_INTERVAL_S` | 900 | Polymarket + Kalshi pull. |
| `FORECASTS_GENERATE_INTERVAL_S` | 600 | Forecast generation tick. |
| `FORECASTS_METRIC_SCAN_INTERVAL_S` | 420 | Decision-metric / paper-bet candidate scan. |
| `FORECASTS_RESOLUTION_POLL_INTERVAL_S` | 300 | Resolution tracker. |
| `FORECASTS_PAPER_BET_DRAIN_INTERVAL_S` | 60 | Settle paper bets on resolved markets. |
| `FORECASTS_LIVE_ORDER_POLL_INTERVAL_S` | 60 | Refresh `SUBMITTED` live bets. |
| `FORECASTS_ARTICLE_INTERVAL_S` | 3600 | Article dispatch trigger evaluation. |
| `FORECASTS_PUBLIC_CALIBRATION_INTERVAL_S` | 86400 | Nightly calibration manifest. |
| `FORECASTS_RECALIBRATION_INTERVAL_S` | 604800 | Weekly per-domain isotonic refit. |
| `FORECASTS_MAX_PREDICTIONS_PER_CYCLE` | 8 | Cap per generate tick. |
| `FORECASTS_LIVE_TRADING_ENABLED` | unset/false | `true` enables live-order polling; the scheduler still never submits. |
| `FORECASTS_ORG_ID` / `FORECASTS_INGEST_ORG_ID` | unset | Single-tenant scope. |
| `FORECASTS_LOG_LEVEL` | INFO | Falls through to `LOG_LEVEL`. |

Every log line is structured JSON, one event per line. Do not pipe
`print()` over the logs — the scheduler uses
`noosphere.observability.get_logger` only.

## Reading `forecasts_status.json`

The status file is the canonical operator surface. It is written
atomically: each update lands in a temp file in the same directory
and is then `os.replace`-d onto the target. Readers (the
`/readyz` route, operator scripts) will never observe a partially
written file.

Key fields:

| Field | Source | Means |
| --- | --- | --- |
| `last_tick_ts` | heartbeat task | **Liveness signal.** Advances every `~min(intervals)/2` seconds (capped to 50 ms – 2 s) independent of any sub-loop. If this stops advancing the scheduler is wedged. |
| `last_ingest_ts` | ingest loop | Last successful exchange ingest. Stale ⇒ Polymarket / Kalshi connectivity issue. |
| `last_generate_ts` | generate loop | Last generate-forecast tick (may be a no-op if no open markets). |
| `last_metric_scan_ts` | metric scan loop | Last decision-metric pass. |
| `last_resolve_ts` | resolve loop | Last resolution-tracker poll. |
| `last_paper_bet_ts` | metric scan loop | Last paper bet placed by the scheduler. |
| `last_live_candidate_ts` | metric scan loop | Last edge-> live-threshold candidate detected (info only). |
| `last_live_submission_ts` | DB | Last operator-driven live submission (the scheduler never submits). |
| `last_article_ts` | articles loop | Last article dispatch tick. |
| `last_public_calibration_ts` / `_hash` | public-calibration loop | Last published calibration manifest. |
| `last_recalibration_ts` / `_models_written` | recalibration loop | Last weekly isotonic refit. |
| `last_error` / `_loop` / `_ts` | any loop | Most recent error and which sub-loop raised it. |
| `last_timeout_loop` / `_ts` | any loop | Most recent tick that exceeded `10 × interval`. |
| `shutdown_at` | shutdown | Set on clean exit. Presence ⇒ the scheduler was last drained gracefully. |
| `kill_switch_engaged` / `_reason` | portfolio state | If true the generate + metric-scan loops skip; ingest/resolve continue. |
| `paper_balance_usd` / `live_balance_usd` / `live_trading_enabled` | portfolio | Status panel. |
| `open_markets` / `predictions_this_hour` | DB rollups | Sanity counters. |

`/readyz` (in `current_events_api/current_events_api/routes/forecasts.py`)
currently keys off `last_ingest_ts` with a `2 × FORECASTS_INGEST_INTERVAL_S`
window. Treat that as a coarse ingest-staleness signal; for true
liveness watch `last_tick_ts` instead.

## What a stuck scheduler looks like

| Symptom | Diagnosis |
| --- | --- |
| `last_tick_ts` stops advancing for more than ~5 s in prod | The asyncio event loop is wedged. Almost certainly a sync C extension call or an unawaited blocking I/O. Capture a thread dump (`py-spy dump`) and restart. |
| `last_tick_ts` advances; specific `last_X_ts` does not | That sub-loop is stuck in its runner. Look for a matching `forecasts_scheduler_tick_timeout` event — the per-tick timeout (10 × interval) will eventually log and skip. If the runner is reproducibly slow, raise the interval; do not raise the timeout. |
| `last_error_ts` keeps advancing with the same loop / error | The sub-loop is crashing every tick. Treat as a bug, not a transient. |
| `last_timeout_loop` is populated | Most recent tick exceeded 10 × interval. Inspect the matching `forecasts_scheduler_tick_timeout` log line for the loop name and elapsed time. |
| `shutdown_at` set on a process that is supposedly running | The process exited cleanly, the supervisor has not restarted yet. Check the supervisor. |
| `/readyz` reports `forecasts_ingest_stuck` but `last_tick_ts` is fresh | Ingest is genuinely behind (slow Polymarket Gamma, network blip). The scheduler itself is fine; the route's window is intentionally conservative. |
| `forecasts_scheduler_status_lock_slow` warning | Lock wait > 1 s. Indicates one of the sub-loops is doing slow DB work in `_status_payload`. Check Postgres health. |
| `forecasts_scheduler_drain_timeout` warning at shutdown | A sub-loop did not return inside the 30 s grace window. The scheduler force-cancels and exits. Investigate which runner was still in-flight at the time. |

## Recovery procedure

1. **First, look at `forecasts_status.json`.** If `shutdown_at` is set
   the process exited cleanly — restart it (or let the supervisor do
   so). No state cleanup is needed: the budget file persists tokens
   used in the current hour, and atomic writes guarantee it is
   internally consistent.
2. **If `last_tick_ts` is stale but the process is alive,** the
   asyncio loop is wedged. `kill -SIGTERM` first (it has 30 s to
   drain). If it does not exit, `kill -SIGKILL` and restart. Open a
   bug.
3. **If `last_error_ts` is hammering with the same `last_error`,**
   stop the scheduler, fix the bug, redeploy. Do not paper over with
   retries.
4. **If the budget file is missing or unreadable on boot,** the
   scheduler will recreate it with a fresh hourly window. You will
   lose any in-progress budget tracking for the current hour. There
   is no recovery needed beyond restarting.

## Hardening that landed with the 2026-05-13 flakiness fix

- **Heartbeat task** — `last_tick_ts` advances independently of any
  sub-loop. See `_heartbeat_loop` in
  `noosphere/noosphere/forecasts/scheduler.py`.
- **Per-tick `asyncio.wait_for`** — every sub-loop iteration is
  wrapped with a `10 × interval` timeout (floor 10 s). Timeouts
  produce a `forecasts_scheduler_tick_timeout` event and `last_timeout_*`
  fields.
- **Atomic status writes** — temp file + `os.fsync` + `os.replace`,
  always in the same directory as the target so the rename is atomic.
  Built into `noosphere.forecasts.status.write_status`.
- **In-order status payload** — the DB read that builds the payload
  now runs inside the `status_lock`, so two sub-loops finishing
  near-simultaneously cannot land an older payload after a newer one.
- **Final status row on shutdown** — `run_forever`'s `finally` block
  drains for ≤ 30 s, sets `state.shutdown_at`, persists one last
  status row, then saves the budget. The presence of `shutdown_at`
  is the operator-visible signal of clean shutdown.

## Production-checklist

- `forecasts_status.json` and `forecasts_budget.json` must be in a
  durable volume (not ephemeral container storage) so a restart
  preserves the hourly budget window and operator visibility.
- The supervisor must send `SIGTERM` (not `SIGKILL`) on stop. The
  scheduler has 30 s of drain logic that you only get with SIGTERM.
- Alert on either of:
  - `last_tick_ts` older than 5 s, or
  - `last_ingest_ts` older than `4 × FORECASTS_INGEST_INTERVAL_S`.
  The first catches a wedged loop; the second catches sustained
  exchange-side outages.
