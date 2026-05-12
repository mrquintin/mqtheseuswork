# Algorithmized Decision Making — Architecture

Date: 2026-05-12
Status: Draft. Design and inventory only. This document does not
modify any live trading behavior. It is the design floor that the
forthcoming coding-prompt batch (prompts 14–25, scoped in §6 below)
will build against.

This is the investment / prediction-market extension of the design
direction recorded in `docs/architecture/UI_UX_Round20_Contract.md`.
That contract governs how Theseus surfaces are read; this contract
governs how Noosphere reasoning becomes an inspectable algorithm when
the output is a position rather than an essay.

## 1. The distinction this document enforces

Noosphere already does three things that get confused with each
other when they shouldn't be. The product direction is that markets
make the confusion costly, so the boundaries must be drawn
explicitly.

### 1.1 Interpretive Noosphere reasoning

Interpretive reasoning is what most of `noosphere/noosphere/coherence`
and `noosphere/noosphere/methods` produces today: a six-layer coherence
verdict, a contradiction probe, a synthesized conclusion, a
methodology fit assessment, a failure-mode catalog match. The outputs
are typed and inspectable but they are addressed to a *reader* — they
exist to defend a philosophical claim. Examples in code:

- `noosphere/noosphere/coherence/engine.py` — six-layer scorer (S₁–S₆),
  composite coherence `Coh(Γ)` with configurable weights.
- `noosphere/noosphere/coherence/argumentation.py` — Dung-style
  abstract-argumentation acceptability over `Claim` neighborhoods.
- `noosphere/noosphere/coherence/judge.py` — LLM meta-judge with
  citation-enforced layer references.
- `noosphere/noosphere/methods/six_layer_coherence.py`,
  `synthesize_conclusion.py`, `contradiction_probe.py`,
  `contradiction_geometry.py`, `domain_bounds.py`, `failure_modes.py`,
  `composition.py` — the registered methods that compose into a
  conclusion.

These outputs are interpretive in the sense that the cost of being
slightly wrong is bounded by reader judgment, not by capital loss.

### 1.2 Algorithmized decision traces

A decision trace is interpretive reasoning *frozen into an
inspectable computation* whose intermediate values are recorded and
whose composition rules are explicit before the run begins. The
current code already begins to do this for forecasts:

- `noosphere/noosphere/forecasts/forecast_generator.py` writes a
  `ForecastTrace` row containing `principles_used`, `model_output`,
  and `gate_results` (`_trace_principles`, `_trace_model_output`,
  `_trace_gate_results`, persisted via `_write_forecast_trace`).
- `noosphere/noosphere/forecasts/safety.py:evaluate_gate_results`
  returns a typed `list[GateResult]` for the eight live-trading
  gates and is the canonical example of "rule graph as data".
- `noosphere/noosphere/models.py` — `ForecastTrace` table
  (`predictionId` unique, `principles_used: list[dict]`,
  `model_output: dict`, `gate_results: list[dict]`, organization &
  market FK columns).

The defining property of a decision trace is that the prose summary
on a page is generated *from* the trace, never the other way around.
If the prose disagrees with the trace, the trace wins.

### 1.3 Investable outputs

An investable output is a concrete *action* that a downstream system
can refuse, defer, or execute. It includes a side, a size (or zero),
a venue, a max-cost band, and a justification pointer back to the
trace that produced it. Today, the investable outputs in the repo
are:

- `noosphere/noosphere/forecasts/paper_bet_engine.py:evaluate_and_stake`
  — paper fills, quarter-Kelly with stake ceiling.
- `noosphere/noosphere/forecasts/edge_calc.py:compute_edge` →
  `EdgeReport` — surfaced edges for the founder UI from a Currents
  opinion linked to a matched market.
- `noosphere/noosphere/forecasts/live_bet_engine.py:submit_live_bet`
  — gated live submission, must pass
  `noosphere.forecasts.safety.check_all_gates` and carry a non-empty
  `operator_id`.
- Frontend reads: `theseus-codex/src/app/(authed)/forecasts/portfolio/ForecastPortfolioView.tsx`
  and `theseus-codex/src/app/(authed)/forecasts/operator/page.tsx`.

The three layers are not a pipeline so much as a *staircase* of
liability: each step adds verifiability and removes one degree of
prose freedom.

```
interpretive reasoning  →  algorithmized decision trace  →  investable output
       (essay)                (data structure)                (action)
   readers judge it           algorithms judge it          markets judge it
```

