# Forecasts scheduler — hosting, intervals, and operator surface

This document covers how the standing Forecasts scheduler is meant to be
hosted, what each sub-loop does, what readiness signals to watch, and
which environment variables exist for tuning.

The scheduler is the component that turns "we have a database with
market mirrors in it" into "the system is monitoring markets and
applying Noosphere's metrics on its own." It is not a one-shot script:
it owns its own cadence and runs forever.

## Sub-loops at a glance

| Loop                  | Default interval  | Env var to tune                            | Purpose                                                                                                                |
| --------------------- | ----------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `ingest`              | 900 s (15 min)    | `FORECASTS_INGEST_INTERVAL_S`              | Pull Polymarket + Kalshi markets and refresh prices into the mirror.                                                   |
| `generate`            | 600 s (10 min)    | `FORECASTS_GENERATE_INTERVAL_S`            | LLM-backed forecast generation for markets without a recent published prediction.                                      |
| `metric_scan`         | 420 s (7 min)     | `FORECASTS_METRIC_SCAN_INTERVAL_S`         | Re-apply Noosphere's decision metrics to recent predictions against the *current* mirrored price; emit paper-bet candidates and log live-candidate ids. Does NOT submit live orders. |
| `resolve`             | 300 s (5 min)     | `FORECASTS_RESOLUTION_POLL_INTERVAL_S`     | Poll exchanges for settlement outcomes on open markets and append `ForecastResolution` rows.                           |
| `paper_drain`         | 60 s              | `FORECASTS_PAPER_BET_DRAIN_INTERVAL_S`     | Settle paper bets attached to resolved markets and update the paper balance.                                            |
| `live_orders`         | 60 s              | `FORECASTS_LIVE_ORDER_POLL_INTERVAL_S`     | Poll exchange status for `SUBMITTED` live bets. No-op when `FORECASTS_LIVE_TRADING_ENABLED` is not `true`.              |
| `articles`            | 3600 s (1 h)      | `FORECASTS_ARTICLE_INTERVAL_S`             | Dispatch triggered Currents articles when their gates fire.                                                            |
| `public_calibration`  | 86 400 s (1 d)    | `FORECASTS_PUBLIC_CALIBRATION_INTERVAL_S`  | Rebuild the public calibration manifest and (best-effort) revalidate the public page.                                  |
| `recalibration`       | 604 800 s (1 wk)  | `FORECASTS_RECALIBRATION_INTERVAL_S`       | Fit and persist per-domain isotonic recalibration models.                                                              |

Realistic-interval guidance:

- Ingest / price refresh: **5–15 min**. Polymarket and Kalshi will rate
  limit at higher cadences; 15 min is the operational floor that still
  catches relevant price moves.
- Metric scan: **5–10 min after refresh**. Picks up new edges as soon as
  the mirror has new prices, without churning through the whole
  prediction history every minute.
- Live-order / live-candidate polling: **30–120 s** when live trading is
  enabled. The `live_orders` loop is a no-op when live trading is off,
  so leaving it at 60 s is cheap.
- Resolution polling: **5–15 min**. Most resolutions are not
  latency-sensitive — a settlement that lands at 12:00 UTC can be
  observed at 12:15 UTC without harm.
- Calibration / public reports: **daily** for `public_calibration`,
  **weekly** for `recalibration`. They are expensive and the underlying
  signal does not move faster than the cadence.

## Status surface (what `/ops` and the operator page can show)

The scheduler writes an atomic JSON file every tick (path: see
`FORECASTS_STATUS_PATH`, default `/var/lib/theseus/forecasts_status.json`
or `$NOOSPHERE_DATA_DIR/forecasts_status.json`). Fields exposed:

- `last_ingest_ts` — last successful market refresh.
- `last_generate_ts` — last generate tick.
- `last_metric_scan_ts` — last decision-metric scan.
- `last_candidate_ts` — last time the scan produced any candidate
  (paper or live).
- `last_paper_bet_ts` — last paper bet that filled.
- `last_live_candidate_ts` — last prediction whose edge crossed the
  live threshold (advisory only; not auto-submitted).
- `last_live_submission_ts` — last operator-authorized live order that
  hit the exchange (read directly from the `ForecastBet` table so it
  survives scheduler restarts).
- `last_live_order_poll_ts` — last live-order polling tick.
- `last_resolve_ts` — last resolution-polling tick.
- `last_error` / `last_error_loop` / `last_error_ts` — first error from
  the most recent failing tick, plus which loop fired and when.
- `paper_balance_usd`, `live_balance_usd`, `live_trading_enabled`,
  `open_markets`, `predictions_this_hour`, `kill_switch_engaged` /
  `kill_switch_reason`.

