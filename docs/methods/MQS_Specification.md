# Methodology Quality Score (MQS) — Specification v1.0.0

Status: source of truth for the operational MQS attached to every Conclusion
that has at least one MethodologyProfile. The five sub-scores are the working
criteria from `THE_META_METHOD.md`, lifted from prose into something the firm
can compute, audit, and revise.

This is the **first formal version** of the specification. The Round 17
prompt 01 draft was prose plus worked examples; this version states the exact
composite formula, the exact gating function, the closed-form of every
sub-score, the boundary cases, and a registry of every constant. The worked
examples now live where they belong — `docs/methods/Aim_Method_Fit_Rubric.md`
for that criterion's rubric — and this file is the precise specification.

The spec is checked against the running code (`noosphere/noosphere/evaluation/mqs.py`)
by `scripts/check_mqs_doc_consistency.py`; CI fails if they drift. A
PDF rendering with numbered equations is `docs/methods/MQS_Specification.pdf`,
built from `docs/methods/MQS_Specification.tex`.

The PDF and this file are the same specification; where this file is precise
the PDF restates it in standard math notation, and the equation numbers below
in brackets — e.g. *(eq. 6)* — refer to the PDF.

## Schema name

`MQS_SCHEMA = "theseus.mqs.v1"`

## 1. Notation

| Symbol | Type | Meaning |
| ------ | ---- | ------- |
| `c` | Conclusion | the conclusion being scored — carries `conclusion_text`, `rationale`, `topic_hint`, and links to forecasts, dissent claims, and a domain bound. |
| `M(c)` | set of MethodologyProfile | the methodology profiles attached to `c`. May be empty. |
| `m` | MethodologyProfile | one method in `M(c)`. |
| `s_P` | float in `[0,1]` | progressivity sub-score. |
| `s_S` | float in `[0,1]` | severity sub-score. |
| `s_AMF` | float in `[0,1]` | aim-method fit sub-score. |
| `s_C` | float in `[0,1]` | compressibility sub-score. |
| `s_DS` | float in `[0,1]` | domain-sensitivity sub-score. |
| `MQS(c)` | float in `[0,1]` | the composite. |

Derived typed inputs, all read from `c` and `M(c)`:

- `F(c) ∈ ℕ` — `forecast_count`, number of `ForecastPrediction` rows linked
  to `c` (counted by the upstream caller; defaults to 0).
- `B(c) ∈ {0,1}` — `has_check_back_date`, 1 iff `c` carries a future
  validation date.
- `R(c) ∈ ℕ` — decision-rule phrase count: the number of regex matches of
  the decision-rule pattern in `conclusion_text + " " + rationale`. The
  pattern detects "if … then", "we will / we'll", "exit if", "by `<year>`",
  "by Q`<n>`", "check back", "trigger", "would falsif…", "will revisit".
- `FM(c) = ⋃_{m ∈ M(c)} failure_modes(m)` — the concatenated failure-mode
  list across all profiles (list, not set; duplicates are kept).
- `A(c) = ⋃_{m ∈ M(c)} assumptions(m)` — the concatenated assumption list;
  `n = |A(c)|`.
- `D(c) ∈ ℕ` — `dissent_claim_count`, the number of dissent claims on `c`.
- `j_S, j_DS ∈ [0,1] ∪ {⊥}` — the LLM judge's numeric scores for severity
  and domain sensitivity (`⊥` = the judge produced no number).
- `κ ∈ [0,1] ∪ {⊥}` — `severity_track_record_ceiling`, an upper cap on
  `s_S` derived from the method's `MethodTrackRecord` (`⊥` = no cap).
- `δ ∈ (0,1]` — `severity_drift_penalty`, a multiplicative penalty on `s_S`
  from inherited drift state across the method's composition DAG.
- `ω ∈ (0,1]` — `objection_severity_penalty`, a multiplicative penalty on
  `s_S` from the severity-weighted peer-review objection aggregate.