## 2. Logic algorithm contract

A "logic algorithm" is the function that turns a market input into an
investable output by way of a decision trace. This section names the
contract precisely so the prompts in §6 can implement it without
re-debating the shape.

### 2.1 Inputs

The contract function MUST accept all of:

1. `market` — a `ForecastMarket` row, including
   `current_yes_price`, `current_no_price` (when present),
   `close_time`, `status`, and `raw_payload`. Source of truth for
   prices and venue identity.
2. `event` — the proximate question text and resolution criteria.
   For markets this is derived from `market.title`,
   `market.description`, and `market.resolution_criteria` via
   `noosphere.forecasts.retrieval_adapter.build_query_from_market`.
   The split between `market` and `event` is intentional: the same
   event may be tradable on multiple `market` rows.
3. `corpus_slice` — the retrieved, filtered set of `Conclusion` and
   `Claim` sources, as produced by
   `noosphere.forecasts.retrieval_adapter.retrieve_for_market`
   (visibility filter, 18-month staleness rule, MMR diversification,
   top-k cap). The slice is the only allowed grounding for the
   trace.
4. `active_principles` — the subset of corpus conclusions the
   algorithm is treating as load-bearing for this trace. Recorded
   verbatim in `ForecastTrace.principles_used` with `weight` and
   `snippet`.
5. `calibration_state` — the per-domain calibration map from
   `noosphere.coherence.recalibration.load_active_record` (and, for
   live, the daily-loss / kill-switch posture from
   `noosphere.forecasts.safety.gate_context_from_env`).
6. `liquidity_cost_data` — `market.current_yes_price`,
   `market.current_no_price`, depth/spread fields when present in
   `raw_payload`, and (for stake sizing) the
   `noosphere.forecasts.paper_bet_engine.PaperBetConfig`
   (`edge_threshold`, `kelly_fraction`, `max_stake_usd`,
   `initial_balance_usd`).

All six MUST be present, even if shallow. Absent inputs are a
design error, not a data error — the algorithm refuses to construct
a trace rather than imputing.

### 2.2 Intermediate metrics

Every metric the algorithm consults MUST be:

- **Named.** A stable snake_case identifier; no anonymous
  intermediate floats inside the rule graph. The §3 catalog is
  authoritative.
- **Typed.** A scalar in a documented range (mostly `[0, 1]` or
  `[-1, 1]`) plus a `low_confidence: bool` and a `method:str`
  describing the producing routine and version.
- **Reproducible.** Given the same inputs at §2.1, the metric value
  is deterministic up to recorded randomness (e.g.
  `contradiction_direction.ContradictionDirection.method` and
  `exemplar_count`).
- **Inspectable.** Persisted as a field inside
  `ForecastTrace.model_output` (or an extension thereof — see §5)
  with its name, value, and producing method version. The UI MUST
  be able to render it as a row.

### 2.3 Rule graph

The rule graph combines metrics into a decision. It is a *graph of
typed rules*, not a model. Each node is one of:

- a **threshold** — `metric_X ≥ τ` with `τ` named in config;
- a **boolean combiner** — `all_of`, `any_of`, `at_least(k_of_n)`;
- a **veto** — short-circuits to `abstain` regardless of downstream
  evaluation when triggered (the live-trading gates in
  `noosphere.forecasts.safety` are the canonical example);
- a **bucket** — maps a scalar metric (e.g. edge magnitude) to a
  candidate `Decision` (see §2.4) before vetoes apply.

The graph is data. It MUST be expressible as JSON and stored
alongside or referenced from the trace so two runs over the same
graph + inputs produce identical traces. Configuration changes are
versioned the way
`noosphere.coherence.calibration.CoherenceCalibrationBundle` is
versioned today.

### 2.4 Output

The investable output is one of exactly seven decisions:

| Decision        | Meaning                                                              | Capital effect            |
|-----------------|----------------------------------------------------------------------|---------------------------|
| `abstain`       | The trace refuses to take a view. No watchlist, no record beyond the trace itself. | none |
| `watch`         | Surface to operator; do not stake.                                   | none                       |
| `paper_trade`   | Open a paper fill via `paper_bet_engine.evaluate_and_stake`.         | paper balance only         |
| `live_candidate`| Eligible for operator confirmation; nothing fills automatically.     | pending operator           |
| `reduce`        | Existing position: cut size by a named fraction.                     | reduces exposure           |
| `exit`          | Existing position: close.                                            | closes exposure            |
| `hedge`         | Open offsetting exposure named in the trace.                         | adds offsetting exposure   |