The Codex `/ops` page and the forecast operator page can render this
payload directly; the FastAPI `forecasts_readyz_contract` already
returns it via `readyz`.

## CLI entry points

All commands are also exposed via the typer CLI as `noosphere forecasts …`.

```sh
# Standing scheduler (production)
python -m noosphere.forecasts.scheduler run

# One pass through every sub-loop, then exit (cron-friendly)
python -m noosphere.forecasts.scheduler tick
python -m noosphere.forecasts.scheduler once         # alias

# Limit a tick to specific sub-loops
python -m noosphere.forecasts.scheduler tick --loop ingest --loop metric_scan

# Decision-metric scan only (debug / one-off catch-up)
python -m noosphere.forecasts.scheduler metric-scan

# Refresh forecasts_status.json without running any tick
python -m noosphere.forecasts.scheduler status-only
```

The `scripts/run-forecast-scheduler.sh` wrapper is the recommended
entry point — it picks the right subcommand for each mode and `exec`s
into the Python module.

## Hosting modes

### Local dev

```sh
export NOOSPHERE_DATA_DIR=$PWD/noosphere_data
./scripts/run-forecast-scheduler.sh loop
```

Or, for one-off iteration:

```sh
./scripts/run-forecast-scheduler.sh once          # full pass
./scripts/run-forecast-scheduler.sh metric-scan   # just the metric scan
```

### Docker (always-on, recommended for production)

`docker-compose.yml` already includes a `scheduler` service backed by
`Dockerfile.scheduler` that runs the standing loop. Flip it on with:

```sh
export FORECASTS_SCHEDULER_ENABLED=true
docker compose up -d scheduler
```

The compose healthcheck reads `forecasts_status.json` and fails if the
file is older than `FORECASTS_STATUS_MAX_AGE_SECONDS` (default 1800 s).
This catches dead schedulers without needing a separate watchdog.

### GitHub Actions sweep (fallback only)

There is no Forecasts-specific Actions sweep today. The existing
`noosphere-process-uploads.yml` workflow handles upload ingest, not
market monitoring. If you want a cron-style fallback (e.g. while the
scheduler container is being moved between hosts), add a workflow that
runs every 10 minutes:

```yaml
schedule:
  - cron: "*/10 * * * *"
jobs:
  forecasts-tick:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python -m noosphere.forecasts.scheduler tick
        env:
          DATABASE_URL: ${{ secrets.CODEX_DATABASE_URL }}
          FORECASTS_INGEST_ORG_ID: ${{ secrets.FORECASTS_INGEST_ORG_ID }}
```

This is a fallback only: market monitoring on a 10-minute floor will
miss intra-window candidates. Prefer the always-on container.

### Bare-metal / systemd cron

If neither Docker nor GitHub Actions fit:

```cron
# Run a tick every 5 minutes
*/5 * * * * cd /opt/theseus && ./scripts/run-forecast-scheduler.sh once >>/var/log/theseus/forecasts.log 2>&1
```

For continuous monitoring, prefer a systemd service that runs
`run-forecast-scheduler.sh loop` and restarts on failure.

## Safety constraints (must hold across hosting modes)

1. **No automatic live orders.** The scheduler will never call
   `submit_live_bet`. `last_live_candidate_ts` is advisory; an operator
   must explicitly authorize each live order via the operator UI/CLI,
   which then sets `live_authorized_at` and triggers
   `live_bet_engine.submit_live_bet` under the prompt-17 safety gates.
2. **Kill switch wins.** Engaging the kill switch
   (`ForecastPortfolioState.kill_switch_engaged = true`) immediately
   skips `generate`, `metric_scan`, and forces the readiness contract
   to 503. `ingest`, `resolve`, and `paper_drain` continue so the
   mirror stays current and resolved markets still settle.
3. **No credentials in logs or status files.** Exchange keys are read
   from env at request time; the status payload is whitelist-derived
   (see `_status_payload`) and never echoes env values.
4. **No new paid services required.** The standing loop runs inside
   the existing `scheduler` container — no extra hosting cost beyond
   what was already provisioned for Currents/Articles.

## Verification checklist

When you change scheduler intervals or add a loop:

```sh
# Focused tests
PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_forecasts_scheduler.py \
                   noosphere/tests/test_forecast_scheduler_decision_metrics.py

# Smoke a tick against a test sqlite store
NOOSPHERE_DATA_DIR=/tmp/forecasts-smoke python -m noosphere.forecasts.scheduler tick

# Whitespace hygiene
git diff --check
```
