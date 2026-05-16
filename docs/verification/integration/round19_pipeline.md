# Round-19 pipeline integration test

The single test `tests/integration/test_round19_pipeline.py::test_arms_race_end_to_end`
walks the founder's arms-race example through every public seam of
the Round-19 algorithm layer. If it goes green, the layer is
*functionally alive*; if any one stage breaks, the test fails inside
that stage's assertion block so the failure points at the right
seam.

Three companion tests guard the adjacent abstain paths:

| Test | What it guards |
| --- | --- |
| `test_synthesizer_abstains_on_normative_only` | Normative-only clusters never reach an LLM call; outcome is `REFUSED_NORMATIVE_ONLY`. |
| `test_portfolio_agent_auto_paper_path` | An `AUTO_PAPER` agent fires a paper bet without operator intervention. |
| `test_contradiction_blocks_synthesis` | A STANDING contradiction between two cited principles forces `ABSTAINED_CONTRADICTION`. |

## Sequence

```text
seed principles + currents events
   │
   ▼
algorithm drafter  ── MockLLM ──▶ DRAFT LogicalAlgorithm
   │
   ▼
founder accept              ──▶ ACTIVE LogicalAlgorithm
   │
   ▼
runtime fire_algorithm ── MockLLM ──▶ AlgorithmInvocation
   │                                  + reasoning trace persisted
   ▼
synthesizer engine     ── MockLLM ──▶ SynthesisResult.CONCLUDED
   │                                  + memo dict persisted
   ▼
memo builder                       ──▶ InvestmentMemo (DRAFT) row
   │
   ▼
update_investment_memo_status      ──▶ memo SENT
   │
   ▼
portfolio router.dispatch_memo     ──▶ MemoDispatch (HUMAN, PENDING)
   │
   ▼
operator accept-and-bet            ──▶ ForecastBet PAPER + dispatch
                                        ACCEPTED_AND_BET
   │
   ▼
time advances +365d                ──▶ ForecastMarket.RESOLVED YES
                                        + ForecastResolution row
   │
   ▼
store.set_invocation_resolution    ──▶ algorithm calibration updated
                                        (correctness=CORRECT)
   │
   ▼
ContradictionEngine.detect         ──▶ verdict != CONTRADICTORY
                                        (cluster passes the canonical
                                         detector against itself)
```

## What this test covers vs. doesn't

**Covers**

- The drafter's full public path on the happy path:
  `principle cluster → DRAFTED → persisted row` via the real
  `Store.put_algorithm` validator stack.
- Algorithm promotion via `store.set_algorithm_status`, the same
  helper the founder UI calls.
- `AlgorithmRuntime.fire_algorithm` with the real `AdapterRegistry`,
  `InputResolver`, and `MockLLMClient`. The runtime persists an
  `AlgorithmInvocation` row through `store.put_invocation`.
- `SynthesizerEngine.synthesize` over the real Store-backed
  principle/contradiction views (exposed through the
  `_IntegrationStore` shim) — including the question
  constituter, governing-principle identification, contradiction
  block, confidence-band guard, and memo-dispatch hook.
- `synthesizer.memo_builder.build_memo` end-to-end:
  - 10-section memo validator
  - persistence via `store.put_investment_memo`
  - markdown render to disk
- `portfolio_agent.router.dispatch_memo` for both HUMAN and
  AUTO_PAPER agents, plus
  `portfolio_agent.router.acknowledge_dispatch` for the operator
  accept path.
- `portfolio_agent.auto_paper.place_paper_bet_from_memo` against
  the real `ForecastBet` row.
- Real `ForecastMarket` → `ForecastResolution` settlement.
- `store.set_invocation_resolution` (the calibration write).
- `ContradictionEngine.detect` (the canonical Round-19 detector).

**Doesn't cover**

- The CLI surfaces for any of the above stages — covered by the
  unit-level CLI tests in `noosphere/tests/test_cli_*`.
- The Polymarket / Kalshi venue clients — the test seeds a market
  row directly rather than going through the discovery / pull loop.
- The PDF-rendering pipeline (`build_memo_pdf` is best-effort and
  may exit non-zero in the integration environment; the memo
  markdown is the load-bearing artifact).
- The cross-tenant `provenance_audit` filter — the test runs in a
  single-tenant fixture.
- The MQS publish bar and the public memo surface — covered by
  `noosphere/tests/test_auto_paper_integration.py`.

## Debugging a failure

Each pipeline stage produces a structured log line via
`noosphere.observability.get_logger`. When the test fails, the
assertion message identifies the stage and the captured logs
under the failing test (`caplog` is wired) carry the structured
event.

| Stage | Log event to inspect | Likely culprits |
| --- | --- | --- |
| Drafter | `algorithm.drafter.*` | Cluster shape, observability source mismatch, validator-stack regression. |
| Runtime fire | `algorithms.runtime.invocation_fired` (success) or `algorithms.runtime.principle_step_abstained` / `algorithms.runtime.chain_without_output` (failure) | Token budget too tight, LLM script ordering off, principle id mismatch. |
| Synthesizer | `synthesizer.memo_persist_failed` or the per-stage abstain reason on `SynthesisResult.reasoning` | Governing-principle threshold, contradiction lifecycle in unexpected state, confidence band > 0.5. |
| Memo builder | `synthesizer.memo_builder.built` (success) or `synthesizer.memo_builder.store_missing_helper` | 10-section validator rejecting the body, missing `put_investment_memo` shim. |
| Router | `portfolio_agent.dispatch` | Memo not SENT, agent not ACTIVE, subscription topic/qtype mismatch. |
| Auto-paper | `portfolio_agent.auto_paper.*` | `implied_bet` missing `prediction_id`, zero stake range, ceiling too small. |
| Resolution / calibration | `store.set_invocation_resolution` raising `AlgorithmValidationError` | Invocation id wrong, brier value out of range. |
| Contradiction engine | Engine returns `CONTRADICTORY` against a cluster the test treats as coherent | Embedding fixture drift, detection threshold change. |

The test also tags every LLM call by stage on `CountingMockLLM.stage_counts`,
so a regression that double-invokes the LLM at any seam is caught
without having to inspect prompts.

## Extending the test when a new pipeline stage lands

1. Add a setup helper at the top of `tests/integration/test_round19_pipeline.py`
   that mirrors the existing helpers (`seed_*`, `simulate_*`,
   `advance_time`, `resolve_*`). Keep it small — the test should
   call your helper exactly once.
2. Append a new "── N. <stage> ──" block to
   `test_arms_race_end_to_end` between the existing stages, with:
   - the `llm.stage("<new-stage>")` tag if your stage calls the
     LLM,
   - one assertion that the stage's expected row landed in the
     store,
   - one assertion that the per-stage LLM call count matches.
3. If your stage emits a structured log line, document the log
   event name in the table above so a future failure points at
   the right log.
4. If your stage introduces a new abstain mode, add a companion
   test (mirroring `test_synthesizer_abstains_on_normative_only`)
   that exercises the refusal path.

The test's perf budget is 30 seconds on an M-series Mac. Above
the budget the test emits a `RuntimeWarning` rather than failing —
perf regressions get tracked separately, but the warning surfaces
in the CI logs so the regression cannot land silently.

## CI

The integration suite runs in the existing `smoke` workflow as a
follow-on step to the smoke harness (`./scripts/smoke/run.sh`).
Both run on every PR and on every push to `main`.