Today `forecast_generator.py` effectively emits only `abstain` (its
`ForecastOutcome.ABSTAINED_*` variants), `paper_trade` (via the
unconditional `evaluate_and_stake` call), and an implicit
non-existent `live_candidate` (the gate `live_trading_activation`
always returns `passed=False` in `_trace_gate_results`). The other
four decisions are not yet emitted; they are scoped to the prompts
in §6.

### 2.5 Explanation

Prose is generated **from the trace**. Concretely:

- `headline` and `reasoning_markdown` in the
  `forecast_generator.py` output remain LLM-produced, but the
  schema validator (`_validate_forecast_citations`) already
  refuses outputs whose `reasoning_markdown` does not mention at
  least one cited source id. The same discipline extends to
  algorithm-driven decisions: the UI may render only the trace
  fields plus, separately, a clearly marked "narrative summary"
  block whose text is generated from the trace fields, never
  the inverse.
- A decision row in the operator UI MUST be reconstructible from
  the trace alone (decision, side, size, the metrics consulted,
  the rules fired, the vetoes considered) without consulting the
  narrative summary.

## 3. Candidate logic-based metrics

This catalog names ten initial metrics for market decisions. All
ten are *logic-based* in the sense that they are computed from the
Noosphere graph and the market input — not from price-history
quant signals. The first six already have substantial code
substrate; the last four are partly there and partly missing
(§5 inventories them).

For each metric: type, definition, primary input(s), producing
routine if any, and the role in the rule graph.

### 3.1 `thesis_resonance`

- Type: `float ∈ [0, 1]`.
- Definition: degree to which the market's resolved-YES world is
  *positively entailed* by the union of `active_principles`,
  measured via NLI entailment from each principle's load-bearing
  span to a templated resolution statement.
- Inputs: `active_principles`, `event`.
- Substrate today: `noosphere/noosphere/coherence/nli.py`,
  `noosphere/noosphere/methods/nli_scorer.py`,
  `noosphere/noosphere/methods/citation_entailment.py`.
- Rule-graph role: gate for `paper_trade` and `live_candidate`;
  low values force `abstain` or `watch`.

### 3.2 `contradiction_pressure`

- Type: `float ∈ [0, 1]`.
- Definition: maximum NLI-contradiction score between any active
  principle and the templated resolution statement, optionally
  amplified by the Dung-style attack count from
  `argumentation.evaluate_pair_with_neighbors`.
- Inputs: `active_principles`, `event`, `corpus_slice`.
- Substrate today: `noosphere/noosphere/coherence/nli.py`,
  `noosphere/noosphere/coherence/argumentation.py`,
  `noosphere/noosphere/coherence/contradiction_direction.py`,
  `noosphere/noosphere/methods/contradiction_geometry.py`.
- Rule-graph role: veto on high values (`> τ_contradict`) →
  forced `abstain`; degrades `confidence` continuously below the
  veto threshold.

### 3.3 `premise_support_density`

- Type: `float ∈ [0, 1]`.
- Definition: fraction of the algorithm's stated premises that
  resolve to at least one verbatim-quoted citation that survives
  `forecast_generator._validate_forecast_citations`. Bounded by the
  distinct-sources floor (`MIN_DISTINCT_SOURCES = 3`).
- Inputs: `active_principles`, `corpus_slice`.
- Substrate today: `forecast_generator._validate_forecast_citations`,
  `noosphere/noosphere/methods/citation_entailment.py`.
- Rule-graph role: hard floor — below the minimum density, the
  output is forced to `abstain` regardless of `thesis_resonance`.

### 3.4 `source_domain_locality`

- Type: `float ∈ [0, 1]`.
- Definition: angular-cosine similarity between the market's
  embedded query (`retrieval_adapter.build_query_from_market`) and
  each cited principle's domain centroid, aggregated as the
  fraction of citations whose `verdict` is `in_bounds` under the
  principle's `DomainBound`.
- Inputs: `corpus_slice`, `active_principles`, `market`.
- Substrate today: `noosphere/noosphere/methods/domain_bounds.py`
  (`Verdict ∈ {in_bounds, edge_case, out_of_bounds}`),
  `noosphere/noosphere/coherence/locality.py` (ANN-backed
  domain-local neighborhood).
