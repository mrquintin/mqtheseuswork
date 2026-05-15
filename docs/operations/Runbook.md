# Theseus / Noosphere — Operations runbook

Status: **descriptive, not aspirational.** Every job entry below is a job
that exists in code today. Every alert entry below is wired to a real
rule or a real dashboard signal. Procedures the firm has not actually
exercised are marked **untested — verify on first use**; that label is
not a failure of nerve, it is the honest pointer back to the meta-method
("you may not yet know what you think you know").

The complementary daily-workflow document is
[`docs/Operations_Manual.md`](../Operations_Manual.md). This file is
narrower and harder: what runs on a schedule, what alerts fire, what to
do in the first five minutes, and how to write a postmortem the firm
will actually re-read.

A consistency check ([`scripts/check_runbook_completeness.py`](../../scripts/check_runbook_completeness.py))
fails CI when a scheduled job in code is missing from this runbook, or a
runbook entry points at a file that no longer exists. Drift between
code and this document is therefore a build failure, not a vibe.

---

## How to read this runbook

Each job has the same six fields. Be precise; "roughly 10 minutes" is
not a wall time, "$0–5" is not a cost.

| Field | What it means |
|-------|---------------|
| **Source** | The file the job lives in. `path/to/file.py` or `.github/workflows/*.yml`. Consistency check verifies it exists. |
| **Schedule** | Either a cron expression (UTC) or a cadence description ("standing loop, 5-min cycle"). |
| **Owner** | The human who fixes it when it breaks. Defaults to Michael while the firm has one operator; reassign on rotation. |
| **Expected wall time** | Typical end-to-end duration. Bracketed range is p10–p90 across the recent runs the firm has observed; **untested** when no production sample exists yet. |
| **Expected cost** | Dollar cost per run. CI minutes only → "$0 (CI minutes)". LLM/API spend → estimate; if not measured, say so. |
| **Alerts** | The alert rules and dashboard signals that fire when the job goes wrong. Link to the `### <alert-name>` block in the Alert response section. |
| **Recovery** | First-five-minute response and re-run procedure. Cite the exact CLI command or workflow re-dispatch path. |

Each alert has the same five fields: **Trigger**, **Severity**,
**Probable cause**, **First-five-minute response**, **Escalation**. The
trigger always names the **span attribute** or **metric** the rule
reads, so an operator can confirm the signal at the source rather than
trust the dashboard's framing.

---

## Job catalog

### qh-benchmark

- **Source:** `.github/workflows/qh_benchmark.yml`
- **Schedule:** `30 6 * * *` (nightly 06:30 UTC). Also runs on PRs that
  touch benchmark code and on pushes to `main`.
- **Owner:** Michael
- **Expected wall time:** ~8–15 min (CI-side; pinned `QH_EMBEDDER_DIM=192`,
  `QH_SEED=0`)
