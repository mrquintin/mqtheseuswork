# Round 19 — Philosopher in a Box: the algorithm layer, contradiction-geometry, synthesizer + memo, polymorphic bets

Active batch authored 2026-05-15 in response to the 05/15 weekly
meeting. Round 18 (all 72 top-level prompts including the
51–72 extension) was implemented and archived; Round 19 builds
the missing layer — algorithms as logical functions over
principles — and the supporting infrastructure (synthesizer
engine, memos, polymorphic bets, knowledge graph, Dialectic
live-recording, deletion pass, Philosopher-in-a-Box identity
rollout, verification).

The active runnable batch is exactly the top-level numbered
prompt set 01–18. Round 18's prompts are at
`archive_round18_completed/` and are NOT picked up by the
runner.

## Run

```bash
cd /Users/michaelquintin/Desktop/Theseus
./run_prompts.sh
```

The runner naturally picks up only the 18 new prompts because
its glob is `coding_prompts/[0-9][0-9]_*.txt` at the top level.
No script change was needed.

Useful filters:

```bash
./run_prompts.sh --dry-run
./run_prompts.sh --from 4
./run_prompts.sh --to 5         # finish the algorithm layer alone
./run_prompts.sh --only 17      # rebuild only the identity + pitch
./run_prompts.sh --model claude-opus-4-7
./run_prompts.sh --continue
```

The runner uses the Claude Code CLI's existing
login/subscription path (`claude -p`), NOT an API key. Streaming
is rendered through `format_stream_claude.py`. Raw JSONL persists
at `.claude_code_runs/<timestamp>_<prompt>.raw.jsonl`; the
human-readable log is at
`.claude_code_runs/<timestamp>_<prompt>.log`.

## Map

### Wave A — Algorithm layer (the headline)

| #  | File | Summary |
|----|---|---|
| 01 | `01_algorithm_data_model.txt` | `LogicalAlgorithm` + `AlgorithmInvocation` schema. Inputs/output/reasoning chain/trigger predicate. Three worked examples (arms-race, hyperstition, founder-quality) anchor the design |
| 02 | `02_algorithm_extraction_from_principles.txt` | LLM-assisted drafter proposes algorithms from clusters of related principles. Founder-triaged. Refuses to invent principles or fabricate observable inputs |
| 03 | `03_algorithm_runtime_and_invocation.txt` | Runtime that fires algorithms against the world. InputResolver pulls from Currents, markets, artifacts, operator entries. Idempotent. Trigger predicate evaluated in sandbox |
| 04 | `04_algorithm_visibility_surface.txt` | `/algorithms` public + `/(authed)/algorithms/operator`. Founders SEE algorithms working — invocation drill pages with full reasoning trace |
| 05 | `05_algorithm_calibration_and_retirement.txt` | Track record per algorithm. Hit rate, Brier, calibration drift, retirement triggers. Promotion path bumps weighting in the synthesizer |

### Wave B — Contradiction engine + source demarcation

| #  | File | Summary |
|----|---|---|
| 06 | `06_contradiction_geometry_engine.txt` | Replace the six fragile heuristics with one canonical geometry-based detector. Versioned. Confidence-calibrated. Human explanation grounded in verbatim disagreement |
| 07 | `07_embedding_cluster_prefilter.txt` | Cluster principles in embedding space; test only within-cluster + small cross-cluster sample. Bounds the O(N²) blowup |
| 08 | `08_source_driven_resolution.txt` | Kill the manual contradiction-resolve UI. Sources resolve contradictions via the lifecycle (WEAKENED → RESOLVED_BY_SOURCE → SUBSUMED). Founder confirms SUBSUMED |
| 09 | `09_proprietary_vs_external_source_demarcation.txt` | Upload-time tagging: PROPRIETARY / ENDORSED_EXTERNAL / STUDIED_EXTERNAL / OPPOSING_EXTERNAL. Oracle checkboxes. Synthesizer weighting per kind |

### Wave C — Synthesizer + memo + portfolio agent

| #  | File | Summary |
|----|---|---|
| 10 | `10_synthesizer_engine.txt` | The engine that takes inputs + principles + algorithm invocations → conclusion. Abstains on no-principles, contradiction-in-chain, normative-only, budget |
| 11 | `11_investment_memo_format.txt` | 10-section memo as canonical output. Markdown + pdflatex. Public memos surface for selective publication |
| 12 | `12_portfolio_agent_interface.txt` | HUMAN / AUTO_PAPER / AUTO_LIVE portfolio agents. Subscriptions per topic + question_type. AUTO_LIVE still queues for operator per-bet confirmation |

### Wave D — Knowledge graph + Dialectic

