# The Meta-Method: Working Criteria For Inquiry

Status: conceptual framing for the current Theseus system. This document is not
a claim that every criterion below is fully automated in production.

## Why A Meta-Method Matters

Theseus distinguishes three levels of work:

1. **Object-level claims**: what the firm believes about a company, institution,
   market, or event.
2. **Methods**: the reasoning procedures used to arrive at those claims.
3. **Meta-methods**: criteria for deciding whether a method is reliable in the
   domain where it is being used.

The Codex and Noosphere now support parts of this distinction directly:
uploaded sources are processed into claims, conclusions, methodology profiles,
embeddings, source-structure records, Currents opinions, and reviewed public
articles. The current system is still incomplete, but its direction is clear:
preserve enough of the reasoning record that a later reviewer can inspect both
the conclusion and the method that produced it.

## Five Working Criteria

These criteria are practical evaluation handles. They should be used as prompts
for review, not as proof that a conclusion is true.

### 1. Progressivity

A method is more useful when it generates claims that could have been wrong in
observable ways. A method that only explains what is already known may be
descriptively interesting, but it is weak as a guide to future action.

Operational question: did the analysis produce a prediction, implication, or
decision rule that can later be checked?

### 2. Severity

A test is severe when it would probably have exposed the claim's weakness if the
claim were false. Confirmation is cheap if the procedure would have passed many
different claims.

Operational question: what evidence, counterexample, or failure mode would have
changed the conclusion?

### 3. Aim-Method Fit

A method should fit the aim it serves. A strong valuation screen is not
automatically a strong product thesis. A useful education argument is not
automatically a useful capital-allocation rule.

Operational question: is the method actually capable of answering the question
being asked?

### 4. Compressibility

An explanation that requires many special exceptions is less likely to transfer
well. This does not mean simple claims are always true; it means additional
assumptions should be visible and priced as risk.

Operational question: which assumptions are doing the real work, and how many
would need to hold for the conclusion to survive?

### 5. Domain Sensitivity

No reasoning method is reliable everywhere. Methods have domains, failure modes,
and boundary conditions.

Operational question: where should this method stop being trusted?

## How This Shows Up In The Product

The current product implements the meta-method imperfectly but concretely:

- **Methodology profiles** describe reasoning moves, assumptions, possible
  transfer targets, and failure modes.
- **Source exploration** keeps transcripts and documents inspectable instead of
  reducing them to a single summary.
- **Embeddings and Explorer views** help identify related conclusions and
  clusters.
- **Adversarial review** records structured objections to conclusions.
- **Forecast and calibration surfaces** give some claims later outcome checks.
- **Currents and public articles** publish firm perspectives only when source
  grounding and citation validation are available.

These mechanisms do not eliminate judgment. They make judgment easier to audit.

## Limits

The meta-method is not a universal algorithm for truth. It is a set of criteria
for making inquiry more inspectable and less dependent on unrecorded intuition.
It can itself fail: the criteria may be misapplied, the source record may be
thin, the generator may overstate confidence, or the domain may not support the
kind of evidence being requested.

That is why the current product emphasizes revision. A conclusion should carry
its source trail, method, objection, confidence, and revision condition so the
firm can later identify whether the claim failed, the method failed, or the
evidence changed.

## Current Relationship To Theseus

The meta-method is best understood as the evaluation layer for the rest of the
repository:

- Noosphere extracts and processes the reasoning record.
- Dialectic captures live conversational material.
- Theseus Codex exposes the private workspace and the public publication
  surface.
- Currents applies the recorded firm memory to live events.

The goal is not to turn every argument into a formula. The goal is to keep
enough structure that serious review remains possible after the conversation,
publication, or market event has passed.