- Rule-graph role: gates `live_candidate`; values below a named
  threshold downgrade to `watch`.

### 3.5 `causal_chain_completeness`

- Type: `float ∈ [0, 1]`.
- Definition: fraction of the trace's stated cause→effect edges
  that have at least one supporting citation (`DIRECT` or
  `INDIRECT`) and no `CONTRARY` citation overriding them. Cause
  edges are extracted via the existing claim/voice decomposition
  primitives.
- Inputs: `active_principles`, `corpus_slice`.
- Substrate today: `noosphere/noosphere/methods/decompose_voice.py`,
  `noosphere/noosphere/methods/extract_claims.py`,
  `noosphere/noosphere/methods/extract_methodology.py`. A direct
  causal-chain extractor does not exist yet (see §5).
- Rule-graph role: combined with `thesis_resonance` via `all_of`
  for `live_candidate`; degrades `confidence` continuously
  otherwise.

### 3.6 `adversarial_fragility`

- Type: `float ∈ [0, 1]`. Higher = more fragile.
- Definition: drop in `thesis_resonance` (or rise in
  `contradiction_pressure`) under a curated adversarial perturbation
  set — paraphrased premises, contradiction-direction nudges, and
  red-team objections drawn from the existing red-team batch.
- Inputs: `active_principles`, `event`, `corpus_slice`.
- Substrate today: `noosphere/noosphere/coherence/contradiction_direction.py`
  (`ContradictionDirection`, exemplar pool); red-team prompts under
  `coding_prompts/16_run_redteam_tournament.txt`.
- Rule-graph role: veto on high values for `live_candidate`;
  downgrades to `paper_trade` or `watch` at intermediate values.

### 3.7 `temporal_decay_pressure`

- Type: `float ∈ [0, 1]`. Higher = more decayed.
- Definition: weighted age of the load-bearing citations, divided by
  the market's time-to-resolution, with the
  `is_load_bearing` flag in `retrieval_adapter._is_stale` acting as
  an exemption.
- Inputs: `corpus_slice`, `market.close_time`.
- Substrate today: `noosphere.forecasts.retrieval_adapter`
  (`MAX_SOURCE_AGE = 18 * 31 days`, `is_load_bearing` exemption);
  `market.close_time` already validated in
  `forecast_generator._market_expired`.
- Rule-graph role: bucketed — high decay forces `watch`;
  moderate decay caps `confidence`.

### 3.8 `calibration_adjusted_confidence`

- Type: `float ∈ [0, 1]`.
- Definition: the algorithm's raw confidence
  (e.g. `confidence = 1 − (confidence_high − confidence_low)` as
  used by `forecast_generator._trace_model_output`), mapped
  through the per-domain isotonic calibration from
  `noosphere.coherence.recalibration`.
- Inputs: `calibration_state`, raw confidence band from the
  trace.
- Substrate today: `noosphere/noosphere/coherence/recalibration.py`
  (`fit_per_domain`, `load_active_record`,
  `recalibration_min_samples`). Today the recalibration map is
  applied at render time and never mutates
  `ForecastPrediction.probability_yes`; the same rule applies
  here: the *raw* confidence is what the model said, the
  *calibrated* confidence is what gets sized against.
- Rule-graph role: drives stake sizing; below
  `recalibration_min_samples` returns
  `low_confidence=True` and the rule graph refuses to escalate
  beyond `paper_trade`.

### 3.9 `market_mispricing_edge`

- Type: `float ∈ [-1, 1]`. Signed.
- Definition: `firm_yes_probability − market_yes_price` for YES
  side, with the symmetric expression on NO. Already computed in
  `noosphere.forecasts.edge_calc.compute_edge` and
  `paper_bet_engine.evaluate_and_stake`.
- Inputs: trace probability, `market.current_yes_price`.
- Substrate today: `forecasts/edge_calc.py:compute_edge` (returns
  `EdgeReport(edge_pts, side, surface, low_liquidity,
  suggested_stake_usd, threshold)`).
- Rule-graph role: bucket — sign chooses side; magnitude relative
  to `PaperBetConfig.edge_threshold` chooses
  `abstain`/`watch`/`paper_trade`/`live_candidate`.

### 3.10 `liquidity_cost_feasibility`

