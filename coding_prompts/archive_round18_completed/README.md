# Round 18 — Consolidation, Empirical Execution, and Refined Excellence

Active batch authored 2026-05-08 immediately after Round 17 completed.
Round 17 added roughly 50 substantial features in parallel:
methodology operationalization, the QH benchmark, the calibration
loop, belief revision, source provenance, the adversarial swarm,
public surfaces, dialectic upgrades, observability, retention,
external critique, signing. The throughput was high; the entropy was
also high.

Round 18 has three jobs simultaneously:

1. **Stabilize** — schema audit, migration safety, API envelope
   unification, type alignment, module hierarchy, design system
   extraction, dead-code elimination, CI consolidation, naming
   convention enforcement, circular-dependency removal, config
   unification, observability completion (prompts 01–12).
2. **Run the experiments the prior round only built harnesses for**
   — QH benchmark, cross-model study, Householder ablation, red-team
   tournament, principle distillation, resolution backfill,
   self-critique, the first auto-paper (prompts 13–20).
3. **Refine the surfaces and depen the methodology** — methodology
   explorer v2, calibration scorecard v2, lineage v2, Currents
   dialectic quality, attention-queue signal, Explorer polish,
   provenance polish, print polish, public ask quality, mobile polish
   (prompts 21–30); aim-method-fit rubric, Bayesian belief layer,
   method retirement workflow, reviewer-agreement model, horizon
   calibration, cross-domain transfer study, severity rubric
   calibration (prompts 31–37).
4. **Document, validate, and open up** — single architecture document,
   RATIONALE drift repair, formal MQS spec, outside-reader onboarding,
   operations runbook, threat-model follow-up (38–43); critique pilot,
   replication outreach, first seasonal review, subscription cutover,
   methodology review week (44–48); accessibility review and final
   verification (49–50).

The active runnable batch is the top-level numbered prompt set
01–72. Prompts 01–50 are the original Round 18 batch; 51–72 are
the 2026-05-13 extension authored after the founder's product
voice-memo (bug fixes, principle-first knowledge refactor,
quantitative-from-principles bridge, equities portfolio
integration, UI critique-and-apply pair, PDF user guides, SaaS
template extraction with a VC preset, dev-workflow hardening,
voice-memo capture pipeline, and a final verification pass).

## Extension 51–72 — voice-memo product asks

### Wave A (extension) — Bug fixes
51. `51_published_article_rendering_bug.txt` — fix glitchy article rendering ("Real cost of growth" symptom); regression-test
52. `52_public_homepage_article_surfacing.txt` — published articles appear on the public homepage within 60s
53. `53_continuous_running_scheduler_stability.txt` — diagnose + fix the "continuous running is being weird" scheduler flakiness
54. `54_dashboard_terminology_and_cleanup.txt` — remove Attention box; clarify Snooze/Dismiss/Open-Question; fix Library button font

### Wave B (extension) — Performance + principle-first refactor
55. `55_performance_audit_and_remediation.txt` — site-wide perf audit + remediation with measured baselines and a CI bundle budget
56. `56_principle_first_claim_extraction.txt` — extractor emits PRINCIPLES (transferable decision rules), not first-person quotes
57. `57_principle_to_quantitative_bridge.txt` — every principle gets a structured quantitative-formalisation spec (metrics, tests, null)
58. `58_knowledge_dashboard_principle_first.txt` — Knowledge surfaces re-org around principles; conclusions become "evidence for/against"

### Wave C (extension) — Equities track
59. `59_stocks_portfolio_data_model.txt` — Equity instrument / signal / position / portfolio-state tables; shared eight-gate safety
60. `60_alpaca_paper_integration.txt` — Alpaca official API for paper trading + market data (primary equity broker)
61. `61_stocks_signal_generation_principle_grounded.txt` — equity signals must be grounded in firm principles, not technicals
62. `62_robinhood_live_adapter_optional.txt` — optional Robinhood live adapter, off-by-default, with ToS-risk banner
63. `63_unified_portfolio_dashboard.txt` — single `/portfolio` page across prediction markets + equities + decision-trace drawer

