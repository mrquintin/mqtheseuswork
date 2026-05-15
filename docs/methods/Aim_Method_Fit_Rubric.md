# Aim-Method Fit — Rubric v1.0.0

Status: source of truth for the **Aim-Method Fit** sub-score of the MQS — the
third of the five working criteria in `THE_META_METHOD.md` §2.3. This file is
the prose companion to `noosphere/noosphere/inquiry/aim_method_fit.py` and
`noosphere/noosphere/inquiry/question_typology.py`; the worked examples below
are mirrored in code as `WORKED_EXAMPLES` and exercised deterministically by
`noosphere/tests/test_aim_method_fit.py`.

## What this criterion asks

> Does this method actually answer **THIS** question?

A valuation method gives valuations. Pointed at a product-strategy question, a
valuation method has poor fit — not because it is unreliable, and not because
it is outside its domain, but because the *shape of its output* is not the
shape the question demands.

Aim-Method Fit was, until Round 18, the weakest of the five criteria in the
firm's implementation: the MQS rubric (Round 17 prompt 01) scored it as a soft
LLM judgment with no precise rubric. This document and its companion modules
replace that with a deterministic five-level rubric.

### What "actually answer" means — and what keeps it distinct

"Actually answer" is operationalized through **answer shape**: every question
demands an answer of a particular *kind* (a forecast, an evaluation, a
category, a decision rule, …), and every method produces outputs of a
particular kind. Fit is the relationship between the two.

This is deliberately **not** Domain Sensitivity (§2.5):

| Criterion          | Asks                                              | Failure looks like                                       |
| ------------------ | ------------------------------------------------- | -------------------------------------------------------- |
| Aim-Method Fit     | Is the method's *output shape* the answer shape?  | A valuation answering "what should we build?"            |
| Domain Sensitivity | Is the conclusion inside the method's *domain*?   | A valuation of a company in a sector the method can't price |

A method can have perfect Domain Sensitivity (squarely inside its domain) and
still poor Aim-Method Fit (its in-domain output is the wrong *kind* of thing
for the question). The two criteria are scored from different inputs and
compose independently in the MQS — Domain Sensitivity is the multiplicative
gate; Aim-Method Fit is one of the four averaged sub-scores.

## The question typology

The taxonomy lives in code — `noosphere.inquiry.question_typology.QuestionType`
— not just in this prose. It is the closed set of question *shapes* the firm
encounters. It is also **shared with the public-query classifier** from
prompt 29 (`noosphere.inference.query_classifier`) via
`question_type_for_query_class()`, so the firm has one notion of question
shape across both the `/ask` retrieval surface and methodology scoring.

| Type             | Asks                                  | Answer form                          |
| ---------------- | ------------------------------------- | ------------------------------------ |
| `descriptive`    | What is the case?                     | A characterization of what is        |
| `predictive`     | What will happen?                     | A forecast with a horizon            |
| `normative`      | What is good / sound / valuable?      | An evaluation against a standard     |
| `strategic`      | What should *we* do?                  | A decision rule or course of action  |
| `methodological` | How is this reasoned / derived?       | A procedure or derivation trail      |
| `classificatory` | What kind of thing is this?           | A label or category                  |

The subtle distinction is **normative vs strategic**. A normative question
asks for an actor-independent value judgment ("is this asset sound?"); a
strategic question asks for an actor-relative action given goals and
constraints ("should *we* hold this asset?"). A valuation method produces
normative and predictive outputs — never strategic ones — which is exactly
why it misfits a product-strategy question.

### Relations over the typology

Two relations, both defined in code, drive the rubric below level 3:

- **`DECOMPOSES_INTO`** — the sub-questions whose answers are *directly
  reusable* as a constituent of answering the parent. Kept deliberately tight:
  only `descriptive` and `classificatory` answers are broad enough to be
  genuine constituents of other questions. A method that serves one of these
  answers *part* of the question (level 2).