- Type: `float ∈ [0, 1]`.
- Definition: 1 minus the fraction of the suggested stake that
  would be consumed by spread/depth/fees at the venue. Concretely:
  `low_liquidity == True` from `EdgeReport` collapses this to 0;
  otherwise it is `1 − (effective_cost / stake)` capped at 1.
- Inputs: `liquidity_cost_data`, suggested stake.
- Substrate today: `edge_calc._suggest_stake_usd` already returns
  `None` when `low_liquidity=True`; the full feasibility scalar is
  not yet computed (see §5).
- Rule-graph role: veto for `live_candidate`; downgrades to
  `paper_trade` (which has no liquidity assumption) or `watch`.

The §6 prompt set extends the catalog with at least two more
metrics — `principle_revocation_risk` and `cross_market_consistency` —
once the existing surfaces support them.

## 4. Worked example

The contract above is abstract. To pin it down, here is what a
single decision should look like end-to-end. None of this is
implemented yet at the §1.3 layer; the example is the *target*.

```
ALGORITHMIZED DECISION

market_id        = mkt_…
event            = "Will <X> happen by <T>?"
firm_yes_p       = 0.72     # from generator, raw
calibrated_p     = 0.66     # via recalibration.load_active_record
market_yes_price = 0.55

metrics:
  thesis_resonance               = 0.74   (method = nli_scorer@v3)
  contradiction_pressure         = 0.12   (method = contradiction_probe@v2)
  premise_support_density        = 0.83   (3 distinct cited sources)
  source_domain_locality         = 0.91   (3/3 citations in_bounds)
  causal_chain_completeness      = 0.60   (3 of 5 edges supported)
  adversarial_fragility          = 0.28   (red-team battery v1)
  temporal_decay_pressure        = 0.14
  calibration_adjusted_confidence= 0.66
  market_mispricing_edge         = +0.11  (YES side)
  liquidity_cost_feasibility     = 0.80

rule graph fired:
  premise_support_density >= 0.5           → ok
  contradiction_pressure   < 0.4 (veto)    → ok
  thesis_resonance        >= 0.6           → ok
  edge magnitude          >= 0.05          → bucket = paper_trade
  source_domain_locality  >= 0.7           → eligible for escalation
  adversarial_fragility    < 0.35          → eligible for escalation
  live_trading_activation                  → false (FORECASTS_LIVE_TRADING_ENABLED=false)

decision = paper_trade
side     = YES
size     = $24.50 (quarter-Kelly on calibrated p, capped)
trace_id = ft_…
```

The narrative summary is then generated from the table above. It
adds nothing the table does not already carry.

## 5. Inventory — what exists, what is missing

Already in code (cite path:line for navigability where appropriate):

- Retrieval contract and filter rules:
  `noosphere/noosphere/forecasts/retrieval_adapter.py`
  (`retrieve_for_market`, MMR, visibility filter, staleness rule).
- Strict-JSON model output with verbatim-citation validation:
  `noosphere/noosphere/forecasts/forecast_generator.py`
  (`FORECAST_RESPONSE_SCHEMA`, `_schema_errors`,
  `_validate_forecast_citations`).
- Decision trace persistence:
  `noosphere/noosphere/forecasts/forecast_generator.py`
  (`_trace_principles`, `_trace_model_output`,
  `_trace_gate_results`, `_write_forecast_trace`) writing the
  `ForecastTrace` table (`noosphere/noosphere/models.py`).
- Edge calculation and quarter-Kelly suggestion:
  `noosphere/noosphere/forecasts/edge_calc.py:compute_edge`,
  `noosphere/noosphere/forecasts/paper_bet_engine.py:_stake_usd`.
- Paper-fill engine with edge threshold and stake ceiling:
  `noosphere/noosphere/forecasts/paper_bet_engine.py:evaluate_and_stake`.
- Live-bet safety contract:
  `noosphere/noosphere/forecasts/safety.py:evaluate_gate_results`
  (eight gates), `submit_live_bet` consuming them, kill-switch
  engagement (`engage_kill_switch`, `maybe_engage_*`),
  exchange-error streak tracking.
- Coherence substrate: `noosphere/noosphere/coherence/engine.py`
  (six layers), `argumentation.py` (Dung), `nli.py`,
  `probabilistic.py`, `judge.py`,
  `contradiction_direction.py`, `locality.py`.
