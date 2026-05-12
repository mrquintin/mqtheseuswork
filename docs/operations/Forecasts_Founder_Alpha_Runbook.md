# Forecasts — Founder-Alpha Runbook

Date: 2026-05-12
Status: Active. Companion to `docs/operations/Forecasts_Portfolio_Setup.md`
(credential surface), `docs/operations/Forecasts_Scheduler.md` (worker
loops) and `docs/architecture/Algorithmized_Decision_Making.md` (decision
contract). This document is the single page a founder needs in front of
them when bringing the prediction-market portfolio system from a cold
start to read-only monitoring, to paper trading, and — only when every
gate is satisfied — to live trading.

Founder-alpha rule of thumb: **the system is read-only by default and
stays read-only until you explicitly authorize each step**. Nothing here
auto-promotes. If you skip a step, the next one will refuse to run.

---

## 0. The staircase

```
exchange credentials configured            ← env vars only, see §1
        ↓
scheduler ingesting & monitoring           ← worker container running, see §5
        ↓
paper mode validated                       ← §6
        ↓
risk caps configured                       ← FORECASTS_MAX_STAKE_USD,
                                             FORECASTS_MAX_DAILY_LOSS_USD
        ↓
FORECASTS_LIVE_TRADING_ENABLED=true        ← master live flag
        ↓
per-prediction live authorization          ← operator UI, see §8.1
        ↓
per-bet live confirmation                  ← operator UI, see §8.2
        ↓
kill switch clear at submit time           ← see §9
        ↓
exchange order submitted via submit_live_bet
```

Each arrow is a separate human gate. Nothing crosses an arrow on its own.

---

## 1. Credentials

The only supported credential channel today is environment variables on
the API and scheduler processes. There is no in-app credential entry form
and the codebase intentionally does not log key material. See
`docs/operations/Forecasts_Portfolio_Setup.md` §5 for the negative rules.

### 1.1 Polymarket

| Variable                          | Required | Purpose |
|-----------------------------------|----------|---------|
| `POLYMARKET_PRIVATE_KEY`          | yes      | EVM private key controlling the Polymarket CLOB wallet. Controls real funds. |
| `POLYMARKET_CLOB_BASE`            | no       | CLOB base URL override (default `https://clob.polymarket.com`). |
| `POLYMARKET_CHAIN_ID`             | no       | Defaults to `137` (Polygon). |
| `POLYMARKET_SIGNATURE_TYPE`       | no       | Polymarket SDK signature type, defaults to `0`. |
| `POLYMARKET_FUNDER_ADDRESS`       | no       | Set when trading from a proxy/funder wallet. |
| `POLYMARKET_DEFAULT_TICK_SIZE`    | no       | Defaults to `0.01`. |
| `POLYMARKET_DEFAULT_NEG_RISK`     | no       | `true`/`false`; per-market neg-risk default. |
| `FORECASTS_POLYMARKET_CATEGORIES` | no       | Comma-separated category allow-list for ingestion. |

`POLYMARKET_PRIVATE_KEY` is treated as live-funds key material. Read it
from a secrets manager into the process environment; never paste it into
chat, screenshots, support threads, GitHub issues, or any shared doc.

### 1.2 Kalshi

| Variable                        | Required | Purpose |
|---------------------------------|----------|---------|
| `KALSHI_API_KEY_ID`             | yes      | Kalshi API key id (public part). |
| `KALSHI_API_PRIVATE_KEY`        | yes      | RSA PEM body. For one-line `.env` files, encode newlines as literal `\n`. |
| `KALSHI_PRIVATE_KEY_PEM`        | (alt)    | Legacy variable name; accepted as a fallback. |
| `KALSHI_API_BASE`               | no       | Base URL override (default `https://api.elections.kalshi.com/...`). |
| `FORECASTS_KALSHI_CATEGORIES`   | no       | Comma-separated category allow-list for ingestion. |

The Kalshi PEM body is sensitive. The same handling rule as the
Polymarket private key applies.

### 1.3 Read-only mode

Read-only ingestion does not require either set of credentials. If the
keys are absent, the scheduler still ingests the public market mirror and
prices, and forecasts can be generated and paper-traded. The
`exchange_credentials_configured` gate in `noosphere.forecasts.safety`
will simply refuse `submit_live_bet` for any exchange whose credentials
are not present.