- **`ADJACENT`** — "same family, different question." A method whose outputs
  land in a type adjacent to the question's type answers something *related*
  but not the thing asked (level 1).

### Each method declares the question types it serves

Every method declares which question types its outputs can answer. A method
declares this either directly on its `MethodologyProfile`
(`question_types_served`) or through the registry `METHOD_QUESTION_TYPES`,
keyed on the method's `pattern_type`. An **unregistered** method — one that
declares nothing — is treated as "fit cannot be verified" (level 2), never as
"fits nothing" (level 0): §2.3 forbids retiring a method on this rubric alone.

## The five-level rubric

The level maps to the MQS sub-score as `level / 4`, so the sub-score is one of
`{0.0, 0.25, 0.5, 0.75, 1.0}`.

| Level | Score | Meaning                                                                       |
| ----- | ----- | ----------------------------------------------------------------------------- |
| 0     | 0.00  | The method's outputs cannot answer the question type.                         |
| 1     | 0.25  | The outputs answer a related but different question.                          |
| 2     | 0.50  | The outputs answer part of the question.                                      |
| 3     | 0.75  | The outputs answer the question, with caveats the method cannot articulate.   |
| 4     | 1.00  | The outputs answer the question with explicit caveats within its competence.  |

How the level is computed, from the three inputs §2.3 specifies — (a) the
inferred question type, (b) the question types the producing method serves,
(c) the worked-example match:

- **question type ∈ served types** → the method answers the question.
  Level **4** if a serving method has an *articulated boundary* (it declares
  failure modes, so it can say when it should not be trusted); level **3**
  otherwise.
- **served types intersect `DECOMPOSES_INTO[question_type]`** → the method
  answers a reusable *part* → level **2**.
- **served types intersect `ADJACENT[question_type]`** → the method answers a
  *related* question → level **1**.
- **otherwise** → level **0**.
- **every producing method unregistered** → level **2** ("cannot verify fit").

Input (c), the worked-example match, is a *cross-check*, not an override: when
a `(question_type, pattern_type)` pair corresponds to a documented worked
example below, the scorer records which one and whether the structural level
*agrees* with the labelled level. A disagreement is a rubric bug; the test
suite asserts there are none.

### Level 0 — cannot answer the question type

The method's outputs are disjoint from the question type, its decomposition,
and its neighbours.

- **WE-0a** — *"How did the firm derive this conclusion?"* (topic: methodology)
  → `methodological`. Producing method: **valuation** (serves `normative`,
  `predictive`). A valuation's outputs — a worth figure, a price expectation —
  are not a derivation trail and are not adjacent to one. **Level 0.**
- **WE-0b** — *"What is the firm's current headcount?"* → `descriptive`.
  Producing method: **product_strategy** (serves `strategic`). A method that
  produces recommended actions cannot answer a plain descriptive question.
  **Level 0.**

### Level 1 — answers a related but different question

The method's served types are *adjacent* to the question type but neither
contain it nor a reusable part of it.

- **WE-1a** — *"What product should the company build next?"* (topic: product
  strategy) → `strategic`. Producing method: **valuation** (serves `normative`,
  `predictive`). This is the firm's anchor misfit: normative and predictive
  are adjacent to strategic, so a valuation answers a *related* question
  (what is this worth, where is the price going) — but not "what should we
  build." **Level 1.**
- **WE-1b** — *"Will this product line grow next year?"* (topic: growth
  forecast) → `predictive`. Producing method: **product_strategy** (serves
  `strategic`). Strategic is adjacent to predictive; a product-strategy method
  consumes forecasts but does not itself produce one. **Level 1.**

### Level 2 — answers part of the question

The method serves a type in `DECOMPOSES_INTO[question_type]` — a directly
reusable constituent of the question — but not the whole.

