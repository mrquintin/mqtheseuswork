# Round 17 - Methodology Evaluation + Replication

Active batch created 2026-05-08. This batch turns the methodological
reorientation into measurable infrastructure: methodology quality
scores, method-to-outcome track records, explicit failure-mode catalogs,
drift detection, method composition graphs, domain applicability bounds,
a stronger public methodology explorer, and a reproducible benchmark
program for the Quintin Hypothesis / contradiction-geometry work.

The previous Round 16 public-surface UX batch is archived under
`archive_round16_public_ux_implemented/`. That archive includes the nav
cleanup, Responses removal, article typography cleanup, compact
firm-side sources, Currents citation popovers, Currents/Forecasts theme
cleanup, weekly publication cadence, and regression prompt.

The active runnable batch is exactly the top-level numbered prompt set:

1. `01_methodology_quality_score.txt` - operationalize the five
   criteria from `THE_META_METHOD.md` into a per-conclusion Methodology
   Quality Score.
2. `02_method_outcome_linkage.txt` - connect methods, conclusions,
   forecast predictions, and forecast resolutions into a measured track
   record.
3. `03_method_failure_mode_catalog.txt` - give every registered method
   a curated, machine-checkable failure-mode catalog.
4. `04_method_drift_detector.txt` - detect method-performance drift
   against historical baselines.
5. `05_method_composition_graph.txt` - model methods as a composition
   DAG and propagate risk through dependent methods.
6. `06_domain_applicability_bounds.txt` - make each method's domain of
   applicability explicit and enforceable.
7. `07_methodology_public_explorer.txt` - make `/methodology` a public
   explorer for methods, relationships, limits, failures, and evidence.
8. `08_quintin_hypothesis_benchmark.txt` - build a reproducible
   benchmark for contradiction geometry as an empirical claim.
9. `09_cross_model_geometry_study.txt` - stress-test the geometry claim
   across embedding models.
10. `10_householder_ablation.txt` - isolate the value of the
    Householder reflection step in the contradiction-geometry pipeline.
11. `11_replication_harness.txt` - provide a one-command replication
    harness for the benchmark, cross-model study, and ablation.
12. `12_calibration_scorecard_public.txt` - expose a public calibration
    scorecard for resolved forecasts and opinions.
13. `13_forecast_resolution_backfill.txt` - backfill forecast
    resolutions from Polymarket and Kalshi where upstream markets have
    resolved.
14. `14_calibration_aware_confidence.txt` - condition displayed
    confidence on the firm's observed calibration history.
15. `15_counterfactual_method_replay.txt` - replay past conclusions and
    resolved forecasts through alternative methods to compare skill
    against luck.
16. `16_belief_revision_engine.txt` - add a real belief-revision engine
    for minimal-distance revisions when new evidence contradicts
    existing conclusions.
17. `17_conclusion_lineage_visualization.txt` - expose a first-class
    lineage view from sources through methodology, review, revision,
    calibration, and publication.
18. `18_source_retraction_propagation.txt` - propagate retracted,
    corrected, disputed, or expired source standing through conclusions
    and public citations.
19. `19_source_credibility_ledger.txt` - maintain Bayesian credibility
    posteriors for cited sources as downstream claims resolve or fail.
20. `20_citation_chain_validator.txt` - verify that each citation
    actually supports the claim it is being used to support.

`run_prompts.sh` discovers only top-level
`coding_prompts/[0-9][0-9]_*.txt` files. It does not descend into
`_paused/`, `archive_round*/`, or any other subdirectory.

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

The runner uses the OpenAI Codex CLI login/subscription path
(`codex exec`), not an OpenAI API key. It scrubs `OPENAI_API_KEY`,
`OPENAI_AUTH_TOKEN`, `OPENAI_BASE_URL`, `OPENAI_ORG_ID`, and
`OPENAI_PROJECT` before each Codex invocation so a Cursor terminal with
stale API-key vars still uses the Codex CLI login path. Every Codex
session streams to the terminal and is captured at
`.codex_runs/<timestamp>_<prompt>.log`.

Each prompt instructs Codex to inspect current code and tests first,
verify already-landed work, and make only necessary repair edits.
Reruns are intended to be idempotent.

## Audit

```bash
python3 coding_prompts/_audit_implementation.py
```

Inter-prompt dependencies:

- 02 depends on 01.
- 04 depends on 02.
- 05 depends on 03 and 04.
- 06 depends on the locality/coherence primitives already introduced in
  Round 15 and should be reviewed after 01-05.
- 07 depends on 01-06 because it exposes their artifacts.
- 09 depends on 08.
- 10 depends on the current contradiction-geometry implementation and
  should be compared with the 08 benchmark outputs.
- 11 depends on 08-10.
- 12 depends on forecast resolution/calibration primitives already in
  the codebase and should align with 01.
- 13 depends on the venue clients and existing resolution tracker.
- 14 depends on 12 and the recalibration data it exposes.
- 15 depends on 01, 02, 12, and the existing temporal replay
  primitives.
- 16 depends on cascade graph traversal, temporal replay, and the
  existing relation vocabulary.
- 17 depends on 16 and the existing temporal replay surface.
- 18 depends on 16, 17, literature handling, and citation resolution.
- 19 depends on 18 and the existing source/citation models.
- 20 depends on 18, 19, citation resolution, and NLI scoring.

## Archives

- `archive_round16_public_ux_implemented/` - public-surface UX cleanup
  and publication cadence.
- `archive_round15_currents_and_coherence_implemented/` - Currents
  inversion, X significance metrics, noosphere coherence at scale,
  production migration runner.
- `archive_round14_methodology_implemented/` - methodology extraction.
- `archive_round13_conversation_geometry_implemented/` - conversation
  geometry.