- Methods substrate: `noosphere/noosphere/methods/` —
  `extract_claims.py`, `extract_methodology.py`,
  `contradiction_probe.py`, `contradiction_geometry.py`,
  `decompose_voice.py`, `domain_bounds.py`, `failure_modes.py`,
  `composition.py`, `nli_scorer.py`, `citation_entailment.py`,
  `six_layer_coherence.py`, `synthesize_conclusion.py`.
- Calibration: `noosphere/noosphere/coherence/calibration.py`,
  `noosphere/noosphere/coherence/recalibration.py`.
- Operator and portfolio surfaces:
  `theseus-codex/src/app/(authed)/forecasts/portfolio/ForecastPortfolioView.tsx`,
  `theseus-codex/src/app/(authed)/forecasts/operator/page.tsx`
  (renders gate context, pending authorizations, kill-switch
  panel, live bet ledger).

Missing or partial — to be addressed by §6:

1. **No metric layer between the LLM output and the gate
   results.** `_trace_model_output` records four fields
   (`side`, `edge`, `confidence`, `rationale`). Metrics 3.1–3.10
   are not computed during forecast generation.
2. **No rule-graph data structure.** Threshold values are
   inlined as `MIN_DISTINCT_SOURCES`, `edge_threshold`, etc.
   There is no JSON-serializable rule graph that the
   `ForecastTrace.gate_results` references; the gate list is
   hardcoded in `_trace_gate_results`.
3. **Only three of seven decisions are reachable.** `abstain`,
   `paper_trade`, and implicitly-disabled `live_candidate` are
   the only outputs; `watch`, `reduce`, `exit`, `hedge` are not
   yet emitted. There is no notion of existing position state
   inside `forecast_generator`.
4. **No causal-chain extractor.** Premises today are flat claim
   spans; cause→effect graph extraction is unbuilt
   (`causal_chain_completeness` therefore has no producing
   method).
5. **No adversarial-battery harness wired into the forecast
   path.** Red-team prompts exist but are not invoked from
   `forecast_generator`; `adversarial_fragility` has no producer.
6. **Liquidity feasibility is partial.** `EdgeReport.low_liquidity`
   is a boolean; the scalar `liquidity_cost_feasibility` requires
   spread/depth extraction from `market.raw_payload` not yet
   normalized.
7. **Calibration apply path on the forecast side is not yet
   piped through the trace.** `recalibration.load_active_record`
   is used at TS render time on conclusions; the forecast
   generator path does not yet consume it to produce
   `calibration_adjusted_confidence`. Per the recalibration
   module's contract, the raw probability must remain unchanged
   (`one-directional in display`); the addition is a *new*
   metric field in `ForecastTrace.model_output`.
8. **Public-facing rendering does not currently distinguish
   the trace from the narrative.** Both
   `ForecastPortfolioView.tsx` and the operator page render
   prose-heavy summaries; a "trace view" mode is not yet
   designed.
9. **No principle-revocation propagation onto open positions.**
   `ForecastCitation.is_revoked` exists; nothing reads it to
   trigger `reduce`/`exit` on an open position.

## 6. Implementation plan — prompts 14–25

These prompts will be authored as a new top-level batch in
`coding_prompts/` after Round 20 closure. Numbering is provisional
within the new batch; the existing Round 18 prompts at 14–25 are
not affected. Each prompt below states SCOPE and depends on the
items earlier in the list.

- **14 — Metric layer scaffolding.** Add `noosphere/noosphere/
  forecasts/metrics/__init__.py` and `metric_types.py` defining
  the `Metric` dataclass (`name`, `value`, `range`, `method`,
  `low_confidence`). No metric implementations yet. Extend
  `ForecastTrace.model_output` to allow a `metrics: list[Metric]`
  field. Tests: schema round-trip.
- **15 — Implement four already-substrate-complete metrics.**
  `thesis_resonance`, `contradiction_pressure`,
  `premise_support_density`, `market_mispricing_edge`. Each calls
  existing routines; none introduces new LLM calls beyond the
  current forecast generator path. Tests: deterministic against
  fixture conclusions.
- **16 — Implement four partially-substrate-complete metrics.**
  `source_domain_locality` (via `methods/domain_bounds`),
  `temporal_decay_pressure` (via `retrieval_adapter` staleness),
  `calibration_adjusted_confidence` (via
  `coherence/recalibration`), `liquidity_cost_feasibility`
  (extending `EdgeReport`). Tests: bounded ranges, idempotence.
