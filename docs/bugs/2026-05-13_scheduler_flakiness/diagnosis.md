# Forecasts scheduler — continuous-running flakiness

- Reported: 2026-05-13
- Component: `noosphere/noosphere/forecasts/scheduler.py`
- Status: diagnosed, root-cause patched, hardening landed

## Symptom

The founder reported that "continuous running is being weird" — the
forecasts/bets pipeline appeared to stall intermittently. The
`/readyz` handler in `current_events_api/current_events_api/routes/forecasts.py`
flipped to `forecasts_ingest_stuck` even though sub-loops were
plainly making progress in the logs, and on operator restarts the
status file occasionally reflected a partially-updated tick.

## Bounded reproduction

A fast-clock test
(`noosphere/tests/test_scheduler_continuous.py`) was added that runs
`scheduler.run_forever` with every interval at 50 ms for 3 seconds.
Under that load — before the fix — the following bad behaviours
were observable:

1. The status file occasionally landed with a stale
   `last_ingest_ts` even though the rest of the payload had moved
   forward. The shared `status_lock` ordered writes, but the
   payload was *constructed* outside the lock once and then written
   inside it; in races between two sub-loops the older payload
   could win. (We could not see a torn read because
   `status.write_status` already does an atomic temp-file rename —
   so the kernel-level write was safe, the *content* was the
   problem.)
2. Sub-loops that produced no work (e.g. `live_orders` when
   `FORECASTS_LIVE_TRADING_ENABLED` is unset) did not advance any
   wall-clock field that `/readyz` could see. Only `last_ingest_ts`
   is consulted there, and that field advances only when the
   ingest loop completes. When ingest legitimately takes longer
   than `2 * FORECASTS_INGEST_INTERVAL_S` (slow Polymarket Gamma
   response, 5xx burst, etc.), `/readyz` flipped to "stuck" even
   though nothing was wrong with the scheduler.
3. A hung HTTP call inside an `ingest_polymarket_once` (or any
   other tick runner) had no upper bound — the sub-loop was
   indefinitely starved with no log, and the only signal was the
   stale status file. There was no per-tick timeout.
4. On `SIGTERM` mid-tick the budget JSON was always re-saved
   atomically (the underlying `HourlyBudgetGuard.save` uses temp
   file + `os.replace`), so the recurring "scheduler exits and
   leaves the budget corrupt" theory turned out to be wrong. The
   real issue on shutdown was that no final status row was
   written, so the next process boot saw a status file from the
   *previous* tick with no shutdown marker. Operators had no way
   to distinguish "killed cleanly 30 s ago" from "wedged 30 s ago".

The other candidates listed in the bug report were ruled out:

- **`asyncio.Lock` starvation between sub-loops**: each sub-loop
  has its own per-loop `asyncio.Lock` in `run_forever`, and the
  only shared lock is `status_lock`. Status writes are short, so
  the lock is not a starvation source — but it *was* a place
  where DB reads ran inside the critical section, which we
  removed (see fix #1).
- **Postgres connection pool exhaustion**: ruled out — only one DB
  session is opened per sub-loop tick, with at most nine
  concurrent sessions when every sub-loop runs at once. That is
  well under the default 20-connection pool.
- **SIGTERM-mid-tick corrupting budget JSON**: ruled out — budget
  save is already atomic (temp file + `os.replace` in
  `HourlyBudgetGuard.save`).
- **OOM-kill**: no signal in `dmesg`/container restart logs on
  the reporter's environment. The behavior is reproducible from
  a single Python process, so OOM is not the trigger.
- **DST / naive datetime drift**: every timestamp in the
  scheduler is `datetime.now(timezone.utc)` (aware) and
  serialized via `_json_default` to the `Z` ISO form. `_as_utc`
  normalizes naive DB rows. No naive arithmetic.

## Root causes (ranked)

1. **`/readyz` heartbeat is tied to one slow loop, not to
   scheduler liveness.** `last_ingest_ts` advances only when
   ingest completes. With `FORECASTS_INGEST_INTERVAL_S=900` the
   stuck threshold is 30 min, and a single slow Gamma response
   can blow it.
2. **Status payload was constructed outside the lock, written
   inside.** Two sub-loops finishing close together could write
   the *older* payload last, leaving fields visibly going
   backwards on disk.
3. **No per-tick timeout.** A hung external call had no upper
   bound and produced no log event.
4. **No shutdown marker.** On clean shutdown there was no
   `shutdown_at` field, so a stale status file was indistinguishable
   from a wedged scheduler.

## Fix

Patches landed in `noosphere/noosphere/forecasts/scheduler.py` and
`noosphere/noosphere/forecasts/status.py`:

- **Independent heartbeat task.** `run_forever` launches a
  dedicated `_heartbeat_loop` that updates `state.last_tick_ts =
  utc_now_iso()` and persists the status file every
  ~`min(loop_intervals) / 2` seconds (bounded to `[0.05, 2.0]`).
  `last_tick_ts` is the new authoritative liveness signal — it
  ticks even when every sub-loop is busy or idle. `/readyz`
  continues to consult `last_ingest_ts` for ingest freshness, but
  operators now have a true liveness signal in the same file.
- **Status payload is computed inside the lock.** `_write_status`
  takes `status_lock` *before* building the payload. The DB reads
  are cheap (≤4 indexed queries) and serializing them removes the
  out-of-order overwrite. Combined with the existing
  temp-file + `os.replace` write, the on-disk file now strictly
  advances per the order taken on the lock.
- **Per-tick `asyncio.wait_for`.** Every sub-loop iteration wraps
  its runner in `asyncio.wait_for(runner(), timeout=10*interval_s)`
  (floor 10 s). On `TimeoutError` we emit a `forecasts_scheduler_tick_timeout`
  structured-log event and continue to the next interval. The
  cancelled runner is allowed to drain via the existing 30 s
  grace path on shutdown.
- **`SIGTERM`/`SIGINT` final-row.** The `finally` block of
  `run_forever` now records `state.shutdown_at`, persists one
  last status row, then saves the budget and removes signal
  handlers. The status file's `shutdown_at` field disambiguates a
  cleanly-drained scheduler from a wedged one.
- **Atomic write was already correct.** Kept as-is in
  `status.write_status` (temp file in same directory +
  `os.fsync` + `os.replace`). Documented in `SCHEDULER_OPS.md`.

We did **not** add retries around the LLM / Polymarket calls. The
ingestors already have their own retry/backoff logic; layering
scheduler retries on top would only hide a hung HTTP call. A real
timeout is the right primitive.

## Verification

- New continuous-run integration test
  (`noosphere/tests/test_scheduler_continuous.py`) runs the full
  scheduler for 3 s of fast-clock and asserts:
  - every sub-loop ticked at least 20×,
  - `last_tick_ts` advances monotonically,
  - no exception was raised by any sub-loop,
  - no asyncio lock-wait took longer than 1 s,
  - `SIGTERM` during the run exits cleanly within 5 s and writes
    a `shutdown_at` row.
- The original scheduler suite (`tests/test_forecasts_scheduler.py`)
  was kept green to guard against regressing the SIGTERM-drain and
  no-overlap properties.

## Follow-ups (out of scope for this fix)

- The `/readyz` handler still keys off `last_ingest_ts`. The
  intent is for it to prefer `last_tick_ts` and only fall through
  to `last_ingest_ts` when the heartbeat is missing. Tracked
  separately because the route lives in `current_events_api/` and
  this fix's scope was scoped to `noosphere/forecasts/`.
- The same heartbeat treatment should be backported to the
  Currents scheduler. Currents has one big cycle so the failure
  mode is gentler, but the diagnostic value of a `last_tick_ts`
  field is identical.