- **WE-2a** — *"Will the new market clear by 2026?"* (topic: forecasting) →
  `predictive`. Producing method: **first_principles_decomposition** (serves
  `descriptive`, `methodological`). A predictive question reuses a description
  of current state; the method serves that descriptive part, not the forecast
  itself. **Level 2.**
- **WE-2b** — *"Is this asset a sound long-term holding?"* → `normative`.
  Producing method: **representational_geometry** (serves `classificatory`,
  `descriptive`). A normative judgment reuses what-is and what-kind; the method
  serves those parts, not the value judgment. **Level 2.**
- An **unregistered** producing method also lands here: fit cannot be
  verified, so the conclusion sits at level 2 until the method declares its
  served types.

### Level 3 — answers the question, caveats it cannot articulate

The question type is in the method's served types, but the method declares no
failure modes — so it answers the question while leaving its own caveats
implicit.

- **WE-3a** — *"Will inflation exceed 3% next year?"* (topic: forecasting) →
  `predictive`. Producing method: **bayesian_update** (serves `predictive`,
  `descriptive`) **with no declared failure modes**. It answers the question,
  but cannot say where it would break. **Level 3.**
- **WE-3b** — *"What is the composition of the firm's asset base?"* →
  `descriptive`. Producing method: **first_principles_decomposition** (serves
  `descriptive`, `methodological`) with no declared failure modes. **Level 3.**

### Level 4 — answers the question with explicit, articulated caveats

The question type is in the method's served types **and** a serving method has
an articulated boundary — it declares failure modes, so it can state when it
should not be trusted on this question.

- **WE-4a** — *"Will the company's monthly active users stay above 10k through
  2026?"* (topic: forecasting) → `predictive`. Producing method:
  **empirical_calibration** (serves `predictive`, `descriptive`) **with
  declared failure modes**. It answers the forecast and names its own failure
  conditions. **Level 4.**
- **WE-4b** — *"Is this method's reasoning internally sound?"* (topic:
  reasoning quality) → `normative`. Producing method: **adversarial_audit**
  (serves `methodological`, `normative`) with declared failure modes. **Level 4.**
- **WE-4c** — *"What kind of reasoning pattern does this method use?"* (topic:
  method classification) → `classificatory`. Producing method:
  **representational_geometry** (serves `classificatory`, `descriptive`) with
  declared failure modes. **Level 4.**

## Mismatch detection and the gating composite

The MQS scorer (`noosphere.evaluation.mqs.score_aim_method_fit`) computes the
sub-score deterministically from the rubric above — no LLM judge is consulted.
A mismatch (the method's outputs are not the answer shape the question
demands) surfaces as a **low Aim-Method Fit sub-score** (level 0 → 0.0,
level 1 → 0.25), which feeds into the gating composite:

```
composite = domain_sensitivity * mean(progressivity, severity, aim_method_fit, compressibility)
```

A level-0 Aim-Method Fit drags the averaged term down by a full quarter; it
does **not** zero the composite (only Domain Sensitivity is the multiplicative
gate). This is intentional: a misfit conclusion is weak, but the method that
produced it may still be the best available method for the questions it *does*
fit. The rubric scores the *conclusion*, not the *method*.

### Backfill and the founder's queue

`noosphere/scripts/backfill_aim_method_fit.sh` re-scores every existing
conclusion's Aim-Method Fit under this rubric. Re-scoring shifts the composite;
the composite is bucketed into tiers (`strong` ≥ 0.66, `adequate` ≥ 0.40,
`provisional` ≥ 0.15, `failing` ≥ 0.0). Any conclusion that **drops a tier** on
re-score is routed to the founder's queue for review — the rubric does not
silently downgrade landed conclusions.

## Versioning

Rubric revisions bump the version at the top of this file. A revision that
changes a level boundary, the typology, or a relation is a MAJOR bump and
requires re-running the backfill; adding a worked example without changing the
structural logic is a MINOR bump.
