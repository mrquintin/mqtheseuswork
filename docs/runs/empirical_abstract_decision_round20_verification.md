# Empirical Cases, Abstract Principles, Transfer & Decision Frames — Round 20 Verification

Date: 2026-05-12
Scope: end-to-end verification that Round 20 prompts 20–24
(empirical case extraction, principle abstraction, analogical
transfer, multi-frame decision engine, founder/operator UI surfaces)
hang together — i.e. that a case ingested from a source produces a
contradiction-testable principle, that the principle can be tested
against a new event without collapsing into superficial analogy, and
that the multi-frame decision engine consumes those signals as one
input among several without letting analogy promote a decision past
its evidence.

Companion documents:

- `docs/architecture/Algorithmized_Decision_Making.md` — the contract
  this verification grounds against (§1.2 decision traces,
  §2.2 metric typing, §7 safety inheritance).
- `docs/operations/Forecasts_Founder_Alpha_Runbook.md` — operator
  surface this verification updates (§12 of the runbook is the
  empirical/abstract subsystem added by this round; see edits below).
- `docs/runs/market_system_round20_verification.md` — the market /
  decision-metric / live-execution side, verified in the previous
  report. This document assumes those verdicts hold and does not
  re-verify them.

All concrete examples in §§3–9 are drawn from test fixtures inside
`noosphere/tests/test_case_study_extraction.py`,
`noosphere/tests/test_principle_abstraction.py`,
`noosphere/tests/test_analogical_transfer.py`, and
`noosphere/tests/test_decision_frames.py`. They are labeled
`(fixture)` in the body. No live-trading-derived examples appear in
this report.

---

## 1. Commands run

All commands executed against the working tree at `main` with the
Round 20 prompts 20–24 modifications staged but not yet committed.

### 1.1 Python — focused verification suites

```sh
PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_case_study_extraction.py -q
# 8 passed in 0.26s

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_principle_abstraction.py -q
# 11 passed

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_analogical_transfer.py -q
# 12 passed

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_decision_frames.py -q
# 24 passed

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_forecast_decision_metrics.py -q
# 20 passed

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest noosphere/tests/test_forecast_scheduler_decision_metrics.py -q
# 8 passed (2 pydantic v2 migration warnings on
# conclusions.py:105 and :164; unrelated to this round)

PYTHONPATH=noosphere:current_events_api:. \
  python -m pytest current_events_api/tests/test_routes_operator.py -q
# 14 passed
```

Combined Python verification surface for this report:
**97 tests, 0 failures, 2 pre-existing warnings (Pydantic v2
class-based `config` deprecation in `noosphere/conclusions.py`).**

### 1.2 Frontend — type check and build

Prompt 24 (`24_case_principle_decision_ui_surfaces.txt`) touched
multiple authed surfaces:

- `theseus-codex/src/app/(authed)/forecasts/portfolio/ForecastPortfolioView.tsx`
- `theseus-codex/src/app/(authed)/forecasts/operator/page.tsx` and its
  `PendingAuthorizations.tsx`, `PendingConfirmations.tsx`,
  `LiveBetLedger.tsx` children
- `theseus-codex/src/app/(authed)/knowledge/page.tsx`
- `theseus-codex/src/app/(authed)/conclusions/[id]/page.tsx`,
  `actions-bar.tsx`, `FailureModesCard.tsx`, `MqsCard.tsx`
- `theseus-codex/src/app/(authed)/transcripts/[uploadId]/page.tsx` and
  `SourceStructurePanel.tsx`
- shared types: `theseus-codex/src/lib/forecastsTypes.ts`,
  `forecastPortfolioData.ts`, `forecastsOperatorApi.ts`,
  `currentsApi.ts`

```sh
cd theseus-codex
npx tsc --noEmit            # exit 0, no diagnostics
npm run build               # exit 0, "Compiled successfully in 4.7s"
                            # 75 static pages generated, no errors
```

The build trace enumerates the founder-only routes added by prompt 24:

```
ƒ /principles/[id]
ƒ /principles/queue
ƒ /transcripts/[uploadId]
ƒ /conclusions/[id]
ƒ /forecasts/portfolio
ƒ /forecasts/operator
```

### 1.3 Determinism + serialization checks

`test_decision_trace_to_dict_is_json_stable` in
`test_forecast_decision_metrics.py` confirms a decision trace
round-trips through `to_dict() → json.dumps → json.loads` byte-stably
(it is keyed by `(market_id, frame_name, metric_name)`).

`test_transfer_graph_serialization_is_stable_across_insertion_order`
and `test_transfer_graph_round_trips_through_dict` in
`test_principle_abstraction.py` confirm the transfer graph emits
byte-identical JSON across insertion permutations.

`test_report_is_deterministic_and_serializable` in
`test_analogical_transfer.py` confirms two evaluations against the
same `TransferQuery` and `AbstractPrinciple` set emit the same JSON.