### Wave D (extension) — Long-tail
64. `64_quantitative_test_framework.txt` — runner that actually executes prompt 57's specs against real data, on cadence
65. `65_ui_critique_via_designer_persona.txt` — SV-chief-designer persona produces structured UI critique (READ-ME-FIRST gate)
66. `66_apply_ui_revision_plan.txt` — implementation pass that applies (or refuses) each revision from prompt 65
67. `67_pdf_user_guides.txt` — six pdflatex-built user guides covering every founder-facing surface
68. `68_theseus_template_extraction.txt` — separate `theseus-template/` repo for installing the platform in other organisations
69. `69_vc_preset_configuration.txt` — VC firm preset with `/deals` surface and principle-alignment table
70. `70_dev_workflow_branch_pr_private_audit.txt` — repo-privacy audit, optional branch-per-prompt mode, pre-commit test gate
71. `71_audio_capture_to_principle_pipeline.txt` — founder-only quick-record button → transcript → principle queue
72. `72_round18_extension_verification.txt` — final verification of prompts 51–71, regression report, README update

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
./run_prompts.sh --from 13 --to 20    # the empirical-execution block
./run_prompts.sh --only 50
./run_prompts.sh --model claude-opus-4-7
./run_prompts.sh --continue
```

The runner uses the Claude Code CLI's existing login/subscription
path (`claude -p`), NOT an API key. Streaming via `--output-format
stream-json --include-partial-messages --verbose`, rendered through
`format_stream_claude.py` so tool calls and partial text appear live.
Raw JSONL persists at
`.claude_code_runs/<timestamp>_<prompt>.raw.jsonl`; the human-readable
log is at `.claude_code_runs/<timestamp>_<prompt>.log`.

`run_prompts.sh` discovers only top-level
`coding_prompts/[0-9][0-9]_*.txt` files. It does not descend into
`_paused/`, `archive_round*/`, or any other subdirectory.

## Audit

```bash
python3 coding_prompts/_audit_implementation.py
```

## Inter-prompt dependencies

The 50 prompts are arranged so that, in order, each only depends on
prompts before it. Selected dependencies worth knowing if you reorder:

- 01 (schema audit) blocks 02 (migration safety), 04 (type
  alignment), and 33 (method retirement).
- 03 (API envelope) is referenced by 21 (methodology explorer v2),
  22 (calibration scorecard v2), 29 (public ask quality), 47
  (subscriptions).
- 05 (module hierarchy) inserts shims; later prompts use the new
  paths but the shims remain through the round.
- 06 (design system) supplies primitives consumed by every v2
  prompt (21–30) and by 49 (a11y).
- 12 (observability completion) depends on Round 17 prompt 44.
- 13 (QH benchmark run) provides results consumed by 14 (cross-
  model), 15 (ablation), 21 (methodology explorer v2), 38
  (architecture doc), 41 (reader guide), 46 (seasonal review).
- 18 (resolution backfill) provides numbers for 22 (scorecard v2),
  35 (horizon calibration), 46 (seasonal review).
- 19 (self-critique pass) provides findings for 25 (attention queue
  signal) and 46 (seasonal review).
- 20 (first auto-paper) consumes 13, 18, 17 outputs.
- 31 (aim-method fit) modifies the MQS scorer; 40 (formal MQS spec)
  must follow.
- 37 (severity calibration) gates on having sufficient labeled
  objections from the live system; cold-start gating is in the
  prompt itself.
- 44 (critique pilot) and 45 (replication outreach) produce drafts
  for the founder to send; they do not auto-contact anyone.
- 50 must run last.

## Authoring philosophy

These prompts give direction, not code. They name the files to read,
the constraints to honor, the tests to write, and the SCOPE block
lists exact files to CREATE / MODIFY. The agent is expected to make
real engineering judgments on internal structure, error handling,
naming, and dependencies — not to recover code from the prompt.

The empirical-execution prompts (13–20) are the firm's first real
test of whether the Round 17 infrastructure does what it claims.
They produce real numbers. The agent is expected to publish honest
results, including unflattering ones; flattering-only publication
is a failure mode the prompts call out by name.

The pilot/outreach prompts (44–48) involve outside parties. The
agent never contacts them automatically; it produces drafts and
target lists for the founder to send.

## Archives

- `archive_round17_methodology_implementation/` — Round 17 (methodology
  operationalization, QH benchmark scaffolding, calibration loop,
  belief revision, source provenance, adversarial swarm, public
  surfaces, dialectic upgrades, observability, retention, external
  critique, signing — the 50-prompt round that built the substrate
  Round 18 stabilizes and exercises).
- `archive_round16_public_ux_implemented/` — Round 16 public-surface
  UX cleanup.
- Earlier archives back through round3.

## Additional Isolated Batches

- `ui_ux_round19/` — a dedicated UI remediation batch from the 2026-05-11
  live path walk. It is intentionally not part of the top-level Round 18
  runner because the active 01-50 Round 18 prompts are still partial or
  not implemented by the audit script. Run with:

  ```bash
  ./coding_prompts/ui_ux_round19/run_prompts.sh
  ```

- `ui_ux_round20/` — a successor UI remediation batch from the later
  2026-05-11 live path walk. It focuses on operational clarity across
  dashboard, conclusion detail, Knowledge, audio transcripts, upload,
  Ask, Currents, Ops, and interaction performance, then extends into
  algorithmized market decision-making and founder-alpha Polymarket /
  Kalshi portfolio infrastructure. The later prompts add empirical
  case-study extraction, abstract principle transfer, and multi-frame
  game-theory-like decision traces. It also uses the Claude Code CLI
  subscription path, not an API key. Run with:

  ```bash
  ./coding_prompts/ui_ux_round20/run_prompts.sh
  ```

## Extension 51–72 (2026-05-13 → 2026-05-15)

Twenty-two prompts numbered 51–72 extend the top-level Round 18 batch
with the bug fixes, new surfaces, and integrations called out by the
2026-05-13 founder walk. Verification artefacts live at
`docs/verification/round18_ext_2026_05_13/` —
[manifest.md](../docs/verification/round18_ext_2026_05_13/manifest.md)
records per-file deliverable presence and
[SUMMARY.md](../docs/verification/round18_ext_2026_05_13/SUMMARY.md)
records per-prompt status, the test-suite roll-up, the seven invariant
re-checks, the five biggest open questions, and the run cost.

| # | Prompt | Verification |
|---|---|---|
| 51 | [Published-article rendering bug](51_published_article_rendering_bug.txt) | shipped — manifest §P51 |
| 52 | [Public-homepage article surfacing](52_public_homepage_article_surfacing.txt) | shipped — manifest §P52 |
| 53 | [Continuous-running scheduler stability](53_continuous_running_scheduler_stability.txt) | shipped — manifest §P53 (`status.py` inlined) |
| 54 | [Dashboard terminology + cleanup](54_dashboard_terminology_and_cleanup.txt) | shipped — manifest §P54 (Playwright snapshot unverified — webServer issue) |
| 55 | [Performance audit + remediation](55_performance_audit_and_remediation.txt) | shipped — manifest §P55 (`next.config` is `.ts`) |
| 56 | [Principle-first claim extraction](56_principle_first_claim_extraction.txt) | shipped — manifest §P56 |
| 57 | [Principle → quantitative bridge](57_principle_to_quantitative_bridge.txt) | shipped — manifest §P57 |
| 58 | [Knowledge dashboard, principle-first](58_knowledge_dashboard_principle_first.txt) | shipped — manifest §P58 |
| 59 | [Stocks portfolio data model](59_stocks_portfolio_data_model.txt) | shipped — alembic round-trip FAILS (open question 1) |
| 60 | [Alpaca paper integration](60_alpaca_paper_integration.txt) | shipped — manifest §P60 |
| 61 | [Stocks signal generation, principle-grounded](61_stocks_signal_generation_principle_grounded.txt) | shipped — verbatim-citation invariant verified |
| 62 | [Robinhood live adapter (optional)](62_robinhood_live_adapter_optional.txt) | shipped — manifest §P62 |
| 63 | [Unified portfolio dashboard](63_unified_portfolio_dashboard.txt) | shipped — pages live under `(authed)/` |
| 64 | [Quantitative test framework](64_quantitative_test_framework.txt) | shipped — manifest §P64 |
| 65 | [UI critique via designer persona](65_ui_critique_via_designer_persona.txt) | shipped — manifest §P65 |
| 66 | [Apply UI revision plan](66_apply_ui_revision_plan.txt) | shipped — manifest §P66 |
| 67 | [PDF user guides](67_pdf_user_guides.txt) | shipped — `screenshots/.gitkeep` missing |
| 68 | [Theseus template extraction](68_theseus_template_extraction.txt) | shipped — manifest §P68 |
| 69 | [VC-firm preset configuration](69_vc_preset_configuration.txt) | shipped — `test_vc_principle_alignment.py` skipped (jsonschema missing) |
| 70 | [Dev workflow + privacy audit](70_dev_workflow_branch_pr_private_audit.txt) | shipped — manifest §P70 |
| 71 | [Audio capture → principle pipeline](71_audio_capture_to_principle_pipeline.txt) | shipped — voice-memo queue invariant verified |
| 72 | [Round 18 extension verification](72_round18_extension_verification.txt) | this prompt — see [SUMMARY.md](../docs/verification/round18_ext_2026_05_13/SUMMARY.md) (PARTIAL FAIL: pytest 8 failed, npm build broken) |