- `v ∈ {in_bounds, edge_case, out_of_bounds} ∪ {⊥}` — `domain_bound_verdict`,
  the orchestrator's verdict from checking `c` against the method's declared
  `DomainBound` (`⊥` = no bound declared / not checked).

`clamp(x)` maps `x` to `[0,1]`, and maps `NaN` to `0`. Every sub-score formula
below is **total**: it is defined for every input, including the empty-profile
case (see §6, Boundary cases). The LLM judge produces sub-score *evidence* and,
for two sub-scores, a numeric input `j_S` / `j_DS`; the formulas themselves
are arithmetic on numbers — no formula calls an LLM judge.

## 2. Score domain

Each sub-score is in the closed interval `[0,1]`. The composite is in `[0,1]`.

Each sub-score also emits an evidence blob: a small, human-auditable JSON
object naming the rule(s) that fired, the inputs they read, and the produced
score. Evidence must round-trip through Prisma `Json` without truncation; each
evidence string is capped at `EVIDENCE_STR_CAP` characters.

## 3. Sub-scores

### 3.1 progressivity (`s_P`) — deterministic

Question: did the analysis produce a prediction, implication, or decision rule
that can later be checked?

Inputs: `F(c)`, `B(c)`, `R(c)`. No LLM input. The score is a piecewise
constant, evaluated top to bottom — the **first** matching clause wins
*(eq. 1)*:

```
s_P = 1.00   if  B(c) = 1  ∧  F(c) ≥ 2  ∧  R(c) ≥ 1
      0.85   if  (B(c) = 1 ∧ F(c) ≥ 1)  ∨  F(c) ≥ 2
      0.65   if  B(c) = 1  ∨  F(c) ≥ 1
      0.40   if  R(c) ≥ 1
      0.00   otherwise
```

### 3.2 severity (`s_S`) — deterministic floor, LLM-judged, then deterministic caps

Question: would the procedure that produced this conclusion have caught the
claim if it were false?

Inputs: `FM(c)`, `D(c)`, `j_S`, `κ`, `δ`, `ω`. The score is computed in five
stages *(eq. 2–6)*; each later stage can only lower the score relative to the
LLM judge's number, never raise it past a deterministic bound:

1. **Deterministic floor** *(eq. 2)*:
   `floor = min(1, SEVERITY_FAILURE_MODE_FLOOR_STEP · |FM(c)| + SEVERITY_DISSENT_FLOOR_STEP · D(c))`.
2. **Judge, floored** *(eq. 3)*: `s_S⁽⁰⁾ = max(floor, clamp(j_S))`. If
   `j_S = ⊥` it is treated as `0`, so `s_S⁽⁰⁾ = floor`.
3. **No-failure-modes cap** *(eq. 4)*: if `FM(c) = ∅ ∧ D(c) = 0` then
   `s_S⁽¹⁾ = min(s_S⁽⁰⁾, SEVERITY_NO_FAILURE_MODES_CAP)`, else
   `s_S⁽¹⁾ = s_S⁽⁰⁾`. A method that lists no way it could fail is by
   construction not severe.
4. **Track-record ceiling** *(eq. 5)*: if `κ ≠ ⊥` then
   `s_S⁽²⁾ = min(s_S⁽¹⁾, clamp(κ))`, else `s_S⁽²⁾ = s_S⁽¹⁾`. A method with a
   thin or poorly calibrated `MethodTrackRecord` cannot project high severity
   onto new conclusions in its domain.