These three together are the canonical evidence that the
case → principle → transfer → decision-trace chain produces
inspectable, diffable artifacts (the §1.2 contract requirement that
"prose summary is generated from the trace, never the other way
around").

---

## 2. Subsystem inventory

| Subsystem                | Module                                            | Public entry point(s)                     | Test suite                                  |
|--------------------------|---------------------------------------------------|-------------------------------------------|---------------------------------------------|
| Empirical case extraction | `noosphere/noosphere/cases/extractor.py`         | `CaseStudyExtractor.extract`              | `test_case_study_extraction.py`             |
| Case typed model         | `noosphere/noosphere/cases/models.py`             | `EmpiricalCaseStudy`, `CaseStudyExtraction` | (covered transitively)                    |
| Principle abstraction    | `noosphere/noosphere/principles/abstractor.py`    | `PrincipleAbstractor.abstract`            | `test_principle_abstraction.py`             |
| Principle typed model    | `noosphere/noosphere/principles/models.py`        | `AbstractPrinciple`, `TransferGraph`      | (covered transitively)                      |
| Analogical transfer      | `noosphere/noosphere/principles/transfer.py`      | `evaluate_transfer`, `TransferReport`     | `test_analogical_transfer.py`               |
| Multi-frame decisions    | `noosphere/noosphere/decisions/frames.py`         | `run_frames`, `FrameContext`              | `test_decision_frames.py`                   |
| Decision synthesis       | `noosphere/noosphere/decisions/synthesis.py`      | `synthesize`, `SynthesisAction`           | `test_decision_frames.py`                   |
| Decision-trace assembly  | `noosphere/noosphere/forecasts/decision_metrics.py` | `build_decision_trace`                  | `test_forecast_decision_metrics.py`         |
| UI: founder/operator     | `theseus-codex/src/app/(authed)/forecasts/*`      | `ForecastPortfolioView`, operator page    | `theseus-codex/src/__tests__/*` + tsc/build |

---

## 3. Case-study extraction examples (fixture)

Source: `noosphere/tests/test_case_study_extraction.py`. The
`CaseStudyExtractor` is LLM-backed in production; the fixtures inject
a stub LLM client so the extractor's deterministic post-validation
logic — the verbatim-quote check, the thin-case rejection, the
prompt-stripping defense — is what is actually exercised.

### 3.1 Named historical case → both layers populated

Input chunk text (fixture):

> "In 2008 Lehman Brothers failed after its leverage ratio climbed
> past 30:1 and short-term funding markets refused to roll its repo
> book. The collapse froze interbank lending and forced the U.S.
> Treasury to backstop the rest of the dealer community within a
> week."

Extracted `EmpiricalCaseStudy` (fixture):

| Field                  | Value                                                       |
|------------------------|-------------------------------------------------------------|
| `kind`                 | `named_case`                                                |
| `title`                | "Lehman Brothers failure (2008)"                            |
| `actors`               | ["Lehman Brothers", "U.S. Treasury"]                        |
| `institutions`         | ["Lehman Brothers", "U.S. Treasury", "repo market"]         |
| `time_period`          | "2008"                                                      |
| `domain`               | "finance"                                                   |
| `observed_mechanism`   | "Excess leverage combined with reliance on short-term repo funding produced a run when counterparties refused to roll." |
| `outcome`              | "Lehman collapsed; the Treasury backstopped the rest of the dealer community within a week." |
| `stated_causal_claim`  | "High leverage funded by overnight repo is fragile to a counterparty refusal to roll." |
| `evidence_quality`     | `asserted`                                                  |
| `linked_principles[0]` | "Maturity mismatch between long assets and overnight funding creates run risk." |
| `is_grounded()`        | `True` (both concrete and abstract layers populated)        |

This is the "happy path" case: concrete (actor + mechanism + outcome)
and abstract (a linked principle with a transfer condition) layers
both come back populated, the source quote is a verbatim substring of
the chunk, and `is_grounded()` flips `True`. Downstream principle
abstraction (§4) will key off this case's `linked_principles[0]`.

### 3.2 Hypothetical → captured as a non-case mention, not as evidence

Input chunk text (fixture):

> "Imagine a startup that decides to raise a Series A at twice the
> valuation its revenue can justify, just to lock out a competitor.
> Within eighteen months the down-round forces a recap and the cap
> table is destroyed."

Result: `cases=[]`, `non_case_mentions=[NonCaseMention(kind=hypothetical, …)]`.

The extractor preserves the audit trail ("the passage was about a
case, and we explicitly classified it as not-a-case") so the
distinction between "no case found" and "case found and rejected" is
inspectable. This is the
`test_hypothetical_classified_as_non_case` assertion.

### 3.3 Analogy → captured as a non-case mention

Input chunk text (fixture):

> "A founder's reaction to dilution is like a central bank's reaction
> function: the rules look discretionary, but the trajectory is
> over-determined by the structure of incentives they sit on top of."

Result: `cases=[]`,
`non_case_mentions=[NonCaseMention(kind=analogy, summary="Structural
parallel between founder dilution response and central-bank reaction
functions.")]`.

The structural parallel is recorded so downstream readers can see the
author drew it — but it never enters the empirical-evidence pool. This
is part of "do not let analogy promote to proof" enforced at
extraction time, before any transfer/decision logic runs.

### 3.4 Bare abstract concept → neither case nor fabrication

Input chunk text (fixture):

> "Markets punish overconfidence eventually, regardless of how a
> particular manager rationalizes their position sizing in the
> moment."

Result: `cases=[]`,
`non_case_mentions=[NonCaseMention(kind=abstract_concept, …)]`. No
fabricated actor or institution is invented for the "naked" principle.
The abstractor (§4.3) can still consume the bare statement via the
`AbstractOnlySource` path; the extractor refuses to backfill empirical
fields.

### 3.5 Defensive: fabricated quote is dropped

`test_quote_not_in_source_is_rejected` (fixture): the chunk text is
"The 2008 financial crisis was triggered by structural leverage." and
the LLM is stubbed to return a fully-formed `named_case` whose
`source_quote` references *Enron 2001* — text that does not appear in
the chunk. The extractor refuses to emit it; the result is
`cases == [] and non_case_mentions == []`. The same defense covers
LLM paraphrase drift and prompt-leak attacks.

### 3.6 Defensive: thin "case" with no mechanism/outcome is dropped

`test_thin_case_with_no_mechanism_is_rejected` (fixture):

> "Apple is a large technology company headquartered in Cupertino."

The LLM stub returns a `named_case` with `actors=["Apple"]` and
empty `observed_mechanism`, `outcome`, and `linked_principles`. The
extractor drops it: a name-drop is decoration, not evidence. The
`has_actor_or_institution and has_mechanism_or_outcome and principles`
gate is what enforces this in `extractor.py`.

### 3.7 Defensive: prompt text cannot become case facts

`test_prompt_text_is_stripped_before_extraction` (fixture): a written
source begins with "Prompt: Write about a fictional company called
Prompttown Inc and its CEO Q. Ficticio." followed by the analytical
body. The case extractor runs through `PromptSeparator`, the prompt
section is stripped, and only the founder/author body is forwarded to
the LLM. The fixture asserts that "Prompttown Inc" never appears as
an actor in the resulting case.

This is the same posture `noosphere.claim_extractor` uses for the
claim layer; the case layer inherits it.

---

## 4. Abstract principle examples (fixture)

Source: `noosphere/tests/test_principle_abstraction.py`. The
`PrincipleAbstractor` consumes `CaseStudyExtraction` rows and
emits typed `AbstractPrinciple` records plus the `TransferGraph` that
links them.

### 4.1 Two cases → one principle (content-addressed convergence)

`test_two_cases_abstract_to_same_principle` (fixture):

Case A — Lehman 2008 (finance, leveraged repo intermediary, roll
refusal → collapse).
Case B — Northern Rock 2007 (finance, wholesale short-term funding,
window closure → depositor run → nationalisation).

Both `linked_principles[0].principle_text` resolve, after canonical
normalization, to:

> "Maturity mismatch between long assets and overnight funding
> creates run risk."

The abstractor hashes that canonical statement
(`canonical_principle_id`) and the two cases converge on the same
`AbstractPrinciple.id`, with:

| Field                                | Value                                  |
|--------------------------------------|----------------------------------------|
| `status`                             | `refined` (two independent supporting cases) |
| `confidence.band`                    | `moderate`                             |
| `confidence.supporting_case_count`   | 2                                      |
| `supporting_case_ids`                | `["case_lehman", "case_northern_rock"]` |
| `provenance` (count, distinct chunks) | 2 (`chunk_lehman`, `chunk_nb`)        |
| Edges in `TransferGraph`             | two `CASE_INSTANTIATES`, no others     |

Each provenance row preserves the verbatim source quote, so a future
reader can trace the principle back to the sentence in either upload.

### 4.2 Cross-domain corroboration widens `scope` but caps confidence

`test_two_cases_in_different_domains_widen_scope` (fixture):

Case A — domain `finance` (leveraged broker, overnight repo →
insolvency).
Case B — domain `sovereign_debt` (sovereign rolling short-tenor debt
under a buyers' strike → default).

Both link the same canonical principle text. The merged principle
records `scope = {"finance", "sovereign_debt"}` and
`confidence.domain_breadth = 2`, but the score is capped at `≤ 0.7`
and the band stays `moderate`. Promotion to `HIGH` is delegated to
`noosphere.distillation` (cross-domain breadth is one input among
several there); the abstractor refuses to escalate to firm-level
conviction on case count alone.

This is the §1 contract requirement that "do not promote a principle
to firm-level confidence merely because it has multiple examples."

### 4.3 Abstract-only source produces a principle without a case edge

`test_abstract_only_source_creates_principle_without_case_edge`
(fixture):

> "When a coordination system rewards credential signaling over
> truth-seeking, local actors optimize for legibility rather than
> discovery."

The principle is built via `build_principle_from_abstract_source`
(rather than from a case), with:

- `preconditions = ["credentialing is rewarded", "truth-seeking is unrewarded"]`
- `failure_conditions = [FailureCondition(description=…)]`
  (required, otherwise construction fails — see §5)
- `supporting_case_ids = []`
- `status = candidate` (no supporting case yet)
- `provenance[0].extracted_from = "abstract_only"`

No `CASE_INSTANTIATES` edge is created. The graph still lists the
principle, ready to be tested against future cases.

### 4.4 Provenance chain (chunk → case → principle) is preserved

Across every fixture in this suite, the assertion is that
`principle.provenance[i].chunk_id` matches the originating chunk and
`principle.provenance[i].source_quote` is the verbatim quote from the
case's `SourceSpan`. The chain is what makes principles
*decomposable* — clicking back from a principle to its evidence
ground is one hop per layer (principle → provenance → chunk).

---

## 5. Contradiction-testable principles (fixture)

A principle that cannot be contradicted is not a principle. The
contract is enforced at construction time by
`AbstractPrinciple._needs_failure_or_negation`:

```python
@model_validator(mode="after")
def _needs_failure_or_negation(self) -> "AbstractPrinciple":
    if not self.failure_conditions and not self.negation_candidates:
        raise ValueError(
            "AbstractPrinciple must declare at least one failure_condition "
            "or negation_candidate so it is contradiction-testable"
        )
```

### 5.1 Concrete `FailureCondition` example (fixture)

From `test_failure_signal_present_drops_to_does_not_apply` and the
shared `_principle()` fixture in `test_analogical_transfer.py`:

```python
FailureCondition(
    description=(
        "A central-bank backstop is announced before counterparties withdraw."
    ),
    detectable_signal="central bank backstop announced",
    severity=PrincipleConfidence.HIGH,
)
```

The `detectable_signal` is what the transfer engine
(`_contradiction_risk` in `transfer.py`) tokenises and matches
against `TransferQuery.failure_signals_present`. A single specific
match is enough to flip the recommendation to `DOES_NOT_APPLY` (see
§6.4).

### 5.2 Concrete `NegationCandidate` example (fixture)

```python
NegationCandidate(
    statement=(
        "Long-asset / short-funding intermediaries are stable through "
        "counterparty refusal episodes."
    ),
    rationale=(
        "If true, the maturity-mismatch principle is wrong as stated."
    ),
)
```

`NegationCandidate` is a propositional negation, not a detectable
signal. It feeds the dense-overlap Jaccard test in
`_contradiction_risk` so a future case whose source-text densely
overlaps the negation statement raises `contradiction_risk` even if
no explicit failure signal was supplied.

### 5.3 Negative test: principles without either field refuse to construct

`test_abstract_only_source_without_failure_condition_or_negation_raises`
(fixture):

```python
with pytest.raises(ValueError, match="contradiction-testable"):
    AbstractPrinciple(
        id=canonical_principle_id("All swans are white."),
        canonical_statement="All swans are white.",
        # no failure_conditions, no negation_candidates
    )
```

This is the floor the §1 contract requires. A principle that cannot
contradict itself is not allowed into the graph.

### 5.4 Contradicting cases update principle status

`test_third_case_contradicts_principle` (fixture):

After Lehman + Northern Rock have given the principle `status=REFINED`,
a third case is added via a `ContradictingCaseLink`:

> A leveraged-but-deposit-insured commercial bank weathers a comparable
> short-funding shock without failing because the deposit insurance
> stabilizes the funding side.

The abstractor:

- adds the case id to `contradicting_case_ids`
- flips `status` to `contradicted`
- adds a `CASE_CONTRADICTS` edge to the graph
- *does not delete* the principle — keeping it lets future cases
  rediscover the contradiction in the trace.

`test_third_case_bounds_principle` is the matching "bound, don't
contradict" path: a `BoundingCaseLink` adds a `CASE_BOUNDS` edge and
flips status to `bounded`, but the principle remains usable inside
its now-recorded scope.

---

## 6. Analogical transfer examples (fixture)

Source: `noosphere/tests/test_analogical_transfer.py`. The transfer
engine has no LLM calls, no retrieval-adapter dependency, and no
embedding lookups; all scoring is over tokens and recorded
`AbstractPrinciple` / `EmpiricalCaseStudy` fields. The engine's
contract is that its output is *reproducible from the inputs alone*,
which is what makes it citable inside a decision trace.

### 6.1 Close structural match → `APPLIES` with bracket

`test_close_structural_match_yields_applies` (fixture):

- Principle: "Maturity mismatch between long assets and overnight
  funding creates run risk" with supporting cases Lehman (2008) and
  Northern Rock (2007).
- Query: Silvergate Capital wind-down 2023.
  - `domain="finance"`, `actors=("Silvergate Capital",)`,
    `institutions=("Silvergate Capital", "FHLB funding")`
  - `mechanism="Leveraged intermediary lost access to rolling
    short-term funding from FHLB advances as crypto deposits fled."`
  - `preconditions_present=("leveraged intermediary", "rolling
    short-term funding", "long-duration assets held to maturity")`

Result:

| Metric                | Value                                                |
|-----------------------|------------------------------------------------------|
| `structural_fit`      | ≥ 0.45 (composite of precondition, mechanism, outcome) |
| `mechanism_match`     | > 0.10                                               |
| `closest_case_ids`    | ⊇ {`case_lehman`, `case_northern_rock`}              |
| recommendation stance | `APPLIES`                                            |
| `confidence`          | bounded in `(0.1, 0.9)` — never reaches 1.0          |

The capped confidence is deliberate: the transfer engine cannot turn
analogy into proof. Downstream `build_decision_trace` consumes the
report as one input among several.

### 6.2 Superficial keyword match → not `APPLIES` (rejection)

`test_keyword_only_match_falls_short_of_applies` (fixture):

- Same principle (Lehman/Northern Rock support).
- Query carries deliberately empty structural fields:
  - `source_text="leverage funding short-term long-duration assets
    repo intermediary liquidity"` — keyword-soup.
  - No `mechanism`, no `preconditions_present`, no `actors`, no
    `institutions`, no `outcome_question`.

Result:

| Metric                | Value                                                |
|-----------------------|------------------------------------------------------|
| `structural_fit`      | < 0.45 (below the `APPLIES_FIT_FLOOR`)               |
| recommendation stance | `WATCH` or `ABSTAIN` (never `APPLIES`)               |
| `reasons`             | contains `"structural_fit"` / `"APPLIES floor"`      |
| `report.best_stance`  | `!= APPLIES`                                         |

This is the verification example required by the prompt: a query that
shares the principle's *vocabulary* but lacks the *structure* must not
be promoted to `APPLIES`. The engine's posture is "vocabulary overlap
without precondition coverage and mechanism alignment is a
suspicion, not a match."

### 6.3 Cross-domain structural match → `WATCH`

`test_cross_domain_structural_match_downgrades_to_watch` (fixture):

- Principle scope restricted to `["finance"]` (sovereign-debt cases
  were never recorded as supporting).
- Query: "Country X 2026 funding crisis", `domain="sovereign_debt"`,
  with a clean mechanism match and three preconditions present.

Result: `domain_shift ≥ 0.7`, `stance = WATCH`, reasons include the
domain-shift signal. The engine surfaces the principle as worth
watching but refuses `APPLIES` because the scope was never empirically
extended to sovereign debt. (Compare §4.2: a different supporting
case in sovereign debt would have widened the scope and removed this
gate; the principle here has only finance cases.)

### 6.4 Failure signal present → `DOES_NOT_APPLY`

`test_failure_signal_present_drops_to_does_not_apply` (fixture):

- Same principle.
- Query mechanism and preconditions are clean, but
  `failure_signals_present=("central bank backstop announced",)` —
  the principle's recorded failure-condition `detectable_signal`.

Result: `contradiction_risk ≥ 0.5`, `stance = DOES_NOT_APPLY`,
`report.best_stance = DOES_NOT_APPLY`. A single specific failure
signal vetoes the transfer even when every other axis aligns.

### 6.5 Single supporting case cannot reach `APPLIES`

`test_single_supporting_case_cannot_reach_applies` (fixture): even a
structurally perfect Silvergate-style query, against a principle that
has only `case_lehman` as a supporting case, drops to `WATCH`.
`MIN_CLOSE_CASES = 2`. This is the §1 constraint "do not let a single
case dominate."

### 6.6 Monitoring hooks (Currents / market / upload)

`query_from_currents_event`, `query_from_market`, `query_from_upload`
(all fixture-verified) convert producer-side records into
`TransferQuery` objects without any extractor pass. Verified
behaviors:

- `query_from_currents_event` pulls `id`, `topic` (→ domain), `actors`,
  and `observed_at` from a dict or duck-typed event object.
- `query_from_market` mirrors the recipe in
  `noosphere.forecasts.retrieval_adapter.build_query_from_market`: the
  market `title` becomes `outcome_question`, the `description` +
  `resolution_criteria` become `source_text`, the `category` becomes
  `domain`.
- `query_from_upload` normalizes `disciplines` (string or list) into a
  `domain`, pulls `body`/`text` into `source_text`, and is robust to
  missing fields (the engine downgrades, never raises).

These hooks are what make "every new upload / new Currents event /
new market price becomes a candidate transfer query" a wire, not a
manual step.

---

## 7. Multi-frame decision traces (fixture)

Source: `noosphere/tests/test_decision_frames.py` and
`test_forecast_decision_metrics.py`. The frame engine is the §1.2
contract's "rule graph as data": each frame is a deterministic rule
that consumes a typed `MetricView` (or transfer summary) and emits a
typed `FrameVerdict`. Synthesis is a separate, deterministic rule
over the frame outputs.

Seven frames in the default `DEFAULT_FRAMES` list:

1. `incentive_alignment` — caller-supplied conflict signals (e.g.
   `issuer_conflict`) force `HARD_STOP`.
2. `coordination_equilibrium` — tiny edge (no consensus break) or
   absurdly huge edge (mispricing implausible) → `WATCH`.
3. `principal_agent` — revoked principle on an open position → `EXIT`;
   side flip → `REDUCE`.
4. `reflexivity` — high temporal decay or feedback-prone edges →
   downgrade.
5. `option_value` — low confidence + time remaining → `WATCH` (wait,
   don't act).
6. `contradiction` — `contradiction_pressure` above
   `CONTRADICTION_HARD_STOP` (0.55 per the constants) → hard-stop
   ABSTAIN.
7. `empirical_transfer` — consumes a `TransferReport`; `APPLIES` →
   `SUPPORT`, `WATCH`/`DOES_NOT_APPLY` → downgrade, missing report
   → `ABSTAIN`.

### 7.1 All frames agree → `SUPPORT` (fixture)

`test_scenario_all_frames_agree_on_trade`: a strong-metrics
`FrameContext` (`thesis_resonance=0.78`, `contradiction_pressure=0.10`,
edge=0.11, decay=0.15, calibration good) plus
`transfer_best_stance="APPLIES"` and four supporting recommendations.
All seven frames vote `SUPPORT`, synthesis emits `SUPPORT`, side
preserved.

### 7.2 Transfer supports but incentive frame blocks → `ABSTAIN` (fixture)

`test_scenario_transfer_supports_but_incentive_frame_blocks`: same
metrics, transfer still `APPLIES`, but the caller adds
`incentive_signals=("issuer_conflict",)`. `incentive_alignment` flips
to `HARD_STOP`, `empirical_transfer` stays `SUPPORT`, synthesis emits
`ABSTAIN` with `hard_stop_frames` listing `incentive_alignment`. This
demonstrates that no single frame — including a strong empirical
transfer signal — can override a hard-stop in another frame.

### 7.3 Contradiction frame forces abstain (fixture)

`test_scenario_contradiction_frame_forces_abstain`:
`contradiction_pressure = CONTRADICTION_HARD_STOP + 0.1` collapses
to `ABSTAIN` regardless of how favourable every other frame is. The
contradiction frame is the always-true veto on the §1 list.

### 7.4 Reflexivity downgrades a naive edge (fixture)

`test_scenario_reflexivity_downgrades_naive_edge`: edge=0.22 (large)
combined with `decay=0.7` (high temporal-decay pressure on the
load-bearing citations) trips `reflexivity → WATCH`. Synthesis must
not return `SUPPORT`; the actual outcome is `WATCH` or `ABSTAIN`
depending on what `coordination_equilibrium` says about the edge
magnitude. The intuition: an edge that's "obviously big" combined
with stale evidence is a feedback-loop pattern, not a signal — the
crowd has had time to price it.

### 7.5 Synthesis is deterministic on assembled frames

`test_synthesis_all_support_returns_support`,
`test_synthesis_hard_stop_forces_abstain_even_with_majority_support`,
`test_synthesis_exit_overrides_supports`,
`test_synthesis_unstable_assumptions_force_abstain`, and
`test_synthesis_split_returns_watch` together pin the synthesis rule:

- Any `HARD_STOP` → `ABSTAIN` (regardless of `SUPPORT` majority).
- Any `EXIT` → `EXIT` (position management overrides new-trade votes).
- Too many `UNSTABLE` verdicts → `ABSTAIN`.
- Split votes (no hard-stop, no majority) → `WATCH`.
- Clean majority `SUPPORT` with no hard-stop → `SUPPORT`.

There is no LLM in this path; the synthesis trace is reproducible.

---

## 8. Market/forecast example — empirical transfer affects the action (fixture)

`test_decision_trace_downgrades_when_transfer_says_does_not_apply` in
`test_analogical_transfer.py` is the canonical example. Same setup
exists for `WATCH` in
`test_decision_trace_downgrades_live_to_watch_on_transfer_watch`.

Setup (fixture):

- `_FakeForecastMarket(id="mkt", title="Will the policy bill pass
  before June?", category="policy", current_yes_price=0.45,
  current_no_price=0.55, status="OPEN")`.
- Three policy-aligned sources (`c_a`, `c_b`, `c_c`), each with
  `disciplines=["policy"]` and dated 20 days before now; three
  `DIRECT` citations into them; clears the
  `min_distinct_sources=3` floor.
- `payload={probability_yes=0.75, confidence_low=0.70,
  confidence_high=0.80, topic_hint="policy"}` — a confident YES, 0.30
  edge over current price.
- `calibration_state` provides a per-domain factor of 1.0 for `policy`
  and a sample count above the `recalibration_min_samples` floor.

Without an empirical transfer signal, the trace reaches
`LIVE_CANDIDATE` (strong edge, in-domain, well-calibrated, three
distinct sources). With a `TransferReport(best_stance=DOES_NOT_APPLY)`
attached — built from a principle whose recorded failure signal was
tripped by the new event — the trace adds a rule overlay named
`analogical_transfer`, that overlay fires, and the action drops to
`ABSTAIN`.

Key assertions (fixture, verified to pass):

```python
trace = build_decision_trace(
    market=_FakeForecastMarket(),
    sources=_policy_sources(),
    citations=_direct_citations(),
    payload={…},
    calibration_state={…},
    now=NOW,
    min_distinct_sources=3,
    transfer_report=report,   # best_stance=DOES_NOT_APPLY
)

assert trace.action == MarketDecisionAction.ABSTAIN
overlay = next(r for r in trace.rules if r.name == "analogical_transfer")
assert overlay.fired is True
body = trace.to_dict()
assert body["analogical_transfer"]["best_stance"] == "DOES_NOT_APPLY"
```

The §1 contract requirement is "analogy can only *downgrade*, never
escalate." This test pins it: the same inputs without the transfer
report give `LIVE_CANDIDATE`; with `DOES_NOT_APPLY` they give
`ABSTAIN`. The trace records *why* (the overlay rule's `fired=True`
and the report's `best_stance` are both inspectable).

`test_decision_trace_no_transfer_report_is_backwards_compatible`
pins the corollary: omitting the transfer report leaves the legacy
decision behaviour intact. The metric layer + rule graph from prompts
14–18 still drive the decision; the analogical overlay is purely
additive.

---

## 9. Superficial-analogy rejection example (fixture)

§6.2 above (`test_keyword_only_match_falls_short_of_applies`) is the
required rejection example.

Concretely: the same principle that earned `APPLIES` for the
Silvergate query in §6.1 is given a query whose `source_text` is a
keyword-soup of "leverage funding short-term long-duration assets repo
intermediary liquidity" with no structural fields populated. The
engine refuses to escalate it:

- `structural_fit < 0.45` (the `APPLIES_FIT_FLOOR`).
- Recommendation `stance ∈ {WATCH, ABSTAIN}`, never `APPLIES`.
- `report.best_stance != APPLIES`.
- The reasons list contains `"structural_fit"` / `"APPLIES floor"`
  text, so the rejection is auditable in the recommendation row.

The analogue scenario inside the decision frames is
`test_empirical_transfer_does_not_apply_hard_stops_when_supported`
in `test_decision_frames.py`: a transfer report with `DOES_NOT_APPLY`
and ≥ MIN_ELIGIBLE_FRAMES_FOR_SUPPORT principles considered makes the
`empirical_transfer` frame emit `HARD_STOP`, propagating to synthesis
`ABSTAIN`.

The substantive content of both rejections is the same: *a
superficial match is not a structural match, and the system has a
named place to record that distinction* (the recommendation's
reasons list, the frame verdict, the decision-trace overlay).

---

## 10. UI surface verification

Prompt 24 added founder/operator UI surfaces. The browser verification
is *type-and-route checked only* in this run — an authenticated
visual walkthrough is the next-session item, matching the §5 caveat
in `market_system_round20_verification.md`.

Type/route checks (verified above):

- `npx tsc --noEmit` exits clean.
- `npm run build` compiles 75 static pages, no errors. The build
  trace enumerates the new founder-only routes:
  - `/principles/[id]`, `/principles/queue` — case/principle browse
    surfaces.
  - `/transcripts/[uploadId]` — exposes per-source case studies and
    abstracted principles via `SourceStructurePanel.tsx`.
  - `/conclusions/[id]` — case-vs-principle-vs-decision-rule kind
    label.
  - `/forecasts/portfolio` — embeds the decision-trace panel that
    surfaces frame results and analogical-transfer overlay.
  - `/forecasts/operator` — kill-switch panel + pending authorizations
    / confirmations + live ledger.

Private-source visibility check: the public routes
(`/forecasts`, `/currents`, `/post/[slug]`) do not render
case/principle metadata; that surface is gated behind the
`(authed)` middleware. The `forecastPortfolioData.ts` and
`forecastsOperatorApi.ts` helpers carry the visibility flag through;
the `forecasts/portfolio` route is `307` → `/login?next=…` for an
anonymous probe (verified in
`market_system_round20_verification.md` §5 and unchanged in this
round).

---

## 11. Constraint check

- **No fabricated verification examples.** Every concrete example
  in §§3–9 is a fixture in the named test file, labeled `(fixture)`
  in the body. No live trade was executed; no real upload's source
  text appears verbatim. The single-line quotes in §§3–4 are the
  exact strings authored inside the test files for the purpose of
  exercising the extractor, not text scraped from a live source.
- **No claim of live trading readiness.** This document does not
  re-verify the live-execution chain; it cites the prior
  `market_system_round20_verification.md` §§7–8 verdicts (paper-mode
  READY, live-mode CONDITIONALLY READY pending environment
  configuration). Nothing in prompts 20–24 changes those verdicts;
  the analogical-transfer overlay can only *downgrade* a decision,
  and the eight live-trading safety gates in
  `noosphere/noosphere/forecasts/safety.py` are inherited unchanged.
- **No private source text exposed.** Fixture text is invented for
  the test and is the only verbatim text in this document; private
  upload bodies are not referenced.

---

## 12. Verdicts

**Empirical case extraction:** ready. The extractor correctly
distinguishes named cases, brief examples, hypotheticals, analogies,
and abstract concepts, refuses to fabricate cases from
non-grounded quotes, refuses to extract case facts from prompt text,
and rejects thin "cases" that lack mechanism/outcome. Eight fixture
tests pass.

**Principle abstraction:** ready. Two cases with the same canonical
principle text converge on a content-addressed `AbstractPrinciple.id`
with refined status; cross-domain corroboration widens scope without
escalating the confidence band past `moderate`; bounding and
contradicting cases produce typed graph edges; abstract-only sources
produce principles without case edges. Eleven fixture tests pass.

**Contradiction testability:** enforced. `AbstractPrinciple`
construction refuses any principle that lacks both
`failure_conditions` and `negation_candidates`. The transfer engine
consumes both. The negative-construction test
(`test_abstract_only_source_without_failure_condition_or_negation_raises`)
pins the floor.

**Analogical transfer:** ready. Structural matches earn `APPLIES`
with capped confidence; superficial keyword matches drop to
`WATCH`/`ABSTAIN`; cross-domain structural matches drop to `WATCH`;
recorded failure signals drop to `DOES_NOT_APPLY`; a single supporting
case cannot reach `APPLIES`. Twelve fixture tests pass, including
the determinism check.

**Multi-frame decisions:** ready. Twenty-four fixture tests pin the
frame-by-frame and synthesis behavior. Hard-stops in any frame
(`contradiction`, `incentive_alignment`, `empirical_transfer
DOES_NOT_APPLY`) force `ABSTAIN`; `EXIT` overrides `SUPPORT`; split
votes go to `WATCH`; clean majorities with no hard-stop go to
`SUPPORT`.

**Decision-trace integration:** ready. `build_decision_trace`
accepts an optional `transfer_report` and adds an
`analogical_transfer` overlay rule. The overlay can only downgrade
the decision; it cannot escalate. The trace round-trips through
`to_dict` byte-stably.

**Operator UI surfaces:** ready as code, browser-walkthrough
pending. `npx tsc --noEmit` clean, `npm run build` clean, founder
routes enumerated; visibility rules unchanged from the prior round.

**Overall:** the case → principle → transfer → decision-frame chain
holds end-to-end on fixture inputs, with the §1 contract's
constraints enforced at every step (analogy never proves; superficial
similarity is rejected; principles must be contradiction-testable;
the trace is inspectable and reproducible).

---

## 13. Cross-references

- `docs/architecture/Algorithmized_Decision_Making.md` — design floor
  (especially §1.2 trace contract, §2.2 metric typing, §3 metric
  catalog, §7 safety inheritance).
- `docs/operations/Forecasts_Founder_Alpha_Runbook.md` — operator
  runbook; §12 added by this round describes the empirical/abstract
  subsystem.
- `docs/runs/market_system_round20_verification.md` — market /
  decision-metric / live-execution verification. This report
  presupposes those verdicts.
- `docs/runs/ui_ux_round20_verification.md` — parallel UI/UX
  Round 20 verification.
- `noosphere/noosphere/cases/` — case extraction module.
- `noosphere/noosphere/principles/` — principle abstraction, transfer
  engine, transfer graph.
- `noosphere/noosphere/decisions/` — multi-frame decision engine and
  synthesis.
- `noosphere/noosphere/forecasts/decision_metrics.py` —
  `build_decision_trace` that fuses metrics, frames, and transfer
  into a single inspectable trace.
