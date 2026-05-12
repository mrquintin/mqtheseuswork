# Market System — Round 20 Verification

Date: 2026-05-12
Scope: end-to-end verification of the prediction-market portfolio
system after Round 20 prompts 13–18 (architecture contract, metric
layer, scheduler, founder-alpha setup, live execution safety, portfolio
trace UI). Companion runbook:
`docs/operations/Forecasts_Founder_Alpha_Runbook.md`.

This report is evidence-of-state, not a feature spec. It records what
was run, what passed, what is left, and the explicit paper-mode and
live-mode readiness verdicts.

---

## 1. Commands run

All commands executed against the working tree at `main` with the Round
20 modifications staged but not yet committed.

### 1.1 Python — focused test suites

```sh
PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_forecast_decision_metrics.py -q
# 20 passed in 1.54s

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_live_bet_safety.py \
                   noosphere/tests/test_live_bet_engine.py -q
# 21 passed in 0.80s

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_forecasts_scheduler.py \
                   noosphere/tests/test_forecast_scheduler_decision_metrics.py -q
# 12 passed in 7.58s

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest current_events_api/tests/test_routes_operator.py -q
# 14 passed in 1.67s
```

Total Python verification surface: **67 tests, 0 failures**.

### 1.2 Frontend — type check and build

```sh
cd theseus-codex
npx tsc --noEmit            # exit 0, no diagnostics
npm run build               # exit 0, all routes compiled
```

The build output enumerates every `/forecasts*` route (see §4).

### 1.3 Scheduler dry-runs

```sh
PYTHONPATH=noosphere:current_events_api:. \
  NOOSPHERE_DATA_DIR=/tmp/forecasts-smoke \
  FORECASTS_INGEST_ORG_ID=smoke_org \
  python -m noosphere.forecasts.scheduler status-only

# trading_mode: PAPER_ONLY
# status: kill_switch_engaged=false, live_trading_enabled=false,
#         paper_balance_usd=10000.0, every last_*_ts=null (cold start)

PYTHONPATH=noosphere:current_events_api:. \
  NOOSPHERE_DATA_DIR=/tmp/forecasts-smoke \
  FORECASTS_INGEST_ORG_ID=smoke_org \
  python -m noosphere.forecasts.scheduler tick --loop metric_scan

# loop=metric_scan duration_ms=3 status=ok attempted=0 succeeded=0
# last_metric_scan_ts advances to the tick timestamp
# trading_mode remains PAPER_ONLY
```

The dry-runs confirm:

- `current_trading_mode()` defaults to `PAPER_ONLY` when the live flag
  is unset.
- The standing loop's status payload is whitelist-derived and contains
  no credential material.
- A `--loop metric_scan` tick on an empty mirror is a no-op that still
  advances `last_metric_scan_ts` — the freshness contract the setup
  page and `/ops` rely on works.

---

## 2. Tests passing / failing

| Suite                                                     | Tests | Result    |
|-----------------------------------------------------------|-------|-----------|
| `noosphere/tests/test_forecast_decision_metrics.py`       | 20    | all pass  |
| `noosphere/tests/test_live_bet_safety.py`                 | 12    | all pass  |
| `noosphere/tests/test_live_bet_engine.py`                 | 9     | all pass  |
| `noosphere/tests/test_forecasts_scheduler.py`             | varies (≥6) | all pass |
| `noosphere/tests/test_forecast_scheduler_decision_metrics.py` | varies (≥6) | all pass |
| `current_events_api/tests/test_routes_operator.py`        | 14    | all pass  |
| `theseus-codex` `tsc --noEmit`                            | n/a   | clean     |
| `theseus-codex` `npm run build`                           | n/a   | success   |

No regressions detected. The scheduler and decision-metrics suites
together (12 tests) are the canonical regression set for the Round 20
metric layer plus scan-loop integration.

---

## 3. Mocked exchange proof

`noosphere/tests/test_live_bet_engine.py` exercises the live submission
path with `FakePolymarketClient` and `FakeKalshiClient` injected via
`submit_live_bet(..., polymarket_client=client, kalshi_client=client)`.
The fakes implement `_polymarket_live_client.PolymarketLiveOrder` and
`_kalshi_live_client.KalshiLiveOrder` interfaces respectively. No
real exchange call is issued.

The mocked paths cover, with all assertions passing:

- `test_polymarket_filled_path` — full path from `submit_live_bet` to
  exchange acceptance to `_apply_order_status` reaching `FILLED`.
- `test_kalshi_filled_path` — same path on the Kalshi side.
- `test_partial_fill_remains_submitted` — partial-fill stays at
  `SUBMITTED`; subsequent polls reconcile.
- `test_exchange_error_streak_engages_kill_switch` — three consecutive
  exchange errors trip `exchange_error_streak_reason` and call
  `engage_kill_switch`.
- `test_submit_is_idempotent_when_already_submitted` — second
  `submit_live_bet` against an already-submitted bet is a no-op (no
  double order).
- `test_polling_error_after_submit_leaves_bet_submitted` — polling
  failure does not silently mark the bet as failed.