- **17 — Rule graph as data.** Introduce `forecasts/rule_graph.py`
  with `RuleGraph`, `Threshold`, `Veto`, `Bucket`, `Combiner`
  node types and a JSON serializer. Replace the inlined gate list
  in `forecast_generator._trace_gate_results` with a graph
  evaluation that produces the same eight gate results plus the
  new metric-driven rules. Persist the graph version into
  `ForecastTrace`. Tests: identical gate results on existing
  fixtures.
- **18 — Causal-chain extractor.** New method
  `noosphere/noosphere/methods/causal_chain.py` (with
  `.RATIONALE.md` and `.FAILURES.yaml`) producing cause→effect
  edges from a `Claim` set. Wire `causal_chain_completeness` in
  the metric layer. Tests: known causal chains in fixtures;
  graceful degradation on ambiguous claim sets.
- **19 — Adversarial battery harness.** Promote the red-team
  prompts under `coding_prompts/16_run_redteam_tournament.txt`
  into a callable battery; compute `adversarial_fragility` as
  the metric. Budget-gated. Tests: fragility scoring monotone in
  the size of the adversarial set.
- **20 — Decision space expansion.** Extend
  `forecast_generator.generate_forecast` to emit `watch` (new
  outcome enum value, persisted as a `ForecastTrace` without a
  paper fill), and add `position_state`-aware decisions:
  `reduce`, `exit`, `hedge`. Requires reading the open paper /
  live position set. Tests: no regression in PUBLISHED outcomes;
  new outcomes covered.
- **21 — Principle revocation propagation.** When a
  `ForecastCitation` becomes `is_revoked=True`, mark the
  associated open positions for `reduce` or `exit` review and
  surface to the operator page. Tests: revocation flow end-to-end.
- **22 — Operator trace view.** Add a "Trace" mode to
  `theseus-codex/src/app/(authed)/forecasts/portfolio/ForecastPortfolioView.tsx`
  rendering the metrics, the fired rule-graph nodes, and the
  decision. Defaults to a collapsed panel under the existing
  position rows (consistent with the Round 20 contract's
  "progressive disclosure for diagnostics" principle, §1 of
  `UI_UX_Round20_Contract.md`).
- **23 — Public-facing decision rendering.** Define how (and how
  much of) a trace is publishable. The recalibration contract's
  "one-directional in display" rule extends here: the *decision*
  is publishable, the *internal metric values* are publishable in
  rounded form, the *trade actually placed* is publishable
  post-resolution, the *narrative* is generated from the trace
  fields. Build the page under
  `theseus-codex/src/app/forecasts/[id]/page.tsx`.
- **24 — Empirical case-study harness.** Replay
  `forecast_generator` against the resolution-backfill set (built
  by Round 18 prompt 18) with the new metric and rule-graph
  stack disabled vs. enabled. Persist a comparison report. This
  prompt produces evidence, not features.
- **25 — Abstract principle audit and contract close.** Survey
  whether the ten metrics in §3 of this document fired
  meaningfully across the 24-output cohort. Document drift,
  metric retirement candidates, and the next-batch additions
  (`principle_revocation_risk`, `cross_market_consistency`).
  Close the algorithmized-decision-making contract or schedule
  a revision.

Subsequent prompts (26+) — abstract-principle and empirical
case-study deep dives — are out of scope for this contract and
will be authored once 24–25 are complete.

## 7. Safety — algorithmization is not authorization

Algorithmizing a decision changes its *inspectability*, not its
*authority*. The existing live-trading safety contract is the floor,
not the ceiling.

The following constraints are inherited unchanged and MUST NOT be
weakened by any prompt above:

1. **`is_live_authorized` returns `False` from the forecast
   generator path.** `forecast_generator.is_live_authorized`
   today unconditionally returns `False`. Algorithmization does
   not flip this default. A separate, deliberate path
   (`submit_live_bet` in
   `noosphere/noosphere/forecasts/live_bet_engine.py`) handles
   live submission with the eight gates from
   `noosphere/noosphere/forecasts/safety.py`.
2. **All eight gates remain mandatory for live.**
   `live_trading_enabled`, `exchange_credentials_configured`,
   `prediction_live_authorized`, `operator_confirmation`,
   `stake_ceiling`, `daily_loss_ceiling`, `kill_switch_clear`,
   `sufficient_live_balance`. Failing any gate raises
   `GateFailure` *before* the algorithm's decision is acted on,
   regardless of how confidently the rule graph picked
   `live_candidate`.