| #  | File | Summary |
|----|---|---|
| 13 | `13_knowledge_graph_view.txt` | Cross-source node graph (concept/person/source/topic/principle/algorithm/memo). Edge-click invokes the agent reasoner. Refuses fabricated connections |
| 14 | `14_dialectic_live_recording_mode.txt` | Live meeting/podcast recording. Real-time contradiction flags (INTRA, HISTORICAL_SELF, HISTORICAL_OTHER, HISTORICAL_FIRM). Provisional principles triaged post-session |

### Wave E — Bet polymorphism

| #  | File | Summary |
|----|---|---|
| 15 | `15_polymorphic_bet_abstraction.txt` | `BetSpec` abstraction. Kinds: MARKET_BET, ADVISORY_BET, STRATEGIC_BET, SCIENTIFIC_BET. Per-kind resolvers. Eight-gate safety applies to MARKET only |

### Wave F — Trim + identity + verification

| #  | File | Summary |
|----|---|---|
| 16 | `16_deletion_pass.txt` | "Every assumption fights for its life." Audit every surface; DELETE / DEMOTE / KEEP with rationale. Anti-resurrection tests |
| 17 | `17_philosopher_in_a_box_identity_and_pitch_deck.txt` | Roll out the Philosopher-in-a-Box identity across homepage / about / README. Build a pdflatex pitch deck with live-snapshot slide-11 data |
| 18 | `18_round19_verification.txt` | Verify all 15 Round-19 invariants. Manifest, test roll-up, summary report. Final pass |

### Wave G — Round 19b: bug-testing + sync-safety infrastructure (prompts 19–28)

Authored 2026-05-15 immediately after 01–18 to ensure that running
the round and then syncing to GitHub does not produce build
failures, drift, or strange behavior. Adds a `ready-to-sync` gate
the operator runs (or sync invokes automatically) before any
push. Daily-driver command: `make ready-to-sync`.

| #  | File | Summary |
|----|---|---|
| 19 | `19_migration_linearity_and_schema_contract.txt` | Prisma + Alembic chain linearity; up-down-up cycle; Prisma-vs-SQLModel column parity with documented allowlist |
| 20 | `20_import_cycle_and_type_contract.txt` | Import-linter layered contract over the new modules; FastAPI ↔ TypeScript generated-type sync enforced in CI |
| 21 | `21_end_to_end_smoke_harness.txt` | `scripts/smoke/run.sh` — every public route, every CLI `--help`, one tick per scheduler sub-loop, three pipeline e2e flows |
| 22 | `22_algorithm_pipeline_integration_test.txt` | Arms-race end-to-end: principles → cluster → drafter → ACTIVE → tick → invocation → memo → portfolio agent → paper bet → resolution → calibration |
| 23 | `23_env_var_validation_and_boot_check.txt` | Extended validator + boot-time refusal of startup on missing required vars; readyz exposes the validation report (redacted) |
| 24 | `24_sandbox_and_safety_regression_suite.txt` | 10 named safety properties (sandbox, eight gates, verbatim citations, provenance policy, no-secrets-in-logs, operator HMAC, kill switch, idempotency) each get a dedicated test |
| 25 | `25_bug_replay_regression_catalog.txt` | Every bug we've actually hit (B01–B15) gets a regression test. Catalog is living; freshness test enforces 1:1 between BUG_CATALOG.md and test functions |
| 26 | `26_ci_workflow_tooling_and_doc_freshness.txt` | Every workflow YAML parses + references real scripts; tooling availability probe (pdflatex/gh/vercel/prisma/alembic); doc link freshness |
| 27 | `27_pre_sync_gate.txt` | `scripts/ready-to-sync.sh` runs steps 19–26 sequentially. Sync refuses to push if the gate fails. `--from`, `--only`, `--skip` flags |
| 28 | `28_round19b_bugtesting_verification.txt` | Meta-verification: every check from 19–27 caught its planted synthetic bug. Coverage report. Final pass |

### Daily workflow after Round 19 + 19b land

```bash
# After running the round:
make ready-to-sync         # invokes scripts/ready-to-sync.sh
                           # passes → safe to push
                           # fails → structured report, fix, re-run with --from N

# To push (gate runs automatically):
make sync

# To run only the gate without pushing:
./scripts/sync-to-github.sh --ready-to-sync-only
```

## 15 invariants Round 19 protects (prompt 18)