---

## 2. Risk-limit environment variables

These are read by the API and scheduler at start. Restart both after
changes. Required-for-live means the live path refuses to submit without
them.

| Variable                                   | Required for live | Purpose |
|--------------------------------------------|-------------------|---------|
| `FORECASTS_LIVE_TRADING_ENABLED`           | yes (`true`)      | Master live gate. Without this the live path refuses regardless of authorization. |
| `FORECASTS_MAX_STAKE_USD`                  | yes (> 0)         | Per-bet stake ceiling enforced by `stake_ceiling` gate. |
| `FORECASTS_MAX_DAILY_LOSS_USD`             | yes (> 0)         | Daily-loss ceiling enforced by `daily_loss_ceiling` gate. |
| `FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD` | no                | When daily loss reaches this value, kill switch auto-engages via `daily_loss_auto_engagement_reason`. |
| `FORECASTS_INGEST_ORG_ID`                  | yes (any mode)    | Organization id for ingested markets, predictions, bets, and the portfolio state row. |
| `FORECASTS_STATUS_PATH`                    | no                | Override the scheduler status-file path. |
| `FORECASTS_STATUS_MAX_AGE_SECONDS`         | no                | Freshness threshold for "Monitoring active" (default `1800`). |
| `FORECASTS_OPERATOR_SECRET`                | yes (for operator UI) | HMAC shared secret between Codex and the operator API. |
| `FORECASTS_OPERATOR_CSRF_TOKEN`            | no                | Optional pinned CSRF token (defaults to a founder-scoped value). |
| `FORECASTS_API_URL` / `CURRENTS_API_URL`   | yes               | Base URL of the FastAPI service the Codex proxy talks to. |

Per `Forecasts_Portfolio_Setup.md` §1.3: configure the risk caps **before**
flipping `FORECASTS_LIVE_TRADING_ENABLED`. The setup page reports
"Ready for live orders" only when all three are present.

---

## 3. Local development

```sh
# 1. Repo root .env (gitignored)
#    POLYMARKET_PRIVATE_KEY=...           (optional for read-only)
#    KALSHI_API_KEY_ID=...                 (optional for read-only)
#    KALSHI_API_PRIVATE_KEY=...            (optional for read-only)
#    FORECASTS_INGEST_ORG_ID=org_dev
#    FORECASTS_OPERATOR_SECRET=dev_secret
#    FORECASTS_API_URL=http://localhost:8000
#    FORECASTS_MAX_STAKE_USD=50           (only when you intend to test live)
#    FORECASTS_MAX_DAILY_LOSS_USD=200     (only when you intend to test live)

# 2. API
uvicorn current_events_api.app:create_app --factory --reload

# 3. Scheduler (separate terminal)
export NOOSPHERE_DATA_DIR=$PWD/noosphere_data
./scripts/run-forecast-scheduler.sh loop

# 4. Theseus Codex frontend (separate terminal)
cd theseus-codex && npm run dev
```

Open `http://localhost:3000/forecasts/setup`. The three readiness tiles
report what the server actually sees from env and from the scheduler
status file. In a fresh dev environment "Ready for live orders" must say
NOT READY until you set the risk caps and flip the live flag — that is
correct.

---

## 4. Deployment

Theseus deployment is Docker Compose by default (`docker-compose.yml`).
The `api` and `scheduler` services both read env from the host.

- **Single-host self-hosted**: place the env in `/etc/theseus/.env`
  (root-owned, `0600`) and reference from compose via `env_file:`.
- **Managed secret store (recommended for multi-host)**: mount the
  secret into the container at start using your platform's secret
  manager (AWS Secrets Manager, GCP Secret Manager, 1Password Connect,
  Doppler, etc.). Do not bake keys into the image. CI does not need
  live keys.
- **Always-on worker**: `Dockerfile.scheduler` builds the worker image;
  `docker compose up -d scheduler` starts the standing loop. The compose
  healthcheck reads `forecasts_status.json` and fails when the file is
  older than `FORECASTS_STATUS_MAX_AGE_SECONDS` (default 1800 s). This
  catches a dead scheduler without a separate watchdog.