5. **Multiplicative penalties** *(eq. 6)*: `s_S = s_S⁽²⁾ · δ · ω`. Drift
   penalty `δ` is applied before objection penalty `ω`; both are in `(0,1]`,
   so each can only lower the score. `δ` is the documented drift multiplier
   (`OK`/`INSUFFICIENT` → 1.00, `WARN` → 0.85, `ESCALATE` → 0.65; the source
   of truth is `noosphere.decay.method_drift_policies.severity_penalty_multiplier`,
   composed across the method's DAG). `ω` is the severity-weighted
   peer-review objection aggregate (`noosphere.peer_review.severity.aggregate`).

Drift and objection penalties touch only Severity. A method's recent
calibration and its open objections tell us how much to trust *this* claim of
having considered counter-evidence; they do not touch Domain Sensitivity,
Compressibility, etc.

### 3.3 aim_method_fit (`s_AMF`) — deterministic

Question: is the method actually capable of answering the question being
asked?

Since prompt 31 this sub-score is **deterministic** — no LLM judge. It is the
five-level rubric in `noosphere/noosphere/inquiry/aim_method_fit.py`, driven by
the question typology in `noosphere/noosphere/inquiry/question_typology.py`.
The full rubric, with at least two worked examples per level, is in
`docs/methods/Aim_Method_Fit_Rubric.md`; that file is the source of truth for
the rubric and this section specifies only the mapping into the MQS.

Let `ℓ ∈ {0,1,2,3,4}` be the rubric level the deterministic scorer assigns to
`c`. Then *(eq. 7)*:

```
s_AMF = ℓ / 4
```

so `s_AMF ∈ {0.00, 0.25, 0.50, 0.75, 1.00}`. Level logic, summarized: the
question type is inferred from `c`'s target text and topic hint; if it is in
the set of question types the producing methods serve, `ℓ = 4` when a serving
method declares failure modes (an articulated boundary) and `ℓ = 3`
otherwise; if the served types overlap the question's decomposition,
`ℓ = 2`; if they overlap an adjacent type, `ℓ = 1`; otherwise `ℓ = 0`. A
conclusion with no profiles, or whose every method is unregistered, is `ℓ = 2`
("cannot verify fit", not "fits nothing").

This criterion is kept distinct from `domain_sensitivity`: Aim-Method Fit asks
whether the method's *output shape* is the answer shape the question demands;
Domain Sensitivity asks whether the conclusion is inside the method's *domain*.
A method can be squarely in-domain and still misfit the question.

### 3.4 compressibility (`s_C`) — deterministic, LLM-pruned

Question: how many independent assumptions must hold for the conclusion to
survive?

Inputs: `n = |A(c)|`, and a decorative-assumption count `d` from the LLM judge.
The judge classifies assumptions as load-bearing or decorative; `d` is clamped
to `[0, n]`. The **effective assumption count** is *(eq. 8)*:

```
n' = max(1, n − d)
```

— it cannot fall below 1. The score is *(eq. 9)*:

```
s_C = 1 / (1 + (n' − 1) · COMPRESSIBILITY_PENALTY_STEP)
```

With `COMPRESSIBILITY_PENALTY_STEP = 0.25`: `n' ∈ {0,1} → 1.00`, `2 → 0.80`,
`3 → 0.67`, `4 → 0.57`, `5 → 0.50`. The LLM only ever reduces `n` (via `d`);
it cannot raise `s_C` above what the raw assumption count allows.

### 3.5 domain_sensitivity (`s_DS`) — LLM-judged with deterministic verdict override; acts as the gate

Question: where should this method stop being trusted, and is the current
conclusion inside or outside that domain?

Inputs: `FM(c)`, `j_DS`, `v` (the domain-bound verdict). The score is
*(eq. 10)*:

```
s_DS = 0                                              if v = out_of_bounds
       min(s_DS⁰, EDGE_CASE_DOMAIN_CEILING)            if v = edge_case
       s_DS⁰                                          otherwise
```

where the pre-verdict score `s_DS⁰` is *(eq. 11)*:

```
base   = clamp(j_DS)               if j_DS ≠ ⊥
         DOMAIN_BACKFILL_DEFAULT   if j_DS = ⊥
floor  = DOMAIN_NO_FAILURE_MODES_FLOOR   if FM(c) = ∅
         0                               otherwise
s_DS⁰  = max(base, floor)
```

The pieces, in words:

- An `out_of_bounds` verdict is a hard zero — the orchestrator has already
  established the conclusion is outside the method's declared `DomainBound`,
  and `s_DS = 0` gates the composite to 0 (§5).
- An `edge_case` verdict caps `s_DS` at `EDGE_CASE_DOMAIN_CEILING = 0.4`; the
  composite stays continuous (it is not forced to 0 by the verdict, only by
  the gate if `0.4 < θ`, which it is not).
- The **deterministic floor** `DOMAIN_NO_FAILURE_MODES_FLOOR = 0.10` keeps a
  method with no declared failure modes from scoring 0 on domain sensitivity —
  its domain claim is *unverifiable*, not *failed*. This floor is deliberately
  **below** the gate threshold `θ` (§5): the floor protects the sub-score's
  honesty, but it is not on its own enough to open the gate.
- When no LLM judge is available (the backfill path), `j_DS = ⊥` and
  `base = DOMAIN_BACKFILL_DEFAULT = 0.5` — uncertain, not failed.

## 4. The five sub-scores feed the composite as numbers

Two sub-scores (`s_S`, `s_DS`) take a number from the LLM judge as one input
among several; the other three are fully deterministic. In every case the
**formula is arithmetic on numbers** — `clamp`, `min`, `max`, `·`, `/`,
piecewise selection. The LLM judge's role is to produce (a) the numeric inputs
`j_S` and `j_DS`, and (b) the human-readable evidence rationale. The composite
never consults a judge. This is what makes the MQS auditable: a reviewer can
recompute every number from the typed inputs, and contest the judge's `j_S` /
`j_DS` and the evidence blobs independently.

## 5. Composite

Domain Sensitivity is a **gate**, not a weighted addend and — since this
formal version — not a soft multiplicative penalty either. The composite is a
piecewise function of `s_DS` *(eq. 12)*:

```
MQS(c) = 0                                                 if s_DS < θ
         wgeomean(s_P, s_S, s_AMF, s_C)                    if s_DS ≥ θ
```

with the gate threshold `θ = DS_GATE_THRESHOLD = 0.15`. The gate is **closed
on the passing side**: `s_DS` exactly equal to `θ` opens the gate.

The combining operator for the four non-gate sub-scores is the **weighted
geometric mean** *(eq. 13)*:

```
wgeomean(s_P, s_S, s_AMF, s_C) = s_P^w_P · s_S^w_S · s_AMF^w_AMF · s_C^w_C
```

where the weights are the `SUBSCORE_WEIGHTS` exponents (§5.2), summing to 1.
With the four weights equal at `0.25`, this is `(s_P · s_S · s_AMF · s_C)^(1/4)`.

The canonical formula string, checked verbatim by
`scripts/check_mqs_doc_consistency.py`:

`COMPOSITE_FORMULA = "composite = 0 if domain_sensitivity < DS_GATE_THRESHOLD else wgeomean(progressivity, severity, aim_method_fit, compressibility)"`

### 5.1 Why a piecewise gate, and why the weighted geometric mean

**The gate is piecewise, not soft.** The Round 17 prose draft used
`composite = domain_sensitivity · mean(other four)` — a soft penalty in which
`s_DS = 0.5` merely *capped* the composite at 0.5. That let a borderline
domain fit be averaged against strong scores elsewhere. The firm's stated
position is stronger than that: a method pointed outside its domain is not
producing a *worse* answer, it is producing an answer the firm has no basis to
trust at all. So below `θ` the composite is exactly 0 — a hard verdict — and at
or above `θ` Domain Sensitivity has done its job as a gate and does not also
scale the magnitude. (See §8, Changelog, for the explicit code-and-spec change
this formalization made.)

**The operator is the weighted geometric mean.** The choice was between the
minimum, the harmonic mean, and the weighted geometric mean — three operators
that all share the property the firm wants: a single collapsed sub-score
collapses the composite (no redemption — a strong axis cannot paper over a
failed one). Among them:

- The **minimum** discards information: three of the four sub-scores carry no
  signal once they are not the smallest. An auditable composite should move
  when *any* input moves.
- The **harmonic mean** keeps all four, but is so dominated by the smallest
  value that the other three barely register.
- The **weighted geometric mean** keeps all four with proportional weight,
  still refuses redemption (it is 0 whenever any input is 0; *(eq. 14)*), and
  is the exact multiplicative analogue of the prose draft's arithmetic mean —
  the same `SUBSCORE_WEIGHTS` map, used as exponents instead of coefficients.
  It satisfies the formal claims the compliance test checks: monotone
  non-decreasing in each of the four arguments, equal to 1 iff all four inputs
  are 1, and confined to `[0,1]`.

The weighted geometric mean is the choice.

### 5.2 Sub-score weights

The canonical sub-score weights — the exponents of the weighted geometric
mean:

```
SUBSCORE_WEIGHTS = {
    "progressivity": 0.25,
    "severity": 0.25,
    "aim_method_fit": 0.25,
    "compressibility": 0.25,
}
```

They sum to 1. Domain Sensitivity is not in this map because it is the gate,
not a weighted addend.

## 6. Boundary cases

A formal spec must say what happens at every edge. Each boundary below is
stated as a rule and is pinned by a named test in
`noosphere/tests/test_mqs_spec.py`.

### 6.1 A sub-score with insufficient data

No sub-score is ever *undefined*. Every formula in §3 is total, with an
explicit fallback when its inputs are thin:

- **No profiles attached** (`M(c) = ∅`, so `FM(c) = ∅` and `A(c) = ∅`):
  `s_P` is still computed from `c` alone; `s_S` has `floor = 0` and, since
  `FM(c) = ∅ ∧ D(c) = 0`, is capped at `SEVERITY_NO_FAILURE_MODES_CAP = 0.35`;
  `s_AMF = 0.5` (rubric level 2, "cannot verify fit"); `s_C` has `n = 0` so
  `n' = 1` and `s_C = 1.0`; `s_DS` has `floor = DOMAIN_NO_FAILURE_MODES_FLOOR`
  and, with no LLM, `base = DOMAIN_BACKFILL_DEFAULT = 0.5`.
- **No LLM judge** (`j_S = ⊥`, `j_DS = ⊥`): `s_S⁽⁰⁾ = floor`;
  `s_DS` uses `base = DOMAIN_BACKFILL_DEFAULT`. The score is still produced,
  fully deterministically — this is the backfill path.

The principle: insufficient data resolves to a *defined, conservative*
number, never to a missing value. Test: `test_no_profiles_every_subscore_is_defined`,
`test_no_judge_is_fully_deterministic`.

### 6.2 At the gating threshold

The gate condition is the strict inequality `s_DS < θ`. Therefore
`s_DS = θ` exactly **opens** the gate — the boundary point belongs to the
passing side. `s_DS = θ − ε` for any `ε > 0` closes it and the composite is 0.
The composite is discontinuous at `θ`: just below, it is 0; at `θ` it jumps to
`wgeomean(s_P, s_S, s_AMF, s_C)`. This discontinuity is intentional — it is
what makes the gate a verdict rather than a dial. Test:
`test_gate_boundary_is_closed_on_passing_side`.

Note that `DOMAIN_NO_FAILURE_MODES_FLOOR = 0.10 < θ = 0.15`. A method that
declares no failure modes therefore has its `s_DS` floored at `0.10`, which is
*still below the gate*: the floor alone never opens the gate. The LLM judge
(or an `in_bounds`-verdict path that lifts `base` above `θ`) must do that.

### 6.3 When inputs disagree

When a deterministic signal and the LLM judge disagree, the **deterministic
signal wins**, and always in the direction of caution:

- `v = out_of_bounds` forces `s_DS = 0` regardless of `j_DS` — even
  `j_DS = 1.0` is overridden.
- `FM(c) = ∅ ∧ D(c) = 0` caps `s_S` at `0.35` regardless of `j_S` — even
  `j_S = 1.0` is overridden.
- The deterministic severity `floor` overrides a *low* `j_S`: `s_S⁽⁰⁾` is the
  `max` of the two, so a method with many failure modes keeps its floor even
  if the judge scores it low.
- `κ` (track-record ceiling) and the `edge_case` ceiling override a *high*
  `j_S` / `j_DS` by `min`.

So the LLM judge can only move a sub-score *within* the window the
deterministic rules leave open. Test:
`test_deterministic_verdicts_override_llm`.

### 6.4 A non-gate sub-score is exactly 0

If any of `s_P, s_S, s_AMF, s_C` is exactly 0 and the gate is open
(`s_DS ≥ θ`), then `wgeomean(...) = 0` and so `MQS(c) = 0`. This is the
weakest-link property of the weighted geometric mean (§5.1) and it is
intentional: a conclusion that produces nothing checkable (`s_P = 0`), or
whose method cannot answer the question at all (`s_AMF = 0`), has a failing
methodology quality even if every other axis is perfect. The composite is 0,
the tier is `failing`. Test: `test_zero_subscore_zeroes_composite`.

### 6.5 Out-of-range or NaN inputs

Every sub-score input is passed through `clamp` before any arithmetic:
`clamp` confines values to `[0,1]` and maps `NaN` to `0`. A `NaN` sub-score
therefore behaves as `0` — for a non-gate sub-score that zeroes the composite
(§6.4); for `s_DS` that closes the gate. The composite is always a real number
in `[0,1]`. Test: `test_composite_is_total_and_bounded`.

## 7. Composite tiers

The composite is a continuous score in `[0,1]`, but the firm reasons about it
in tiers. The canonical tiers, defined by `COMPOSITE_TIERS` in
`noosphere/noosphere/evaluation/mqs.py` (ordered high → low, each an inclusive
lower bound):

| Tier          | Composite ≥ |
| ------------- | ----------- |
| `strong`      | 0.66        |
| `adequate`    | 0.40        |
| `provisional` | 0.15        |
| `failing`     | 0.00        |

`tier_rank` gives each tier an ordinal (`failing` = 0 … `strong` = 3). The
Aim-Method Fit backfill (`noosphere/scripts/backfill_aim_method_fit.sh`)
re-scores every conclusion under the prompt-31 rubric; any conclusion whose
composite **drops a tier** — `tier_rank(new) < tier_rank(old)` — is routed to
the founder's queue rather than silently downgraded.

## 8. Constants registry

Every named constant in `noosphere/noosphere/evaluation/mqs.py` that this
specification depends on appears in the table below, and `MQS_CONSTANTS` in
that module contains exactly these keys with exactly these values.
`scripts/check_mqs_doc_consistency.py` fails CI on any divergence in either
direction — a constant in code but not here, here but not in code, or a value
mismatch.

| Constant | Value | Role |
| -------- | ----- | ---- |
| `SPEC_VERSION` | `1.0.0` | version of this specification (§9). |
| `MQS_SCHEMA` | `theseus.mqs.v1` | schema string stamped on every MQS row and evidence blob. |
| `PROMPT_VERSION` | `mqs-prompt-v2.0` | LLM-judge prompt version; independent of `SPEC_VERSION`. |
| `DS_GATE_THRESHOLD` | `0.15` | gate threshold `θ`: `s_DS < θ` ⟹ composite 0 (§5). |
| `COMPOSITE_OPERATOR` | `weighted_geometric_mean` | the operator combining the four non-gate sub-scores (§5). |
| `SEVERITY_FAILURE_MODE_FLOOR_STEP` | `0.15` | per-failure-mode step in the severity deterministic floor (§3.2). |
| `SEVERITY_DISSENT_FLOOR_STEP` | `0.10` | per-dissent-claim step in the severity deterministic floor (§3.2). |
| `SEVERITY_NO_FAILURE_MODES_CAP` | `0.35` | cap on `s_S` when a method declares no failure modes and carries no dissent (§3.2). |
| `COMPRESSIBILITY_PENALTY_STEP` | `0.25` | per-effective-assumption penalty step in `s_C` (§3.4). |
| `DOMAIN_NO_FAILURE_MODES_FLOOR` | `0.10` | floor on `s_DS` when a method declares no failure modes (§3.5). |
| `DOMAIN_BACKFILL_DEFAULT` | `0.5` | `s_DS` base when no LLM judge is available (§3.5). |
| `EDGE_CASE_DOMAIN_CEILING` | `0.4` | cap on `s_DS` under an `edge_case` domain-bound verdict (§3.5). |
| `EVIDENCE_STR_CAP` | `600` | per-string character cap on evidence blobs (§2). |

The four `SUBSCORE_WEIGHTS` (§5.2) are checked separately by the same script;
the `COMPOSITE_TIERS` lower bounds (§7) likewise.

## 9. Persistence

MQS rows are written to the `MethodologyQualityScore` table, which is 1:1 with
`Conclusion`. The score is re-runnable: re-scoring overwrites the prior row.
Sub-score `evidence` blobs are stored as Prisma `Json` so a reviewer can
contest them.

The recorded fields:

- `progressivity`, `severity`, `aimMethodFit`, `compressibility`,
  `domainSensitivity`: float in `[0,1]`.
- `composite`: float in `[0,1]`.
- `evidence`: JSON object with one key per sub-score plus `schema`,
  `spec_version`, `composite_formula`, `composite_operator`,
  `ds_gate_threshold`, and `subscore_weights`.
- `modelName`, `promptVersion`: text — what produced the score.
- `scoredAt`: timestamp.

## 10. Public display rule

The public article surface shows the composite MQS only when:

1. The conclusion is published (a row in `PublishedConclusion` exists), AND
2. The MQS row's `scoredAt` is greater than or equal to the conclusion's last
   edit (`Conclusion.updatedAt` if present, else `createdAt`).

If either condition fails, no pill is rendered. A stale MQS is never shown
publicly.

## 11. Versioning and changelog

This file carries two independent version strings:

- **`SPEC_VERSION`** — the version of *this specification*. The first formal
  version is `1.0.0`. Any material change to a formula, a constant, a boundary
  rule, or the composite operator bumps `SPEC_VERSION` and **adds a row to the
  changelog below**.
- **`PROMPT_VERSION`** — the LLM-judge prompt version, of the form
  `mqs-prompt-vMAJOR.MINOR`. Prompt revisions that materially change the judge
  bump its MAJOR. This is independent of `SPEC_VERSION`: the judge prompt can
  change without the formal formula changing, and vice versa.

Re-running over the same conclusion with a newer prompt overwrites the prior
MQS row in place; the older score is recoverable from audit history and from
any out-of-band export.

### Changelog

| `SPEC_VERSION` | Date | Change |
| -------------- | ---- | ------ |
| `1.0.0` | 2026-05-14 | First formal specification. The composite changed from the Round 17 prose draft's soft multiplicative gate, `domain_sensitivity · mean(progressivity, severity, aim_method_fit, compressibility)`, to a hard piecewise gate at `θ = DS_GATE_THRESHOLD = 0.15` followed by the weighted geometric mean of the four non-gate sub-scores. **Both the code (`composite_score` in `noosphere/noosphere/evaluation/mqs.py`) and this spec were changed together** — they had previously agreed on the soft formula. Rationale in §5.1: the firm's position on out-of-domain methods is a verdict, not a discount, and the weighted geometric mean is the operator that refuses redemption while still using all four sub-scores. Named every previously-magic constant and added the §8 constants registry. |
