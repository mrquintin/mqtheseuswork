# Resolution backfill — dry-run

- run stamp (UTC): `20260514T172931Z`
- generated_at: 2026-05-14T17:29:31Z
- driver: `noosphere/scripts/run_resolution_backfill.sh`
- backfill module: `noosphere/noosphere/forecasts/resolution_backfill.py`

## A. Pre-flight

- verdict: **GATED**
- resolution_backfill imports cleanly: yes
- Polymarket config present: yes (gamma_base=https://gamma-api.polymarket.com)
- Kalshi keys present: no (api_base=https://api.elections.kalshi.com/trade-api/v2)
- budget cap set: yes (prompt=1500000/h, completion=400000/h, path=/var/lib/theseus/forecasts_budget.json, writable=no)
- store reachable: yes (url source=noosphere.config.default, scheme=sqlite)
- forecast schema present: yes
- pending-prediction estimate: 0

Gate reasons:
- Kalshi keys absent (KALSHI_API_KEY_ID / KALSHI_API_PRIVATE_KEY not set)

## B. Dry-run

Not executed — pre-flight GATED (see above). A dry-run still needs a reachable store and the forecast schema to enumerate the pending prediction set.

## Run not started — pre-flight GATE

The pre-flight stage did not pass, so the harness stopped before stage B. **No venues were queried and no rows were written.** This is the harness behaving as designed: the pre-flight is a gate, not a warning.

Re-run once the gate reasons above are resolved. The backfill is idempotent and resumable, so a gated run costs nothing — the next run picks up the full pending set.
