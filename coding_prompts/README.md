# Round 17 — Methodology Operationalization, Empirical Validation, and Public Surface Maturation

Active batch authored 2026-05-08. Round 16 is archived under
`archive_round16_public_ux_implemented/` (audit confirmed all ten
prompts effectively implemented; prompt 02's PARTIAL verdict was a
deletion-as-success false negative — `theseus-codex/src/app/responses/`
no longer exists, which is what 02 asked for).

This round's central thesis: Theseus has reoriented around methodology
as product. The artifacts that operationalize that reorientation are
mostly missing. Round 17 builds them. The 50 prompts cluster into nine
themes:

1. **Methodology operationalization (01–07)** — turn the five working
   criteria from THE_META_METHOD into a per-conclusion Methodology
   Quality Score; link methods to outcomes; failure-mode catalogs;
   drift detection; method composition graph; declarative domain
   bounds; a public methodology explorer worthy of being the firm's
   flagship surface.
2. **Quintin Hypothesis empirical validation (08–11)** — a frozen
   benchmark, a cross-model study, an honest Householder-reflection
   ablation, a one-command replication harness.
3. **Calibration & truth-tracking loop (12–15)** — a public
   calibration scorecard, resolution backfill across venues,
   calibration-aware confidence display, counterfactual method
   replay.
4. **Belief revision and lineage (16–17)** — an actual revision
   engine with minimum-distance plans, conclusion lineage as a
   first-class navigation surface.
5. **Source provenance and trust (18–20)** — retraction propagation,
   a source-credibility ledger, citation-chain entailment validator.
6. **Adversarial / peer review strengthening (21–24)** — multi-model
   swarm, severity-weighted objections, a red-team tournament,
   geometry-based blindspot detection.
7. **Public intellectual capital surfaces (25–31)** — open questions
   engine, provenance heatmap, Currents dialectic, public inquiry
   search, paper auto-generator, signed authorship, response-dialog
   loop.
8. **Dialectic + UX excellence (32–38)** — speaker models, live
   argument map, unified founder dashboard, Explorer 2.0,
   keyboard-driven workspace, mobile public site, print views.
9. **Operational maturation (39–50)** — research subscriptions,
   principle distillation, Currents↔market edge linkage, methodology
   diffs, self-critique pass, observability spans, load tests, data
   retention, seasonal review, external-critique invitations,
   security hardening, and a final verification pass.

The active runnable batch is exactly the top-level numbered prompt set
01–50.

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
./run_prompts.sh --model claude-opus-4-6
./run_prompts.sh --continue
```

The runner uses the Claude Code CLI's existing login/subscription path
(`claude -p`), NOT an API key. It scrubs `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`,
`CLAUDE_CODE_USE_BEDROCK`, and `CLAUDE_CODE_USE_VERTEX` before each
invocation so a Cursor terminal with stale API-key vars still uses the
Claude Code CLI subscription path. Every session streams to the
terminal and is captured at
`.claude_code_runs/<timestamp>_<prompt>.log`.

Each prompt instructs Claude Code to inspect current code and tests
first, verify already-landed work, and make only necessary repair
edits. Reruns are intended to be idempotent.

`run_prompts.sh` discovers only top-level
`coding_prompts/[0-9][0-9]_*.txt` files. It does not descend into
`_paused/`, `archive_round*/`, or any other subdirectory.

## Audit

```bash
python3 coding_prompts/_audit_implementation.py
```

## Inter-prompt dependencies

The 50 prompts are arranged so that, in order, each only depends on
prompts before it. Selected dependencies worth knowing if you re-order:

- 02 depends on 01 (MQS + track record); 04 depends on 02; 05/06 depend
  on 01–04.
- 09, 10 depend on 08 (the QH benchmark dataset is the input).
- 12–15 are a calibration cluster: 13 backfills resolutions, 12
  publishes the scorecard, 14 layers recalibrated display, 15 enables
  counterfactual method replay.
- 17 depends on 16 (revision engine emits the lineage events the
  visualization renders).
- 18–20 are a source-trust cluster.
- 22 depends on 21 (severity scores roll up swarm output).
- 24 depends on 08 (geometric blindspots use the QH primitives).
- 27 depends on 24.
- 29 depends on 01, 02, 17 (paper generator pulls from MQS, track
  record, lineage).
- 30 sits underneath 38 + 47 (signed authorship is referenced by
  print exports and seasonal reviews).
- 50 must run last.

## Authoring philosophy

These prompts give direction, not code. They name the files to read,
the constraints to honor, the tests to write, and the SCOPE block
lists exact files to CREATE / MODIFY. The prompted agent is expected
to make real engineering judgments on internal structure, error
handling, naming, and dependencies — not to recover code from the
prompt.

## Archives

- `archive_round16_public_ux_implemented/` — Round 16 public-surface UX
  cleanup (nav home, founder portal rename, responses removal, article
  typography, Currents/Forecasts site theme, response email pipeline,
  publication cadence, regression).
- Earlier archives back through round3 contain the reasoning and
  deployment-infrastructure history of the firm.