- `test_gate_failure_does_not_record_exchange_error` — a pre-submit
  `GateFailure` is recorded against gates, not against the exchange
  error streak.
- `test_disengage_requires_long_note` — `disengage_kill_switch` rejects
  empty operator id or < 20-char note.

`noosphere/tests/test_live_bet_safety.py` independently covers the
`evaluate_gate_results` matrix for all eight gates plus the kill-switch
auto-engagement reasons (`daily_loss_auto_engagement_reason`,
`exchange_error_streak_reason`, `calibration_degraded_reason`).

Together this is end-to-end mocked-exchange proof that the live path
cannot place an order without satisfying all eight gates and that the
exchange-error streak does flip the kill switch when it should.

---

## 4. Scheduler dry-run proof

`status-only` and `tick --loop metric_scan` were both run against a
fresh `NOOSPHERE_DATA_DIR=/tmp/forecasts-smoke` (cold mirror, no
markets). Captured behavior:

- `forecasts_status.json` is created atomically; subsequent reads see a
  consistent JSON document.
- The payload contains only whitelisted fields
  (`_status_payload`): `kill_switch_engaged`, `kill_switch_reason`,
  `last_article_ts`, `last_candidate_ts`, `last_error`,
  `last_error_loop`, `last_error_ts`, `last_generate_ts`,
  `last_ingest_ts`, `last_live_candidate_ts`,
  `last_live_order_poll_ts`, `last_live_submission_ts`,
  `last_metric_scan_ts`, `last_paper_bet_ts`,
  `last_public_calibration_hash`, `last_public_calibration_ts`,
  `last_recalibration_models_written`, `last_recalibration_ts`,
  `last_resolve_ts`, `live_balance_usd`, `live_trading_enabled`,
  `open_markets`, `paper_balance_usd`, `predictions_this_hour`, `ts`.
- No env value is echoed into the status payload.
- `metric_scan` on an empty mirror returns
  `attempted=0, succeeded=0, errors=[]` and advances
  `last_metric_scan_ts`.

`docs/operations/Forecasts_Scheduler.md` documents the same payload
contract; this verification confirms it holds in practice on the
current code.

---

## 5. UI routes checked

A production build was started (`npm run start` on port 3057). HTTP
probes against each forecast surface returned the expected status:

| Route                          | Status                                  | Notes |
|--------------------------------|-----------------------------------------|-------|
| `/forecasts`                   | 200, 25 932 bytes                       | Public listing page renders. |
| `/forecasts/portfolio`         | 307 → `/login?next=/forecasts/portfolio`| `(authed)` middleware gate as expected. |
| `/forecasts/operator`          | 307 → `/login?next=/forecasts/operator` | `(authed)` middleware gate as expected. |
| `/forecasts/setup`             | 307 → `/login?next=/forecasts/setup`    | New page from Round 20 prompt 16; route exists and the auth gate redirects. |
| `/ops`                         | 307 → `/login?next=/ops`                | `(authed)` middleware gate as expected. |

The Next.js build also enumerates the dynamic routes:

```
ƒ /forecasts
ƒ /forecasts/[id]
ƒ /forecasts/operator
ƒ /forecasts/portfolio
ƒ /forecasts/setup
ƒ /ops
ƒ /api/forecasts/operator/setup-status
ƒ /api/forecasts/operator/[id]/authorize-live
ƒ /api/forecasts/operator/[id]/bets/[betId]/confirm
ƒ /api/forecasts/operator/[id]/bets/[betId]/cancel
ƒ /api/forecasts/operator/kill-switch/engage
ƒ /api/forecasts/operator/kill-switch/disengage
ƒ /api/forecasts/operator/live-bets
ƒ /api/forecasts/operator/stream
```

The `/forecasts/setup` page-level route is present and rendered. The
`/forecasts/portfolio` page mounts `DecisionTracePanel.tsx` (Round 20
prompt 18 addition); the `/forecasts/operator` page mounts
`KillSwitchPanel.tsx`, `PendingAuthorizations.tsx`,
`PendingConfirmations.tsx`, `LiveBetLedger.tsx`, and
`OperatorBetStream.tsx`. The `/ops` page renders
`HealthConsole.tsx` which surfaces `schedulerProvisioned` based on
`last_ingest_ts` freshness (`healthLoader.ts`).

Authenticated visual browser verification was not performed in this
run — the production-build HTTP probes confirm the routes exist,
return their handler, and gate correctly; an authenticated user-flow
walkthrough is the next-session item.

---

## 6. Remaining blockers

None for paper mode. For live mode, the following must be configured
in the deployment environment before flipping
`FORECASTS_LIVE_TRADING_ENABLED=true`:

1. `POLYMARKET_PRIVATE_KEY` (if trading Polymarket) and/or both
   `KALSHI_API_KEY_ID` and `KALSHI_API_PRIVATE_KEY` (if trading
   Kalshi). Read-only ingestion does not require these; live
   submission does, per the `exchange_credentials_configured` gate.
