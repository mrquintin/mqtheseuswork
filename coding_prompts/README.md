# Round 15 — Currents Inversion + Coherence at Scale

Active batch created 2026-05-07 from a transcript with two thrusts:

1. The X-card on Currents has white corners; the Currents pipeline runs
   backwards (KB-anchored discovery should be event-anchored discovery
   with a KB-relevance gate, weighted by post significance).
2. Noosphere's coherence test is O(n) over the corpus and will not survive
   growth. Replace with a domain-locality ANN gate plus a
   contradiction-direction probe (per the geometry-of-contradiction
   research already in the repo).

The prior methodology batch (Round 14) is archived under
`archive_round14_methodology_implemented/` — the audit script reports
every declared scope file exists for all eight of those prompts.

The active runnable batch is exactly the top-level numbered prompt set:

1. `01_x_post_corner_cosmetic.txt` — eliminate white corners on the X embed
2. `02_x_significance_metrics_capture.txt` — capture public_metrics from X
3. `03_currents_pipeline_inversion.txt` — discovery first, KB relevance second
4. `04_currents_opinion_uses_inverted_flow.txt` — opinion generator follows the inversion
5. `05_noosphere_domain_locality_index.txt` — ANN locality index for coherence
6. `06_noosphere_contradiction_geometry_probe.txt` — predicted-direction probe
7. `07_scaled_coherence_check_integration.txt` — wire the scaled pipeline in
8. `08_production_database_migration_runner.txt` — re-issue the Round 11 gap
9. `09_verification_and_regression.txt` — single regression pass + report

`run_prompts.sh` discovers only top-level `coding_prompts/[0-9][0-9]_*.txt`
files. It does not descend into `_paused/`, `archive_round*/`, or any other
subdirectory.

## Run

```bash
cd /Users/michaelquintin/Desktop/Theseus
./run_prompts.sh
```

Useful filters:

```bash
./run_prompts.sh --dry-run
./run_prompts.sh --from 4
./run_prompts.sh --to 6
./run_prompts.sh --from 2 --to 6
./run_prompts.sh --only 06
./run_prompts.sh --model gpt-5.3-codex
./run_prompts.sh --continue
```

The runner uses the OpenAI Codex CLI login/subscription path (`codex exec`),
NOT an OpenAI API key. It scrubs `OPENAI_API_KEY`, `OPENAI_AUTH_TOKEN`,
`OPENAI_BASE_URL`, `OPENAI_ORG_ID`, and `OPENAI_PROJECT` before each Codex
invocation so a Cursor terminal with stale API-key vars still uses the
Codex CLI login path. Every Codex session streams to the terminal and is
captured at `.codex_runs/<timestamp>_<prompt>.log`.

Each prompt instructs Codex to inspect current code and tests first, verify
already-landed work, and make only necessary repair edits. Reruns are
intended to be idempotent.

## Audit

```bash
python3 coding_prompts/_audit_implementation.py
```

Inter-prompt dependencies (worth knowing if you re-order):

- 03 depends on 02 (significance score)
- 04 depends on 02 + 03
- 06 depends on 05 (locality index)
- 07 depends on 05 + 06
- 09 depends on 01–08

## Triage notes from the audit run on 2026-05-07

The audit reported four NOT_IMPLEMENTED entries inside archive folders.
After inspection:

- `archive_round10/01_forecasts_design_brief.txt` — design doc was created
  at `archive_round10/FORECASTS_DESIGN.md`. False negative; left archived.
- `archive_round9/01_diagnose_aborted_codex_run.txt` —
  `archive_round9/ABORTED_RUN_DIAGNOSIS.md` exists. False negative.
- `archive_round9/03_merger_plan_and_collision_audit.txt` —
  `archive_round9/MERGER_PLAN.md` exists. False negative.
- `archive_round11_originals/02_production_database_migration.txt` —
  `scripts/migrate_production.sh` does NOT exist. Genuine gap.
  Re-issued as prompt 08 in this batch.

## Archives

- `archive_round14_methodology_implemented/` — the previous active batch.
- `archive_round13_conversation_geometry_implemented/` — the batch before that.