**Production caveat — always-on worker subscription.** Live monitoring
requires a continuously running scheduler container (or an equivalent
systemd service). If the deployment target is a serverless platform
that does not provide an always-on worker (e.g. a Vercel-only deploy
with no companion worker host), this must be provisioned separately —
either as a Docker host, a Fly.io / Railway / Render worker, or a
self-managed VM. The Codex `/ops` page surfaces a
`schedulerProvisioned` flag (`HealthConsole.tsx`) that flips to `false`
when `last_ingest_ts` is stale or missing. A 10-minute GitHub Actions
fallback (`docs/operations/Forecasts_Scheduler.md` §"GitHub Actions
sweep") is documented but **not adequate for live trading** — it will
miss intra-window edges.

Restart `api` and `scheduler` after rotating any value.

---

## 5. Scheduler process

The scheduler is the worker loop that turns "we have a database with
market mirrors" into "the system is monitoring on its own." It is not a
one-shot script. Reference: `docs/operations/Forecasts_Scheduler.md`.

Sub-loops at a glance (see scheduler doc for full table and tunables):

| Loop                | Default interval | Purpose |
|---------------------|------------------|---------|
| `ingest`            | 900 s            | Refresh Polymarket + Kalshi markets and prices. |
| `generate`          | 600 s            | LLM forecast generation for markets without a recent published prediction. |
| `metric_scan`       | 420 s            | Re-apply decision metrics against current prices; emit paper-bet candidates and log live candidates. **Never submits live orders.** |
| `resolve`           | 300 s            | Poll exchanges for settlement outcomes; append `ForecastResolution`. |
| `paper_drain`       | 60 s             | Settle paper bets on resolved markets. |
| `live_orders`       | 60 s             | Poll exchange status for submitted live bets. No-op when live flag is off. |
| `articles`          | 3600 s           | Dispatch triggered Currents articles. |
| `public_calibration`| 86 400 s         | Rebuild public calibration manifest. |
| `recalibration`     | 604 800 s        | Fit per-domain isotonic recalibration models. |

Entry points:

```sh
# Standing scheduler (production)
python -m noosphere.forecasts.scheduler run

# Cron-friendly single pass
python -m noosphere.forecasts.scheduler tick

# Restrict to specific loops
python -m noosphere.forecasts.scheduler tick --loop ingest --loop metric_scan

# Refresh status JSON only (no work)
python -m noosphere.forecasts.scheduler status-only
```

`scripts/run-forecast-scheduler.sh` is the recommended wrapper.

The scheduler writes `forecasts_status.json` atomically on every tick.
Fields exposed are whitelist-derived in `noosphere.forecasts.scheduler.
_status_payload`; the file never carries credential material.

---

## 6. Verifying read-only ingestion

1. Start the scheduler (`./scripts/run-forecast-scheduler.sh loop` locally,
   or `docker compose up -d scheduler` in production).
2. Watch the logs for `forecast_polymarket_ingest_ok` and
   `forecast_kalshi_ingest_ok` (or the no-credentials variant —
   ingestion of public market metadata works without keys, but the
   credential-gated client paths log clearly when they are skipped).
3. Confirm `last_ingest_ts` advances:

   ```sh
   PYTHONPATH=noosphere:current_events_api:. \
     NOOSPHERE_DATA_DIR=$PWD/noosphere_data \
     python -m noosphere.forecasts.scheduler status-only
   ```

   Two consecutive calls (one after `tick --loop ingest`, one without)
   should show `last_ingest_ts` rising.

4. In the UI, `/forecasts/setup` "Monitoring active" tile flips to true
   once `last_ingest_ts` is within `FORECASTS_STATUS_MAX_AGE_SECONDS`.
   `/ops` surfaces the same status under "Always-on worker (scheduler)".

No live calls happen during read-only ingestion. The scheduler can also
run with the live flag off and write paper bets only — see §7.

---

## 7. Verifying decision-metric scans

The decision-metric scan is the "what would this look like as an
investable output" pass. It does not submit live orders.

```sh
# One-off scan (logs candidates and writes traces; no submission)
PYTHONPATH=noosphere:current_events_api:. \
  python -m noosphere.forecasts.scheduler metric-scan

# Or restrict a normal tick to the scan loop
PYTHONPATH=noosphere:current_events_api:. \
  python -m noosphere.forecasts.scheduler tick --loop metric_scan
```

After a scan, `last_metric_scan_ts` advances in `forecasts_status.json`,
and the operator and portfolio surfaces show updated decision traces.

Focused test suites covering the metric layer and the scan path:

```sh
PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_forecast_decision_metrics.py -q
PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_forecast_scheduler_decision_metrics.py -q
```

These are the canonical regression set for prompts 14–16 of Round 20.

---

## 8. Paper mode and live mode

### 8.1 Paper mode

Paper mode is on by default. With `FORECASTS_LIVE_TRADING_ENABLED` unset
or `false`:

- `noosphere.forecasts.safety.current_trading_mode()` returns
  `PAPER_ONLY`.
- `paper_bet_engine.evaluate_and_stake` fills against the paper balance
  at quarter-Kelly (capped by `PaperBetConfig.max_stake_usd`).
- `submit_live_bet` is unreachable: the `live_trading_enabled` gate
  fails before any exchange call.

To exercise paper mode end-to-end:

1. Run the scheduler loop (any subset that includes `ingest`, `generate`,
   and `metric_scan`).
2. Open `/forecasts/portfolio` — paper fills appear in the portfolio
   view with their `DecisionTracePanel`.
3. Open `/forecasts/operator` — the pending-authorization panel lists
   `live_candidate` decisions (advisory only) but the live ledger is
   empty.

### 8.2 Enabling live mode

Do not enable live mode until paper mode has been validated for the
specific market category you intend to trade. The promotion sequence
is:

1. Verify the setup page reports "Ready for live candidates" (monitoring
   active AND at least one exchange configured AND kill switch clear).
2. Set the risk caps:
   ```sh
   FORECASTS_MAX_STAKE_USD=50              # start small
   FORECASTS_MAX_DAILY_LOSS_USD=200
   FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD=200
   ```
3. Set the live flag last:
   ```sh
   FORECASTS_LIVE_TRADING_ENABLED=true
   ```
4. Restart the `api` and `scheduler` services so the env reload
   propagates.
5. The setup page should now report "Ready for live orders". This does
   *not* mean the next bet executes — see §8.3.

### 8.3 Live authorization and per-bet confirmation

The live-trading safety contract (`noosphere/noosphere/forecasts/safety.py`)
enforces eight gates in order. `submit_live_bet` raises `GateFailure`
*before* touching the exchange when any gate fails:

1. `live_trading_enabled` — `FORECASTS_LIVE_TRADING_ENABLED=true`.
2. `exchange_credentials_configured` — credentials present for the
   target exchange (Polymarket or Kalshi).
3. `prediction_live_authorized` — the parent `ForecastPrediction` row
   has `live_authorized_at` set.
4. `operator_confirmation` — the bet has `status == "CONFIRMED"` and
   `confirmed_at is not None`.
5. `stake_ceiling` — `bet.stake_usd ≤ FORECASTS_MAX_STAKE_USD`.
6. `daily_loss_ceiling` — running daily loss is within
   `FORECASTS_MAX_DAILY_LOSS_USD`.
7. `kill_switch_clear` — `ForecastPortfolioState.kill_switch_engaged`
   is false.
8. `sufficient_live_balance` — `live_balance_usd ≥ stake_usd`.

Gates 3 and 4 are operator-driven and the UI flow is:

- **Per-prediction authorization** at `/forecasts/operator`
  (`PendingAuthorizations.tsx`). The operator clicks "Authorize live"
  on a specific prediction; the API call
  `/api/forecasts/operator/[id]/authorize-live` sets
  `live_authorized_at` on the prediction.
- **Per-bet confirmation** at `/forecasts/operator`
  (`PendingConfirmations.tsx`). For each `ForecastBet` row in
  `PENDING_LIVE_CONFIRMATION`, the operator clicks "Confirm". The API
  call `/api/forecasts/operator/[id]/bets/[betId]/confirm` flips the
  bet to `CONFIRMED` with `confirmed_at = now()`. Only after this does
  `submit_live_bet` proceed.

Neither authorization nor confirmation is auto-advanced by the
algorithm. The rule graph can pick `live_candidate`; only an operator
can synthesize the two timestamps that make the gates pass.

The full sequence for a single live order, end-to-end:

```
metric_scan → decision = live_candidate
            → ForecastTrace persisted
operator UI → /api/forecasts/operator/[id]/authorize-live
            → prediction.live_authorized_at set
operator UI → /api/forecasts/operator/[id]/bets/[betId]/confirm
            → bet.status = CONFIRMED, bet.confirmed_at set
submit_live_bet → check_all_gates (8 gates)
                → _submit_polymarket_order or _submit_kalshi_order
                → _poll_order_status → bet.status updated
```

Mocked-exchange coverage for this path is in
`noosphere/tests/test_live_bet_engine.py` (Polymarket filled,
Kalshi filled, partial fill, gate failure does not record exchange
error, idempotent re-submit, polling-error path, exchange-error-streak
kill switch).

---

## 9. Kill switch

The kill switch is the always-true veto. Engaging it instantly fails the
`kill_switch_clear` gate and the readiness contract returns 503.
`ingest`, `resolve`, and `paper_drain` continue (so the mirror stays
current and resolved markets still settle), but `generate` and
`metric_scan` short-circuit.

Engagement paths:

- **Operator manual** — `/api/forecasts/operator/kill-switch/engage`
  (operator UI button). Reason field required.
- **Daily-loss auto** —
  `noosphere.forecasts.safety.daily_loss_auto_engagement_reason`. Trips
  when `state.daily_loss_usd ≥ FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD`.
- **Exchange-error streak** — `exchange_error_streak_reason`. Trips at
  three consecutive exchange errors for the organization.
- **Calibration degraded** — `calibration_degraded_reason`. Trips when
  the most recent 50-resolution mean Brier exceeds `max_mean_brier=0.30`.

Disengagement requires both a non-empty `operator_id` and a note ≥ 20
characters (`disengage_kill_switch` raises `ValueError` otherwise).
The operator UI form enforces these.

```sh
# Engage from a shell (emergency)
PYTHONPATH=noosphere:current_events_api:. python - <<'PY'
from noosphere.forecasts.safety import engage_kill_switch
from noosphere.forecasts.store import default_store
engage_kill_switch(default_store(), "org_prod", reason="OPERATOR_HALT")
PY
```

---

## 10. How to stop all trading

In descending order of bluntness — pick the right level for what is
happening:

1. **Stop new live orders** (preserve open positions). Engage the kill
   switch via the operator UI ("Engage kill switch" in
   `KillSwitchPanel.tsx`), or call `engage_kill_switch` directly. New
   `submit_live_bet` calls fail at the `kill_switch_clear` gate; the
   scheduler's `metric_scan` and `generate` loops short-circuit.
2. **Stop the scheduler** (preserve credentials and UI). `docker compose
   stop scheduler`, or `^C` on the local loop. The API still serves
   `/forecasts/*` read endpoints; no new candidates or paper fills are
   produced.
3. **Disable live trading** (preserve scheduler and paper mode). Unset
   or set `FORECASTS_LIVE_TRADING_ENABLED=false` and restart `api` and
   `scheduler`. `current_trading_mode()` returns `PAPER_ONLY`; all live
   gate paths refuse. Paper bets continue.
4. **Remove credentials** (preserve nothing live). Unset
   `POLYMARKET_PRIVATE_KEY`, `KALSHI_API_KEY_ID`, and
   `KALSHI_API_PRIVATE_KEY`. Restart `api` and `scheduler`. The
   `exchange_credentials_configured` gate fails for every exchange.
   Read-only ingestion continues for public market data.
5. **Halt everything**. `docker compose down`. The mirror stops
   advancing; nothing in the system can place an order.

After any of (1)–(4), revisit `/forecasts/setup` to confirm the readiness
tiles match the intended state before resuming.

---

## 11. References

- `noosphere/noosphere/forecasts/safety.py` — gate context, eight gates,
  kill switch, `current_trading_mode()`.
- `noosphere/noosphere/forecasts/live_bet_engine.py` — `submit_live_bet`,
  Polymarket/Kalshi submit paths, polling, error-streak kill switch.
- `noosphere/noosphere/forecasts/scheduler.py` — standing loop, status
  payload, CLI subcommands.
- `noosphere/noosphere/forecasts/decision_metrics.py` — metric layer
  consumed by the scheduler's `metric_scan` loop.
- `current_events_api/current_events_api/routes/operator.py` — operator
  REST surface backing the UI.
- `theseus-codex/src/app/(authed)/forecasts/setup/page.tsx` — setup
  readiness UI.
- `theseus-codex/src/app/(authed)/forecasts/operator/page.tsx` —
  authorization, confirmation, kill switch, live ledger.
- `theseus-codex/src/app/(authed)/forecasts/portfolio/ForecastPortfolioView.tsx`
  and `DecisionTracePanel.tsx` — portfolio and trace view.
- `docs/operations/Forecasts_Portfolio_Setup.md` — credential surface.
- `docs/operations/Forecasts_Scheduler.md` — scheduler lifecycle.
- `docs/architecture/Algorithmized_Decision_Making.md` — decision
  contract whose live output side this runbook gates.
- `docs/runs/market_system_round20_verification.md` — market-system
  end-to-end verification report.
- `docs/runs/empirical_abstract_decision_round20_verification.md` —
  cases / principles / transfer / decision-frame verification report
  (the subsystem documented in §12 below).

---

## 12. Empirical cases, abstract principles, transfer, and decision frames

This section documents the subsystem added by Round 20 prompts 20–24:
the path from "a source was uploaded" or "a Currents event fired" or
"a market refreshed" to "the decision trace cites which empirical
cases and which abstract principles influenced it, and what each
decision frame voted." Reference modules:

- `noosphere/noosphere/cases/` — empirical case-study extraction
  (`CaseStudyExtractor.extract`, `EmpiricalCaseStudy`,
  `CaseStudyExtraction`).
- `noosphere/noosphere/principles/` — `AbstractPrinciple`,
  `TransferGraph`, `PrincipleAbstractor.abstract`,
  `evaluate_transfer`, `TransferQuery`, `TransferReport`.
- `noosphere/noosphere/decisions/` — `FrameContext`, `run_frames`,
  `synthesize`, `SynthesisAction`.
- `noosphere/noosphere/forecasts/decision_metrics.py` —
  `build_decision_trace` fuses metrics, frames, and transfer into a
  single inspectable trace.

The §1 contract from `docs/architecture/Algorithmized_Decision_Making.md`
applies in full: analogy can only *downgrade* a decision, never
escalate it; principles must be contradiction-testable; provenance
from chunk → case → principle is preserved end-to-end.

### 12.1 How new uploads produce cases and principles

1. **Ingestion.** A new upload is chunked through the existing
   `noosphere.relevant_text` / `noosphere.conclusions` pipeline. No
   change there.
2. **Case extraction.** Each `Chunk` is passed through
   `CaseStudyExtractor.extract(chunk, source_type=…)`. The extractor:
   - strips uploaded prompt/instruction text via `PromptSeparator` so
     prompt sentences cannot become case facts;
   - calls the configured LLM with a strict-JSON schema and
     `extra=forbid` validation;
   - re-checks every `source_quote` against the chunk text — if the
     quote is not a verbatim substring, the case is dropped;
   - classifies each passage as one of
     `named_case | brief_example | hypothetical | analogy | abstract_concept`;
   - admits only `named_case` and `brief_example` as evidence
     (with `actors`/`institutions`, mechanism, outcome, and at least
     one linked principle present); the rest are recorded as
     `NonCaseMention` rows for audit but not used as evidence.
3. **Principle abstraction.** `PrincipleAbstractor.abstract(extractions,
   bounding_links=…, contradicting_links=…, abstract_only_sources=…)`
   consumes the extractions and:
   - canonicalises each `linked_principles[*].principle_text` to a
     content-addressed id (`canonical_principle_id` — sha256 of the
     normalized statement). Two cases that converge on the same
     statement get the same `AbstractPrinciple.id`.
   - merges supporting/bounding/contradicting case ids into the
     principle; widens `scope` across domains; preserves all
     `PrincipleProvenance` entries (chunk + verbatim quote + case
     id).
   - refuses to construct any principle without at least one
     `failure_conditions` or `negation_candidates` entry — that is
     enforced by `AbstractPrinciple._needs_failure_or_negation`.
   - caps confidence at `moderate` and status at `refined` on
     example count alone. Promotion to firm-level conviction is the
     `noosphere.distillation` path's responsibility, not the
     abstractor's.
4. **Persistence.** Cases and principles are persisted via the same
   `ForecastTrace` / conclusions models extended in earlier prompts;
   the resulting `TransferGraph` round-trips through
   `to_dict` / `to_json` byte-stably (see
   `test_transfer_graph_serialization_is_stable_across_insertion_order`).

A founder operator who wants to verify this manually can run:

```sh
PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_case_study_extraction.py \
                   noosphere/tests/test_principle_abstraction.py -q
```

### 12.2 How Currents and markets create new case candidates

The transfer engine is the contract that turns "new event / new
market" into "candidate transfer queries":

- **Currents events.**
  `noosphere.principles.transfer.query_from_currents_event(event)`
  accepts a Currents event row (dict or duck-typed object) and emits a
  `TransferQuery` with `case_id`, `domain`, `actors`, `institutions`,
  `mechanism`, `outcome_question`, `source_text`, and `observed_at`
  populated from the event. Missing fields stay empty rather than
  fabricated. Scheduler `articles` loop or operator action can pass
  the resulting query into `evaluate_transfer` to ask "which existing
  principles plausibly apply to this event?".
- **Market refreshes.** `query_from_market(market)` mirrors the
  `noosphere.forecasts.retrieval_adapter.build_query_from_market`
  recipe: `market.title` → `outcome_question`, `description +
  resolution_criteria` → `source_text`, `category` → `domain`. The
  scheduler's `metric_scan` loop is the natural caller; the
  resulting `TransferReport` is attached to
  `build_decision_trace` as the `transfer_report` argument.
- **New uploads.** `query_from_upload(upload)` normalizes
  `disciplines` (string or list) into `domain` and pulls
  `body`/`text` into `source_text`. The intent is "we just ingested
  a new source — does it look like a case that an existing principle
  would predict?".

Two-tier flow: an upload first produces cases via the extractor in
§12.1, and *separately* triggers a transfer query so the new event
can be tested against the existing principle pool. The two flows are
independent and can run concurrently.

### 12.3 How principles are monitored against future cases

The `TransferGraph` is the persistent substrate. Each principle
carries:

- `supporting_case_ids` — cases that have already instantiated it.
- `bounding_case_ids` — cases that narrowed its scope.
- `contradicting_case_ids` — cases that contradicted its predicted
  outcome under stated preconditions (status flips to
  `contradicted`; the principle is *not* deleted — the contradiction
  is kept so future cases can rediscover it).

Each principle also carries `failure_conditions` (with a
`detectable_signal` field) and `negation_candidates`. These are
exactly the predicates `evaluate_transfer` checks when a new
`TransferQuery` arrives:

- If the query's `failure_signals_present` contains a token match
  against a recorded `detectable_signal`, the recommendation's
  `contradiction_risk` jumps and the stance flips to
  `DOES_NOT_APPLY` — even if every other axis (precondition coverage,
  mechanism match, structural fit) aligns. This is the
  "single-failure-signal-is-enough-to-veto" posture verified by
  `test_failure_signal_present_drops_to_does_not_apply`.
- If the query densely overlaps a `negation_candidate.statement`'s
  specific tokens, the same axis is raised.
- If the query lies in a domain the principle's scope never recorded,
  `domain_shift ≥ 0.7` forces `WATCH` even on a clean mechanism
  match. This is the "structural match in a different domain"
  rejection.

Operators do not have to schedule this manually: the same monitoring
hooks in §12.2 produce candidate queries from every upload, Currents
event, and market refresh. Principles that earn a stream of
`DOES_NOT_APPLY` recommendations on plausibly-related queries are
the natural candidates for `noosphere.distillation`'s next review;
that path is unchanged.

### 12.4 How decision traces use empirical and abstract frames

`build_decision_trace(market, sources, citations, payload,
calibration_state, *, transfer_report=None, …)` is the entry point.
The new arguments and their effects:

1. **`transfer_report` (optional).** A
   `noosphere.principles.transfer.TransferReport`. When present, the
   trace adds an overlay rule named `analogical_transfer` whose
   behaviour is:
   - `best_stance == APPLIES` → no downgrade; the underlying
     metric/rule-graph decision stands.
   - `best_stance == WATCH` → live-eligible decisions
     (`LIVE_CANDIDATE`) are downgraded to `WATCH`.
   - `best_stance == DOES_NOT_APPLY` → the decision is forced to
     `ABSTAIN` regardless of what the rule graph picked. The trace
     records the overlay's `fired=True` and the report's
     `best_stance` is queryable via `trace.to_dict()
     ["analogical_transfer"]["best_stance"]`.
   - Missing report → backwards-compatible; the legacy decision
     behaviour from prompts 14–18 is preserved
     (`test_decision_trace_no_transfer_report_is_backwards_compatible`).
2. **Multi-frame engine.** The trace assembles a `FrameContext` from
   the computed metrics, calls `run_frames`, and `synthesize`s the
   verdicts. Seven frames vote:
   - `incentive_alignment` (caller-supplied conflict signals → hard
     stop);
   - `coordination_equilibrium` (edge magnitude sanity — too small =
     no consensus break; too large = mispricing implausible);
   - `principal_agent` (revoked principle on open position → `EXIT`;
     side flip → `REDUCE`);
   - `reflexivity` (high temporal decay or feedback-prone edges →
     downgrade);
   - `option_value` (low confidence + time remaining → wait);
   - `contradiction` (`contradiction_pressure` above
     `CONTRADICTION_HARD_STOP=0.55` → hard stop);
   - `empirical_transfer` (consumes the same `TransferReport`).
3. **Synthesis rules.** Deterministic and inspectable:
   - Any `HARD_STOP` → `ABSTAIN`.
   - Any `EXIT` → `EXIT`.
   - Too many `UNSTABLE` → `ABSTAIN`.
   - Split votes (no hard-stop, no majority) → `WATCH`.
   - Clean majority `SUPPORT` with no hard-stop → `SUPPORT`.
4. **Persistence.** The trace persists exactly the same
   `ForecastTrace.model_output` fields plus the new metric rows and
   the `analogical_transfer` overlay. The narrative summary is
   generated from the trace fields, never the inverse — the §2.5
   contract requirement.

Where the operator reads the trace:

- `/forecasts/portfolio` — `DecisionTracePanel.tsx` renders the
  metric rows, the fired rule-graph nodes, the frame results, and
  the analogical-transfer overlay. Public-facing rendering follows
  the visibility rules from §1.3 of
  `UI_UX_Round20_Contract.md` ("one-directional in display":
  decisions and rounded metric values are publishable; verbatim case
  source text from private uploads is not).
- `/forecasts/operator` — same trace, plus pending authorizations,
  per-bet confirmations, kill-switch panel, and live ledger.
- `/principles/[id]` and `/principles/queue` — founder-only browsing
  of `AbstractPrinciple` rows with their supporting / bounding /
  contradicting case lists and recorded failure conditions.

The eight live-trading safety gates from
`noosphere.forecasts.safety` are inherited unchanged. The
analogical-transfer overlay can only downgrade a decision; it cannot
escalate. Live submission still requires
`prediction_live_authorized`, `operator_confirmation`, the four risk
caps, the kill-switch-clear gate, and sufficient live balance —
exactly as documented in §8.3 above.

Canonical regression suites for this subsystem:

```sh
PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_case_study_extraction.py \
                   noosphere/tests/test_principle_abstraction.py \
                   noosphere/tests/test_analogical_transfer.py \
                   noosphere/tests/test_decision_frames.py \
                   noosphere/tests/test_forecast_decision_metrics.py -q
```

The most recent passing run (2026-05-12): 75 tests, 0 failures.
Verified separately in
`docs/runs/empirical_abstract_decision_round20_verification.md`.
