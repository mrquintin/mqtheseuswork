# Release checklist - Forecasts

## Before merge to main
- [ ] All 18 prompts' tests pass.
- [ ] `cd theseus-codex && npm run build` passes.
- [ ] `cd theseus-codex && npm run test` passes.
- [ ] `pytest noosphere current_events_api` passes.
- [ ] Playwright smoke passes.
- [ ] All 8 invariants hold, including the default `FORECASTS_LIVE_TRADING_ENABLED=false` safety posture.

## Before deploy
- [ ] `FORECASTS_LIVE_TRADING_ENABLED=false` in production env (verify in Vercel dashboard + Docker compose env).
- [ ] Polymarket / Kalshi credentials NOT set in env (verify with `printenv | grep -E 'POLYMARKET|KALSHI'`).
- [ ] `FORECASTS_MAX_STAKE_USD=0` in production env.
- [ ] Status file path is on a persistent volume mount.

## First-week monitoring
- [ ] Daily: check `/v1/portfolio` for kill-switch state and calibration drift.
- [ ] Weekly: check Brier-over-time chart for trend.
- [ ] Monthly: read 5 random predictions end-to-end and confirm citations check.

## Live trading enablement (separate procedure)
- [ ] Founder reviews 30 days of paper trading with mean Brier <= 0.20.
- [ ] Founder funds Polymarket wallet / Kalshi account with capped amount.
- [ ] Founder sets the four env vars: `FORECASTS_LIVE_TRADING_ENABLED=true`, `FORECASTS_MAX_STAKE_USD=<n>`, `FORECASTS_MAX_DAILY_LOSS_USD=<n>`, `FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD=<n>`.
- [ ] Per-prediction authorize-live + per-bet confirm is the only path to actual fills.