- **Expected cost:** $0 (CI minutes only; key-free deterministic runner)
- **Alerts:** workflow failure surfaces in [`/ops/ci`](https://github.com/mrquintin/mqtheseuswork/tree/main/theseus-codex/src/app/(authed)/ops/ci);
  cross-run drift on the QH metric is itself an alert the firm reads as
  "we are losing our own thesis" — see [`#qh-benchmark-regression`](#qh-benchmark-regression).
- **Recovery:**
  1. Read the run page; the workflow uploads `metrics_*.json` and
     `results_*.json` for the failing baseline.
  2. Reproduce locally: `cd noosphere && QH_EMBEDDER_DIM=192 QH_SEED=0
     python -m noosphere.cli benchmark qh --runner cosine --json`.
  3. If leakage is reported (`n_leaks > 0`), inspect the
     `leakage_report.json` artifact and patch the bench config, not the
     runner.
  4. Re-dispatch via the workflow's `workflow_dispatch` trigger after
     fix.
  5. Update `theseus-codex/public/qh-benchmark/` only by re-running the
     workflow; do not hand-edit the leaderboard JSON.

### nightly-replication

- **Source:** `.github/workflows/nightly_replication.yml`
- **Schedule:** `15 7 * * *` (nightly 07:15 UTC, staggered against qh-benchmark)
- **Owner:** Michael
- **Expected wall time:** ~15–22 min (deterministic env:
  `PYTHONHASHSEED=0`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`,
  `OPENBLAS_NUM_THREADS=1`, `THESEUS_CROSS_MODEL_BUDGET=50`)
- **Expected cost:** $0 (CI minutes only; smoke target is key-free)
- **Alerts:** workflow failure; baseline diff failure when
  `replication/baselines/qh-benchmark` exists.
- **Recovery:**
  1. Failed `replication.lib.verify` step → diff is a numerical
     regression. Pull the `replication_envelope.json` and `metrics_*.json`
     artifacts.
  2. Reproduce locally: `cd replication && make smoke
     RUN_ROOT=$PWD/runs`.
  3. If the regression is real, **do not** roll the baseline; open a
     branch, investigate, file an [open question](../../docs/operator/CURRENTS.md)
     if you can't pin it down in one sitting.
  4. To intentionally re-baseline: commit the new
     `replication/baselines/qh-benchmark` directory in a PR titled "Roll
     replication baseline: <reason>". Untested — verify on first use.

### load-test-nightly

- **Source:** `.github/workflows/load_test_nightly.yml`
- **Schedule:** `0 7 * * *` (nightly 07:00 UTC, "viral" profile against
  staging). Spike profile is **manual dispatch only** because it can
  saturate upstream rate limits.
- **Owner:** Michael
- **Expected wall time:** ~6–10 min for viral; ~3–5 min for spike's
  sub-30s ramp window plus drain.
- **Expected cost:** $0 (CI minutes only — third-party APIs are mocked
  per the prompt-45 constraint).
- **Alerts:** workflow failure; pass criteria `p50 < 1.0s`, `p95 < 3.0s`,
  `error_rate < 1.0%`, no DB pool exhaustion. See
  [`#load-test-failure`](#load-test-failure).
- **Recovery:**
  1. Read `tests/load/results/*.json` from the failing run's artifacts.
  2. Identify the failing profile and the failed criterion (p50, p95,
     error rate, pool).
  3. Reproduce against the same preview URL:
     `PROFILE=viral PYTHONPATH=. python tests/load/article_viral.py
     --base-url <staging-url>`.
  4. A failed nightly **does not** block deploy by default; a failed
     preview run (`load_test_preview.yml`) does. To override a preview
     failure, the dispatcher sets `override_reason` on re-dispatch —
     this is logged as policy.
  5. Cross-check at `/ops/load` for trend; one bad night is not a
     regression, three is.

### redteam-tournament

- **Source:** `.github/workflows/redteam_tournament.yml`
- **Schedule:** `15 4 * * 1` (weekly, Monday 04:15 UTC)
- **Owner:** Michael
- **Expected wall time:** ~20–28 min CI side; archive write to
  `noosphere_data/redteam_tournament/archive/`
- **Expected cost:** ~$0 in CI (provider keys are optional; the offline
  deterministic driver is used when keys are missing). Live keys move
  this to several dollars per run when enabled.
- **Alerts:** workflow failure; drift in tournament scores across runs
  feeds the [drift detector](#drift-scheduler-failure).
- **Recovery:**
  1. Tournament artifacts: `theseus-codex/public/redteam/latest.json`
     and the per-run `tournament-*.json` in
     `noosphere_data/redteam_tournament/archive/`.
  2. Reproduce: `./noosphere/scripts/run_redteam_tournament.sh`.
  3. After a successful re-run, [`#agreement-model-retraining`](#agreement-model-retraining)
     should be triggered because the tournament corpus is its training
     input.

### noosphere-process-uploads

- **Source:** `.github/workflows/noosphere-process-uploads.yml`
- **Schedule:** `*/10 * * * *` (every 10 minutes). Also fires on
  `repository_dispatch` from the Codex upload route.
- **Owner:** Michael
- **Expected wall time:** ~10–30s when the queue is empty; ~30s–4min
  per queued upload otherwise.
- **Expected cost:** small per-upload spend (LLM extract, embed). Empty
  passes are CI minutes only.
- **Alerts:** workflow failure (consecutive failures triple the upload
  backlog quickly). Also covered by the in-flight stall signal on
  `/ops?panel=observability`.
- **Recovery:**
  1. List the failing run's logs. Most failures are upstream LLM/embed
     rate limits.
  2. To process a specific upload after a failure, use the manual
     dispatch with `upload_id`.
  3. To catch up after a long outage, leave the cron to drain (it
     processes the queue head per run). For a same-minute drain, queue
     several `workflow_dispatch` runs.
  4. Confirm `Upload.status` transitions in the Codex Prisma DB; stuck
     `processing` rows older than 30 min indicate a worker that lost
     its lock — restart via dispatch.

### public-publishing

- **Source:** `.github/workflows/public-publishing.yml`
- **Schedule:** `*/30 * * * *` (every 30 minutes)
- **Owner:** Michael
- **Expected wall time:** untested — verify on first use. The
  workflow's own `timeout-minutes: 45` is the upper bound, not the
  expectation.
- **Expected cost:** $0 (export + static build).
- **Alerts:** workflow failure. Failure here means the public
  `theseus-public/content/published.json` is stale.
- **Recovery:** untested — verify on first use. Confirm
  `THESEUS_ZENODO_TOKEN` and `THESEUS_PUBLIC_SITE_URL` are present on
  the deploy; re-dispatch.

### decay-scheduler

- **Source:** `noosphere/noosphere/decay/scheduler.py`
- **Schedule:** Standing loop / cron-driven (run via the noosphere CLI,
  typically nightly). Budget cap `budget_per_run=50` by default.
- **Owner:** Michael
- **Expected wall time:** untested — verify on first use. Hard cap is
  `budget_per_run` revalidations.
- **Expected cost:** per-call LLM revalidation (depends on the gate
  configuration). Bounded by `budget_per_run`.
- **Alerts:** thrashing detector escalations (`_escalate_to_human`); no
  webhook today — escalations appear in process logs.
- **Recovery:**
  1. Inspect process logs for `[escalation]` entries; each names the
     `object_id` and the count of thrashes within the window.
  2. Re-run a single object via `python -m noosphere decay
     revalidate --object-id <id>`.
  3. Lower `budget_per_run` if the host is overcommitted.
  4. Untested — verify on first use under sustained drift conditions.

### retention-runner

- **Source:** `noosphere/noosphere/decay/retention_runner.py`
- **Schedule:** Nightly survey, **confirm-to-execute** by default.
  Auto-execute is opt-in per policy.
- **Owner:** Michael
- **Expected wall time:** seconds for the survey; minutes-to-hours if
  bulk archive/delete is confirmed.
- **Expected cost:** $0 (local filesystem and DB operations).
- **Alerts:** missed daily confirmation does **not** silently
  auto-execute on day 2 (`retention_policies.py` enforces this).
  Visual: pending-action count at `/ops/retention`.
- **Recovery:**
  1. Open `/ops/retention`. Each policy's preview is rebuilt on page
     load; a stale preview means the previous day was not confirmed,
     which is acceptable.
  2. Confirm or cancel each policy row. The runner re-surveys before
     execution.
  3. To inspect the DSR handler, run `python -m noosphere decay dsr
     --identifier <email>` (untested — verify on first use).

### self-critique-scheduler

- **Source:** `noosphere/noosphere/peer_review/scheduler_self_critique.py`
- **Schedule:** Quarterly (default `DEFAULT_FRESHNESS_THRESHOLD_DAYS=90`).
  Invoked manually or via cron-driven shell.
- **Owner:** Michael
- **Expected wall time:** O(published articles) × per-article reviewer
  cost. Untested — verify on first use against the corpus this firm
  has.
- **Expected cost:** depends on the configured reviewer mix. The
  scheduler does not bypass the swarm budget.
- **Alerts:** findings land in the unified attention queue at high
  severity; no dedicated webhook.
- **Recovery:**
  1. Confirm there is a published-article iterable feeding the
     scheduler (the codex export or a CLI list).
  2. Re-run the scheduler for a single article via the in-process
     scheduler API; do not bulk-re-run quietly.
  3. Findings that block on missing evidence callbacks are recorded as
     no-op runs in logs — this is expected when evidence retrieval is
     not wired up.

### coherence-scheduler

- **Source:** `noosphere/noosphere/coherence/scheduler.py`
- **Schedule:** Ingest-time (per new proposition); a legacy
  pair-evaluation path remains. Not time-scheduled in the cron sense
  but listed here because operators reach for it during incidents.
- **Owner:** Michael
- **Expected wall time:** per-ingest; sub-second when the locality
  index hits cache.
- **Expected cost:** local compute + (optional) LLM judge. The default
  `_NoExternalLLMClient` short-circuits any ambient API-key use.
- **Alerts:** none configured; failures surface in ingest logs.
- **Recovery:**
  1. If coherence reports stop being produced after an ingest,
     check the domain-locality index (`DomainLocalityIndex`) — corrupt
     index forces a rebuild.
  2. The memoized config hash means a re-ingest with the same
     methodology will not recompute; bump `THESEUS_COHERENCE_CONFIG`
     to force a fresh pass.

### social-scheduler

- **Source:** `noosphere/noosphere/social/scheduler.py`
- **Schedule:** Weekly digest cadence (also immediate for firm-wide
  major events, monthly for opted-in subscribers).
- **Owner:** Michael
- **Expected wall time:** seconds (intake + digest build); the codex
  app does the mail send.
- **Expected cost:** $0 (no third-party telemetry mail vendor).
- **Alerts:** none configured. Failure is visible as an empty outbox
  on the codex side.
- **Recovery:**
  1. Verify the intake JSON exists at the configured path; the
     scheduler is JSON-in/JSON-out.
  2. Re-run the scheduler with an explicit intake path.
  3. Untested — verify on first use after a subscriber-list import.

### drift-scheduler

- **Source:** `noosphere/noosphere/evaluation/scheduler_drift.py`
- **Schedule:** Nightly, alongside the decay scheduler. Idempotent by
  deterministic event ID — re-running on the same window does not
  create duplicate `DriftEvent` rows.
- **Owner:** Michael
- **Expected wall time:** seconds per method; permutation tests are
  bounded by `DEFAULT_PERMUTATION_ITERATIONS`.
- **Expected cost:** $0 (local compute, no LLM).
- **Alerts:** drift events at 1.5σ warn, 2σ escalate, with hysteresis
  (two clean windows required to clear). Surfaced on `/methods`
  pages with a Drift column. See [`#drift-scheduler-failure`](#drift-scheduler-failure).
- **Recovery:**
  1. Drift events with `n < 8` resolutions are suppressed in the UI
     (insufficient data); a missing alert there is policy, not a bug.
  2. To re-evaluate one method: `python -m noosphere evaluation
     drift --method <name> --window 90` (untested — verify on first use).
  3. The seed (`DEFAULT_SEED`) is stored on each event for reproducibility.

### forecasts-scheduler

- **Source:** `noosphere/noosphere/forecasts/scheduler.py`
- **Schedule:** Standing loop. `./scripts/run-forecast-scheduler.sh
  loop` for the long-running form; `once` for cron-driven hosting.
- **Owner:** Michael
- **Expected wall time:** standing process; per-cycle latency
  depends on Polymarket/Kalshi ingest pacing.
- **Expected cost:** capped by `PersistentHourlyBudgetGuard`. Budget
  exhaustion is **expected** and does not error.
- **Alerts:** `BudgetExhausted` is logged and the loop sleeps until
  the next hour. Status path is `forecasts_status.json` — read by the
  health probe.
- **Recovery:**
  1. `./scripts/run-forecast-scheduler.sh status-only` refreshes the
     status file without running ticks.
  2. After a backfill batch, the scheduler auto-recomputes the public
     calibration manifest and per-method track record.
  3. Resume after a host restart: `./scripts/run-forecast-scheduler.sh
     loop`. The persistent budget guard remembers spend across
     restarts within the hour.

### currents-scheduler

- **Source:** `noosphere/noosphere/currents/scheduler.py`
- **Schedule:** Standing loop, `CYCLE_SECONDS=300` (5-minute cycle).
- **Owner:** Michael
- **Expected wall time:** standing process; per-cycle ≈ 5 min.
- **Expected cost:** budget-guarded; LLM opinion generation is the
  dominant cost.
- **Alerts:** none configured beyond budget exhaustion in logs.
  Backlog metric is the count of `OBSERVED`/`ENRICHED` events older
  than the configured window.
- **Recovery:**
  1. `./scripts/refresh-local-currents-runtime.sh` re-runs the
     ingest cycle once.
  2. Per `docs/operator/CURRENTS.md`, the operator deliberately reads
     opinions in a session, not as a feed — backlog is not, in itself,
     an incident.

### method-metrics-rollup

- **Source:** `noosphere/noosphere/observability/db.py`
  (`run_ops_rollup`). Invoked by the nightly track-record job from
  prompt 02.
- **Schedule:** Nightly (window default 24h).
- **Owner:** Michael
- **Expected wall time:** seconds — it scans spans for the window and
  upserts `MethodMetric` rows.
- **Expected cost:** $0 (DB-only).
- **Alerts:** the rollup itself **emits** alerts via
  `evaluate_alerts(metrics, DEFAULT_RULES)`. See
  [`#method_error_rate_high`](#method_error_rate_high) and
  [`#method_p95_slow`](#method_p95_slow).
- **Recovery:**
  1. Empty rollup table with non-empty `Span` table → the rollup
     never ran. Invoke `python -c "from
     noosphere.observability.db import run_ops_rollup;
     print(run_ops_rollup())"`.
  2. `errors` field of `OpsRollupReport` names the failed step.
  3. Spans older than the retention window (30 days default) have
     already been aggregated and purged; the rollup is the durable
     record from that point on.

### resolution-backfill

- **Source:** `noosphere/noosphere/forecasts/resolution_backfill.py`
- **Schedule:** Invoked by the forecasts scheduler after market
  resolution polls; also runnable manually via `python -m
  noosphere.cli forecasts backfill-resolutions [--venue
  polymarket|kalshi|all] [--since DATE] [--dry-run]`.
- **Owner:** Michael
- **Expected wall time:** seconds per backfilled resolution.
- **Expected cost:** venue API quota; honored by the existing
  forecast budget cap. Partial completion is acceptable; the next
  run resumes.
- **Alerts:** `ResolutionMismatch` rows surface in the codex
  `/forecasts` page when the venue's resolution date is >7 days from
  the forecast's `target_date`. No webhook configured.
- **Recovery:**
  1. Dry-run first: `--dry-run` prints what would be written.
  2. To override a venue resolution, file a `ResolutionOverride`
     row with reason, citation, and founder id. Do **not** overwrite
     an existing `ForecastResolution`; create a `ResolutionRevision`.
  3. Discrepancies are auditable; resolve in the codex UI, do not
     silently delete the mismatch row.

### principle-distillation

- **Source:** `noosphere/noosphere/distillation/principle_distillation.py`
- **Schedule:** Re-derivation cadence (manual or cron-driven via
  `python -m noosphere distillation rederive`). Updates draft
  principles when a cluster has shifted.
- **Owner:** Michael
- **Expected wall time:** untested — verify on first use. Bounded by
  the size of the firm-tier conclusion corpus.
- **Expected cost:** one LLM call per cluster for candidate text
  generation.
- **Alerts:** none configured. Stale principles surface in
  `/principles/queue` for triage.
- **Recovery:**
  1. The re-derivation returns counts:
     `{inserted, deleted_stale, draft, ...}`. A run with
     `deleted_stale > 0` and `inserted == 0` indicates a real
     contraction of the principle index — review the deleted set
     before re-running.
  2. To roll back a stale-delete: principles are re-derivable from
     their underlying conclusions; the bookkeeping is recoverable
     but the founder review history is not. Treat stale-deletes as
     auditable.

### agreement-model-retraining

- **Source:** `noosphere/scripts/train_agreement_model.sh`
- **Schedule:** After each `redteam-tournament` run (the tournament
  corpus is the training input). Also runnable on demand.
- **Owner:** Michael
- **Expected wall time:** ~30–90s on the v1 bench (deterministic
  driver, no live provider calls).
- **Expected cost:** $0 in the deterministic path; live-key runs are
  bounded by the same budget guard as the tournament.
- **Alerts:** held-out skill below the baseline is logged
  ("DOES NOT beat the baseline — treat as noise"); the model still
  writes but the dashboard widget flags low/no skill.
- **Recovery:**
  1. Re-run: `./noosphere/scripts/train_agreement_model.sh`.
  2. Artifacts: `noosphere_data/agreement_model/model.json` +
     `calibration_history.jsonl` (append-only) +
     `predictions/<conclusion_id>.json` per bench item.
  3. The existing method-drift detector watches
     `reviewer_agreement_model` via `drift_resolutions.jsonl`. A
     drift warning there is the firm's signal that the agreement
     model itself is decaying.

---

## Alert response

Each alert names the **span attribute** or **metric** the rule reads.
That is the source of truth — the dashboard's color is a projection,
the attribute is the data.

### method_error_rate_high

- **Trigger:** `AlertRule(name="method_error_rate_high", metric="error_rate",
  threshold=0.05, window_minutes=15, min_samples=5)` in
  `noosphere/noosphere/observability/metrics.py`.
- **Span attribute:** derived from `Span.status == SpanStatus.ERROR`
  over completed spans in the rollup window, grouped by `Span.name`.
  See `rollup_method_metrics` in
  `noosphere/noosphere/observability/metrics.py`. The alert reads
  `MethodMetrics.error_rate`.
- **Severity:** **high.** Sustained error rate over 5% on any method
  with at least 5 samples in 15 min is not a flake; it's a feature
  failing.
- **Probable cause:** upstream API outage (OpenAI / Anthropic / Voyage
  / Polymarket / Kalshi); recent code change to the method; a credential
  rotation that missed a deploy.
- **First five minutes:**
  1. `/ops?panel=observability` → "Recent alerts" row identifies the
     method.
  2. Open a recent failed trace from "Recent traces" (filter to
     `status=error`). The flame graph shows the failing span; click
     to read `error_kind` and `error_message` (PII-sanitized).
  3. If `error.kind` is a vendor SDK exception (e.g. `RateLimitError`,
     `APIConnectionError`), the cause is upstream — drop traffic by
     pausing the relevant scheduler (`forecasts`, `currents`) or
     leave the cron-only workflows to drain.
  4. If `error.kind` is a Python `TypeError` / `ValueError`, the cause
     is in our code — bisect to the last deploy that touched the
     method's module.
- **Escalation:** if upstream-caused and sustained > 1 hour, file a
  note on the relevant integration's status page and pause the
  affected job. If in-code, revert the offending commit and file a
  postmortem (see `postmortems/_template.md`).

### method_p95_slow

- **Trigger:** `AlertRule(name="method_p95_slow", metric="p95_ms",
  threshold=30_000.0, window_minutes=15, min_samples=5)` in
  `noosphere/noosphere/observability/metrics.py`.
- **Span attribute:** derived from `Span.duration_ms`
  (`Span.end - Span.start`) over completed spans grouped by
  `Span.name`. The alert reads `MethodMetrics.p95_ms`.
- **Severity:** **medium.** 30s p95 latency on a single method
  is enough to back the queue up; it is not yet user-visible failure.
- **Probable cause:** an external API has slowed (look at
  `external.{provider}` spans, attribute `latency_ms` and
  `retry_count`); a vector index / DB query is no longer hitting
  cache; a hot-path function lost its `sample_rate` (every call now
  emits a span and the latency is real, not measurement overhead).
- **First five minutes:**
  1. From the alerts row, drill into the method's recent traces.
  2. In a slow trace, expand the longest child span. If it is an
     `external.{provider}` span, the cause is upstream; check
     `retry_count` and `status_code`.
  3. If the longest child is internal, compare against the same
     method's traces from yesterday in the per-method latency
     trendline.
  4. For database calls, check connection-pool saturation
     (`prisma:engine` spans, when present).
- **Escalation:** if p95 stays > 30s for > 1 hour and the cause is
  upstream, throttle the scheduler that issues those calls and
  document the upstream incident in a postmortem entry. If the cause
  is internal and persistent, file the regression and consider
  pausing the affected job.

### cost-burndown-80pct

- **Trigger:** dashboard signal — when the 24h cost ratio
  `spentUsd / budgetUsd` exceeds 0.80, the burndown bar on
  `/ops?panel=observability` switches from gold to ember
  (`ops/page.tsx` `burnPct > 80`). Not a configured `AlertRule` —
  the rollup table has the data, the threshold lives in the UI.
- **Span attribute:** `Span.attrs["cost_usd"]` summed by
  `external.{provider}` spans (the LLM wrappers tag it; see
  `rollup_method_metrics` cost accumulation).
- **Severity:** **medium.** Hitting 80% of budget is not yet failure
  but is the last warning before the hourly budget guard begins to
  refuse calls (`BudgetExhausted`).
- **Probable cause:** a self-critique pass or red-team tournament
  was run live (with provider keys) outside the usual cadence; a
  forecast-resolution backfill is processing a large catch-up;
  upstream pricing rose and the budget table is stale.
- **First five minutes:**
  1. Open `/ops?panel=observability` → "Method latency · last 7 days".
     Sort by Cost. The top method is responsible.
  2. Identify whether the cost is from a scheduled job (expected) or
     a one-off manual run (investigate).
  3. If manual, stop the source and let the hour roll over.
- **Escalation:** sustained breach across multiple hours: pause the
  responsible scheduler (`forecasts-scheduler` standing loop has the
  largest live spend). Update the budget table in
  `forecasts/budget.py` only with a written justification.

### in-flight-stall

- **Trigger:** dashboard signal — traces with `Span.end is None`
  (`is_open == True`) older than ~10 minutes appear under
  "In flight" on `/ops?panel=observability`. There is no configured
  `AlertRule`; the metric is `listInFlightTraces().length` and the
  age comes from `Span.start`.
- **Span attribute:** `Span.start` (unix epoch UTC) and
  `Span.end` (None while open).
- **Severity:** **medium**, escalating to **high** if more than five
  stalls accumulate.
- **Probable cause:** a worker crashed mid-trace and the span was
  never closed; an async task was cancelled outside the span's
  `try/finally`; the upload queue is backed up and `processUpload`
  has a stuck row.
- **First five minutes:**
  1. Click the stalled trace; the open span names the function that
     never returned.
  2. For uploads, check the codex `Upload.status` column for stuck
     `processing` rows older than 30 min.
  3. Re-dispatch `noosphere-process-uploads.yml` for that
     `upload_id`.
  4. Open traces with no matching pid / worker liveness indicate
     a crashed process — span recorder will not close them itself.
- **Escalation:** if more than three stalls clear themselves on the
  next worker cycle, the cause is recoverable. If they persist past
  one cycle, file a postmortem; orphaned spans are evidence the
  framework is leaking.

### qh-benchmark-regression

- **Trigger:** `qh-benchmark` workflow non-zero exit, **or** the
  workflow succeeds but the leakage validator reports `n_leaks > 0`.
- **Span attribute:** N/A — this is a CI signal, not a span signal.
  The artifacts (`leakage_report.json`, `metrics_*.json`) are the
  source.
- **Severity:** **high.** The firm publishes this leaderboard; a
  silent regression here is the firm losing its own thesis without
  noticing.
- **Probable cause:** a change to the benchmark code, a change to
  the embedder/seed pin, a contaminated bench item that introduced
  leakage.
- **First five minutes:**
  1. Read the workflow logs from `/ops/ci`.
  2. Pull `leakage_report.json` from the run artifacts. Any
     `n_leaks > 0` is a hard fail.
  3. Reproduce locally: `cd noosphere && QH_EMBEDDER_DIM=192
     QH_SEED=0 python -m noosphere.cli benchmark qh --validate
     --json`.
- **Escalation:** never silently re-leaderboard. Revert the
  offending commit, regenerate `theseus-codex/public/qh-benchmark/`
  from a known-good run, file a postmortem.

### load-test-failure

- **Trigger:** `load_test_nightly.yml` or `load_test_preview.yml`
  exits non-zero. The pass criteria are encoded in the harness:
  `p50 < 1.0s`, `p95 < 3.0s`, `error_rate < 1.0%`, no DB connection-
  pool exhaustion.
- **Span attribute:** N/A on the CI side. The runtime observability
  spans for the public API surface the same metrics under
  `Span.name == "api.public.*"` — cross-reference against
  [`#method_p95_slow`](#method_p95_slow) when investigating.
- **Severity:** **medium** for nightly viral; **high** for preview
  (preview blocks deploy). Spike failures are dispatcher-acknowledged
  via `override_reason`.
- **Probable cause:** Vercel preview cold-start jitter; a new public
  API route without a cache header; a synchronous DB call that
  should be async; a missing index on a public table.
- **First five minutes:**
  1. Open the failed run's `tests/load/results/*.json` artifact.
  2. Identify the failing percentile and the slowest route.
  3. Hit the route manually with `curl` against the preview URL to
     confirm the slowness is repeatable.
  4. For preview failures: do not override blindly; require a one-line
     reason on the dispatch.
- **Escalation:** trend the failure on `/ops/load`. One bad night is
  not a regression; three is. Persistent preview failures block the
  deploy until resolved.

### drift-scheduler-failure

- **Trigger:** the nightly drift evaluation produces a `DriftEvent`
  at 2σ for an active method (`method_drift_policies.escalate`).
  Also fires on workflow/process errors in
  `evaluation/scheduler_drift.py`.
- **Span attribute:** N/A directly; the signal is `DriftEvent.severity`
  in the codex DB. Cross-link: when MQS Severity is downweighted for
  a drifted method, the conclusion's `MQS.severity_note` records the
  penalty.
- **Severity:** **high** at 2σ escalate; **medium** at 1.5σ warn.
- **Probable cause:** regime change (the method's edge has
  saturated); upstream model upgrade silently changed embedding
  semantics; the method's resolutions are no longer i.i.d. with its
  baseline.
- **First five minutes:**
  1. `/methods/<name>` → Drift panel shows the calibration trend
     chart and the alert history.
  2. Check the seed (`DEFAULT_SEED`) on the event; re-run the
     permutation test with the same seed to confirm.
  3. Confirm `n >= 8` resolutions — events below that threshold
     should have been suppressed; finding one is itself a bug.
- **Escalation:** at 2σ sustained over two windows, file a
  postmortem and open the question of retiring or revising the
  method. Hysteresis is intentional — do not clear the alert until
  two clean windows.

---

## Quarterly drill

The drill is the meta-method applied to the runbook itself. Once a
quarter, pick three alerts at random, walk the procedure as written,
and log every place the procedure was wrong, vague, or missing.

`scripts/operations_drill_candidates.py` prints a drill sheet:

```bash
python scripts/operations_drill_candidates.py --count 3 [--seed 17]
```

It selects from the `### <alert-name>` entries under "Alert response",
prints the trigger and first-five-minute response for each, and
includes blank "Gap log" lines for the operator to fill in. The seed
is recorded so a drill is reproducible (and so two operators can run
the same drill independently).

**Drill protocol**:

1. Run the candidate script with no seed. Record the seed it picks.
2. For each of the three alerts, **without re-reading the runbook**,
   walk what you would do in the first five minutes. Write it down.
3. Compare your walk to the runbook entry. Log gaps: the runbook said
   X; you would have done Y; which is right?
4. File the drill as a postmortem under `docs/operations/postmortems/`
   with type `drill`. This is the only postmortem that is not about
   an incident, but it lives in the same place because the firm's
   methodological commitment is that practice is auditable.

**Gap categories** (use these as labels in the postmortem):

- `untested` — the procedure is correct but had never been run; the
  drill is the first run.
- `stale` — the procedure refers to a file, command, or attribute
  that no longer exists.
- `vague` — the procedure is correct in spirit but underspecified at
  step N.
- `missing` — the procedure for the relevant case is not present at
  all.

---

## Cross-links

- [`/ops`](https://github.com/mrquintin/mqtheseuswork/tree/main/theseus-codex/src/app/(authed)/ops) —
  operator dashboard. Recent-alerts rows link directly to alert entries
  in this runbook.
- [`/ops/ci`](https://github.com/mrquintin/mqtheseuswork/tree/main/theseus-codex/src/app/(authed)/ops/ci) —
  CI health (Round 18 prompt 08). Workflow rows correspond to the
  job entries above; click through to GitHub for run logs.
- [`/ops/load`](https://github.com/mrquintin/mqtheseuswork/tree/main/theseus-codex/src/app/(authed)/ops/load) —
  load-test trend; companion to [`#load-test-failure`](#load-test-failure).
- [`/ops/retention`](https://github.com/mrquintin/mqtheseuswork/tree/main/theseus-codex/src/app/(authed)/ops/retention) —
  retention preview / confirm; companion to
  [`#retention-runner`](#retention-runner).
- [Postmortem template](postmortems/_template.md) — every incident
  ends here.
- [Daily operations manual](../Operations_Manual.md) — record→upload→
  read advisor flow; this runbook is the failure-mode complement.