1. Algorithm layer is live (≥ 1 ACTIVE algorithm has fired with complete reasoning trace).
2. Algorithms are visible (public pages render the full reasoning chain).
3. Contradiction engine canonical (one detection method; six legacy heuristics DEPRECATED).
4. Cluster pre-filter is on (bounded contradiction queue; non-zero surprise sampling).
5. Manual contradiction resolution gone (old route returns 404).
6. Provenance demarcation enforced (every artifact tagged; Oracle filters).
7. Synthesizer engine produces structured memos (CONCLUDED or ABSTAINED, never silent fail).
8. Memos are auditable (10-section structure; ≥ 2 governing principles each).
9. Portfolio agent never bypasses gates (AUTO_LIVE queues for operator confirmation).
10. Knowledge graph reflects reality (no fabricated agent-reasoner explanations).
11. Dialectic live recording fires real flags within latency target.
12. Bet abstraction is polymorphic (all four kinds work end-to-end).
13. Deletion pass executed cleanly (every DELETE returns 410 or is gone; every DEMOTE is authed-only).
14. Identity is consistent (homepage / about / README use canonical copy; pitch deck builds).
15. No prior-round regression (Round 18 forecasts invariants + Round 10 eight-gate safety still hold).

## What this round does NOT do

- It does not autonomously trade. The eight-gate contract from Round 10 still requires per-bet operator confirmation for every live order. Round 19 ADDS portfolio agents but does not remove that gate.
- It does not commercialize Theseus as a SaaS product. Per the meeting's explicit reversal, the machine is the firm's edge, not a product. The template-extraction work from Round 18 prompt 68 remains in the codebase for the VC tenant case but is no longer the strategic spine.
- It does not delete the six legacy contradiction heuristics — only DEPRECATES them. Prompt 16's deletion pass removes them.
- It does not extract algorithms from thin air. Drafter (prompt 02) only proposes algorithms from clusters of EXISTING principles, founder-triaged before promotion to ACTIVE.

## Archives

- `archive_round18_completed/` — the 72 implemented prompts from Round 18 (50 original + 22-prompt extension authored 2026-05-13). README + FORECASTS_DESIGN + RELEASE_CHECKLIST also archived there.
- `archive_round17_methodology_implementation/` — Round 17 (methodology operationalization, QH benchmark, calibration loop, belief revision, source provenance, adversarial swarm, public surfaces, dialectic upgrades, observability, retention, external critique, signing).
- Earlier archives back through round3.

## Additional isolated batches

- `ui_ux_round19/` — a dedicated UI remediation batch from the 2026-05-11 live path walk. Run via its own `run_prompts.sh` inside that subdirectory. Not picked up by the top-level runner.
- `ui_ux_round20/` — the 25-prompt UI + algorithmic-decision + portfolio batch. Completed 2026-05-11/12.

## If something goes wrong

- A prompt fails → log at `.claude_code_runs/`; runner prints resume hint (`--from N`).
- A test invariant fails in prompt 18 → halt; file as Round-20 work item.
- The pitch deck (prompt 17) fails to build → check pdflatex is installed locally; the `live_snapshot.py` may have failed against a non-running API.
- Round 18's eight forecasts invariants regress → STOP. Round 19 must not break Round 18 safety properties.

## Round 19 verification

Verification pass: 2026-05-16. Roll-up: **PARTIAL FAIL**.

- All 15 Round 19 invariants (I1..I15) pass —
  `pytest tests/round19/test_invariants.py -v` → 15 passed.
- Alembic upgrade-to-head runs cleanly through `024_bet_polymorphism`.
- `next build` fails: `(authed)/memos`, `(authed)/library`, and
  `(authed)/dialectic/sessions/[id]` collide with their public
  twins under Next 16's app router. Same root cause kills
  `playwright --grep '@smoke'`.
- Two SCOPE gaps deferred to Round 20: `round19_deletion_invariants.test.ts`
  (P16) and the `src/app/portfolio/page.tsx` MODIFY (P12 — implementer
  modified the authed twin, same pattern as Round 18 P63).

Full report: [`docs/verification/round19_2026_05_15/SUMMARY.md`](../docs/verification/round19_2026_05_15/SUMMARY.md).
Manifest, logs, and the invariant suite live alongside it.

## Round 19b — bug-testing infrastructure (prompts 19–28)

Round 19b retrofits Round 19 with the static analysis, regression
suites, smoke harness, integration test, env-var validation,
sandbox + safety regression suite, bug-replay catalog, CI workflow
+ doc freshness, pre-sync gate, and meta-verification it was
missing.

**Daily driver — before every push**

```
make ready-to-sync   # 8-step gate, halts on first failing step
make sync            # pre-flighted by ready-to-sync.sh
```

On failure the gate writes a structured report to
`docs/verification/ready_to_sync/<timestamp>/REPORT.md` and prints
the failing step's log path. Resume with
`./scripts/ready-to-sync.sh --from N`.

**Meta-verification**

The 12 meta-invariants live in
[`tests/meta/test_bugtesting_meta_invariants.py`](../tests/meta/test_bugtesting_meta_invariants.py).
Each plants a synthetic bug and asserts the corresponding check
catches it — "the test that tests the test." Full report:
[`docs/verification/round19b_bugtesting_2026_05_15/SUMMARY.md`](../docs/verification/round19b_bugtesting_2026_05_15/SUMMARY.md).
