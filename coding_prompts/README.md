# Round 11 — Live trading activation

Five prompts that turn the Round 10 Forecasts platform from "paper-only simulation" into a system that can place real money against real markets, with multi-stage human-in-the-loop gates and observability.

**No prompt in this round contains, accepts, or echoes any credential.** All credentials live in `.env.live` (created from `.env.live.template` at the repo root). The runner verifies that file is populated before starting; the prompts reference env-var names only.

Runnable end-to-end via:

```bash
./run_prompts.sh
```

with one required precondition: `.env.live` is populated. Without it, the runner aborts before invoking Codex with a clear list of missing keys.

## Map

| # | File | Wave | Summary |
|---|---|---|---|
| 01 | `01_credential_validator.txt` | A — Pre-flight | `validate_live_credentials.py`: read-only health check against Postgres, Anthropic, Polymarket Gamma, Kalshi (live + demo). Never prints secrets. Redaction tests prove it |
| 02 | `02_production_database_migration.txt` | A — Pre-flight | `migrate_production.sh`: refuses localhost without flag; requires hostname-confirm typing; runs prisma migrate deploy + alembic upgrade |
| 03 | `03_demo_environment_integration.txt` | B — Verify | Real-API integration test against Kalshi demo + Polymarket signature round-trip; pytest-marked `live_demo` (off by default); place + cancel a 1¢ test order |
| 04 | `04_operator_rehearsal_doc_and_smoke.txt` | B — Verify | `OPERATOR_REHEARSAL.md`: 9-stage walkthrough for the first live bet; kill-switch dry run; first 10 settled live bets; `LIVE_BET_LOG.md` operator journal template |
| 05 | `05_deployment_and_observability.txt` | C — Operate | Vercel config; production docker-compose overlay + systemd units; Forecasts Prometheus metrics; 5 alert rules; minimum-viable Grafana dashboard |

## Execution

```bash
# All 5:
./run_prompts.sh

# Skip a prompt you've already completed:
./run_prompts.sh --from 3

# Only one:
./run_prompts.sh --only 04

# Plan without running:
./run_prompts.sh --dry-run
```

## What this round does NOT do

- It does not auto-enable live trading. `FORECASTS_LIVE_TRADING_ENABLED=false` remains the default in `.env.live.template`. The operator flips it manually after completing the rehearsal.
- It does not place any real-money order. The demo integration test in prompt 03 places a 1¢ order against Kalshi *demo*. Real orders happen only via the operator console, manually, one at a time.
- It does not bypass any of the eight gates from Round 10. The rehearsal exercises them; it doesn't disable them.

## Precondition: `.env.live`

Before running this round:
1. Copy `.env.live.template` to `.env.live`. Verify `.gitignore` lists `.env.live` (the Round 11 patch ensures it does — but check anyway).
2. Fill in every value. The chat that produced these prompts deliberately did not accept credential values; they remain in your custody at all times.
3. Run a sanity check that the file parses: `grep -c '=' .env.live` should return ~22 (one per env var). Empty values are valid for paper-only operation; the validator (prompt 01) names which fields are required vs. optional.

## What you'll have at the end of Round 11

- A credential validator runnable on demand.
- A migration runner that won't deploy to the wrong DB by accident.
- An integration test against real APIs in demo mode.
- A documented, gate-by-gate rehearsal procedure for the first live bet.
- Production deployment scripts.
- Observability that pages on kill-switch engagement, scheduler stalls, calibration drift, exchange-error streaks, and budget exhaustion.

After completing the rehearsal documented by prompt 04, the system is operationally ready to take a first $5 live bet. Scaling up beyond that is a separate decision based on the calibration evidence you accumulate.

## Architecture (unchanged from Round 10)

The platform's structure is fixed by Round 10. Round 11 only adds:
- Pre-flight scripts (validator, migrator).
- Demo-mode tests.
- Documentation.
- Deployment + metrics + alerts.

No new tables. No new routes. No new LLM calls.

## If something goes wrong

- A prompt fails → log lives in `.codex_runs/`; the runner prints the resume command (`--from N`).
- The runner halts with a `.env.live` complaint → fill in the missing fields and re-run.
- The credential validator reports red on a service → fix that service's env vars; do not proceed to live trading.
- The demo integration test times out → check Kalshi's demo env status; do not proceed until it passes.
- The rehearsal hits a stop condition → engage the kill switch, follow OPERATOR_REHEARSAL.md §9.