3. **Operator confirmation is per-bet.** A confirmed bet is one
   with `status == "CONFIRMED"` and `confirmed_at is not None`.
   The rule graph cannot synthesize that timestamp.
4. **Kill-switch precedence.** A kill switch engaged by
   `daily_loss_auto_engagement_reason`,
   `exchange_error_streak_reason`,
   `calibration_degraded_reason`, or operator action overrides
   every algorithm output until `disengage_kill_switch` is
   invoked with a non-empty operator and a ≥20-char note.
5. **Trace immutability.** A persisted `ForecastTrace` is not
   rewritten after the fact. If a metric implementation changes,
   the new version is recorded on subsequent runs; old traces
   keep their old values, indexed by `method` and version
   strings.
6. **Calibration is non-mutating.**
   `noosphere.coherence.recalibration` does not modify
   `ForecastPrediction.probability_yes` or `Conclusion.confidence`;
   the algorithmized metric `calibration_adjusted_confidence` is
   an *additional* field, not a replacement.

A useful summary: the algorithm decides *what trade is logically
warranted*; the safety system decides *whether the firm is allowed
to act on it right now*. Both must agree before capital moves.

## 8. Open questions

Out-of-scope for this contract but tracked here so the §6 prompts do
not silently resolve them:

- Whether `live_candidate` should auto-expire after a market-time
  budget (e.g. 24h) if not operator-confirmed.
- Whether `hedge` outputs are constructed by the same algorithm
  that constructed the original position, or by a parallel
  pricing-of-hedges algorithm with its own trace.
- Whether the rule graph should be per-market-category or global.
  Current default: global, with category-specific thresholds as
  config overrides.
- How `principle_revocation_risk` is to be made forward-looking
  (an *estimate* of revocation probability) rather than reactive
  (`is_revoked` already True).

These are intentionally not answered here. They are the first
items the §6 prompt set will need to take a position on.

## 9. Verification

For this document specifically:

- `git diff --check` is clean.
- All cited files exist at the paths given:
  `noosphere/noosphere/forecasts/forecast_generator.py`,
  `noosphere/noosphere/forecasts/retrieval_adapter.py`,
  `noosphere/noosphere/forecasts/edge_calc.py`,
  `noosphere/noosphere/forecasts/paper_bet_engine.py`,
  `noosphere/noosphere/forecasts/live_bet_engine.py`,
  `noosphere/noosphere/forecasts/safety.py`,
  `noosphere/noosphere/coherence/` (engine, argumentation, nli,
  probabilistic, judge, calibration, recalibration,
  contradiction_direction, locality),
  `noosphere/noosphere/methods/` (domain_bounds, composition,
  failure_modes, contradiction_geometry, nli_scorer,
  citation_entailment, decompose_voice, extract_claims,
  extract_methodology),
  `noosphere/noosphere/models.py` (`ForecastTrace`,
  `ForecastPrediction`, `ForecastCitation`, `ForecastBet`),
  `theseus-codex/src/app/(authed)/forecasts/portfolio/ForecastPortfolioView.tsx`,
  `theseus-codex/src/app/(authed)/forecasts/operator/page.tsx`,
  `docs/architecture/UI_UX_Round20_Contract.md`.
- All cited APIs exist in those files: `generate_forecast`,
  `retrieve_for_market`, `build_query_from_market`,
  `compute_edge`, `EdgeReport`, `evaluate_and_stake`,
  `_stake_usd`, `PaperBetConfig`, `submit_live_bet`,
  `check_all_gates`, `evaluate_gate_results`,
  `gate_context_from_env`, `engage_kill_switch`,
  `disengage_kill_switch`,
  `daily_loss_auto_engagement_reason`,
  `exchange_error_streak_reason`,
  `calibration_degraded_reason`, `is_live_authorized`,
  `ContradictionDirection`, `evaluate_pair_with_neighbors`,
  `Verdict`, `recalibration_min_samples`,
  `load_active_record` (in `recalibration.py`),
  `_validate_forecast_citations`, `MIN_DISTINCT_SOURCES`,
  `FORECAST_RESPONSE_SCHEMA`, `_trace_principles`,
  `_trace_model_output`, `_trace_gate_results`.
- The document does not implement, alter, or schedule any
  live-trading change. It is design and inventory only.