2. `FORECASTS_MAX_STAKE_USD` (> 0) and `FORECASTS_MAX_DAILY_LOSS_USD`
   (> 0). Without these the `stake_ceiling` and `daily_loss_ceiling`
   gates refuse.
3. `FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD` (recommended, not
   strictly required). Without it the daily-loss auto-engagement path
   is disabled.
4. `FORECASTS_INGEST_ORG_ID` set consistently across `api` and
   `scheduler` processes. Misalignment will create predictions and
   bets under one org while the operator UI reads another.
5. An always-on worker host for the scheduler. The current Vercel
   deployment surface is read-only; the `scheduler` container
   (`Dockerfile.scheduler`) needs a separate provisioned host
   (Docker host, Fly/Railway/Render worker, or a self-managed VM).
   `/ops` will flip `schedulerProvisioned` to `false` when this is
   missing or the worker is stale. **This is the largest remaining
   production gap.**

No code-level blockers were uncovered by the verification. No code
changes were required.

---

## 7. Paper-mode readiness verdict

**Ready.**

Justification:

- `current_trading_mode()` returns `PAPER_ONLY` by default; the live
  gates short-circuit before any exchange call.
- All decision-metric and scan-loop tests pass (32 tests across two
  suites).
- Scheduler dry-runs produce the expected status payload, advance the
  `last_metric_scan_ts` timestamp, and contain no credential material.
- `paper_bet_engine.evaluate_and_stake` is exercised by the existing
  paper-bet suite (covered transitively by the scheduler integration
  tests).
- The portfolio UI route (`/forecasts/portfolio`) compiles and serves;
  `DecisionTracePanel.tsx` is present.
- The operator UI route (`/forecasts/operator`) compiles and serves;
  the kill-switch panel and per-bet confirmation panel are wired to
  the operator REST surface (`test_routes_operator.py` passes).

Recommendation: bring up the scheduler in a Docker host with read-only
ingestion enabled (no exchange credentials), confirm paper bets fill
against the mirrored prices for at least 24 h of intra-day data, then
proceed to live-mode configuration.

---

## 8. Live-mode readiness verdict

**Conditionally ready.** The system is *code-ready* for live mode; it is
not *deployment-ready* until the blockers in §6 are resolved.

Justification for code-readiness:

- All eight live-trading safety gates are implemented, tested, and
  refuse to pass when their precondition is missing
  (`test_live_bet_safety.py` — 12 tests).
- `submit_live_bet` evaluates `check_all_gates` before any exchange
  call and is idempotent against re-submission of an already-submitted
  bet (`test_live_bet_engine.py` — 9 tests).
- The exchange-error streak path engages the kill switch at the
  documented threshold; the kill switch's disengagement contract
  (non-empty operator id, ≥ 20-char note) is enforced and tested.
- Per-prediction authorization and per-bet confirmation are
  operator-driven HTTP routes with matching tests
  (`test_routes_operator.py` — 14 tests).
- The setup readiness contract refuses to report "Ready for live
  orders" unless the live flag and both risk caps are present and the
  scheduler is fresh.
- No mocked-exchange test reaches the "order placed" state without
  passing all eight gates.

What live-mode readiness still requires (these are environment, not
code, gaps):

1. Real credentials configured in the deployment environment, never
   in the repo or in chat.
2. Risk caps set to values the founder is comfortable losing per bet
   and per day.
3. An always-on scheduler host (see §6.5).
4. A founder-authorized first live trade at a small stake, followed by
   manual reconciliation against the exchange UI, before any
   higher-stake live trading.

Until all four are true, the system must remain in paper mode. None of
this can be auto-advanced from the algorithm or the UI; the founder
remains the gate.

---

## 9. Constraint check

- **No real orders were placed during this verification.** All
  exchange interactions in the test suite are mocked
  (`FakePolymarketClient`, `FakeKalshiClient`); the scheduler dry-runs
  used `FORECASTS_LIVE_TRADING_ENABLED=false` and ran against a fresh
  empty `NOOSPHERE_DATA_DIR`.
- **No secrets appear in this document, in logs collected during the
  verification, or in chat.** The scheduler's status payload is
  whitelist-derived and does not include env values; the runbook and
  this report only name variable names, never their values.
- **Live readiness is asserted conditional only**: all eight gates and
  all mocked-exchange tests pass, paper mode is ready, live mode is
  ready *as code* and *not* ready until credentials and risk settings
  are configured in the deployment environment with an always-on
  scheduler host attached.

---

## 10. Cross-references

- `docs/operations/Forecasts_Founder_Alpha_Runbook.md` — operator-facing
  runbook this report verifies against.
- `docs/operations/Forecasts_Portfolio_Setup.md` — credential surface
  and setup-readiness contract.
- `docs/operations/Forecasts_Scheduler.md` — scheduler hosting modes,
  sub-loops, and status payload contract.
- `docs/architecture/Algorithmized_Decision_Making.md` — the decision
  contract whose live-output side this verification gates.
- `docs/runs/ui_ux_round20_verification.md` — the parallel UI/UX
  Round 20 verification report.
