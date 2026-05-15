# Method Retirement Criteria

Status: normative · Owner: Methodology Review · Schema: `theseus.method_retirement.v1`

Round 17 gave the firm two ways to *notice* a method has gone bad — the
drift detector and the per-method failure-mode catalogs — but no clean
way to *act* on that knowledge. Without a workflow, a method that has
earned retirement just lingers in the registry as a zombie: still
callable, still feeding conclusions, with nothing recording that the
firm stopped trusting it.

This document defines **when** a method has earned a retirement review.
The workflow that acts on it — the `{ACTIVE, UNDER_REVIEW, DEPRECATED,
RETIRED}` state machine, the founder review memo, and conclusion
migration — lives in `noosphere/noosphere/methods/retirement.py` and is
driven by `noosphere methods retirement ...`.

A retirement review is **not** a retirement. It is the firm committing
to *look*. The review produces a permanent memo at
`docs/methods/retirement/<method>.md`; the founder then accepts (the
method is deprecated and its conclusions migrate) or rejects (the method
returns to ACTIVE and the memo stays as the record that the question was
asked and answered).

## The four criteria

A method **qualifies for retirement review** if **any one** of the
following holds. Each maps to a `RetirementCriterion` enum value and is
checked by `qualifies_for_review()`.

### 1. Sustained drift alert (> 60 days) — `sustained_drift`

The method's drift alert (`noosphere/decay/method_drift_policies.py`) has
been continuously non-OK — `WARN` or `ESCALATE` — for more than **60
days**.

A single warn window is not retirement-grade. The drift policy already
has hysteresis: it will not clear an alert until two consecutive clean
windows. The 60-day threshold is the much longer fuse — it means the
method has been *measurably* miscalibrated against its own historical
baseline for two full months and has not recovered. That is no longer a
blip; it is the method's new normal.

The signal is `RetirementSignals.drift_alert_active_since` — the
timestamp the alert first went non-OK and has stayed non-OK since.

### 2. Zero ablation contribution — `zero_ablation_contribution`

An ablation study of the method's pipeline returns a **`REMOVE`**
recommendation: removing the method's step produces no measurable loss
(and possibly a gain) against a baseline variant, at adequate
statistical power.

**Only a `REMOVE` verdict counts.** This is the criterion most likely to
be misapplied, so the rule is strict. An ablation that is *inconclusive*
is **not** grounds for retirement. The QH-v1 Householder Reflection
Ablation (`docs/research/Householder_Ablation.pdf`, 2026-05-14) is the
worked example: every variant constant-predicted the same label because
the frozen sparsity threshold was saturated, so McNemar returned `b + c
= 0` and `p = 1.0` for every variant. That is the signature of a test
with **zero power**, not of a confirmed null — and the study's own
decision rule correctly returned `KEEP-WITH-FURTHER-WORK`, not `REMOVE`.
A zero-power ablation tells you nothing about contribution; it does not
qualify a method for review.

The signal is `RetirementSignals.ablation_recommendation`, one of
`KEEP` / `REMOVE` / `KEEP-WITH-FURTHER-WORK`; the criterion fires only on
`REMOVE`.

### 3. Dormant (zero invocations in 90 days) — `dormant`

The method has been invoked **zero times in the last 90 days**.

Dormancy is the weakest of the four signals and the one most worth
stating carefully: a dormant method is not necessarily a bad method — it
may simply be specialised for material the firm has not seen lately. So
dormancy does not retire a method; it *triggers a review that asks
whether the method is still load-bearing*. If the founder concludes the
method is still the right tool for a domain that will recur, the review
is rejected and the method stays ACTIVE. If the capability has been
absorbed by another method, the review proceeds.

The signal is `RetirementSignals.invocations_last_90d`. `0` triggers;
`None` (unknown) does not — a missing count is never treated as zero.

### 4. All conclusions revised away — `all_conclusions_revised`

**Every** conclusion the method ever produced has since been revised
away — retracted, superseded, or otherwise no longer standing.

This is the strongest signal. If a method's entire output has been
walked back, the method is not merely drifting — its track record is, in
full, a record of conclusions the firm no longer holds. There is little
left to review except *which* replacement should carry the
responsibility forward.

The signals are `RetirementSignals.conclusions_total` and
`conclusions_revised_away`; the criterion fires only when the method
produced at least one conclusion and *all* of them have been revised
away.

## What qualifying does — and does not — do

Qualifying for review **does not** change a method's state. It is an
advisory verdict. Acting on it means a human runs:

```
noosphere methods retirement open <method> --replacement <m> --reason "..."
```

which moves the method `ACTIVE → UNDER_REVIEW` and scaffolds the founder
review memo. From there:

- **Founder accepts** → `UNDER_REVIEW → DEPRECATED`. Every conclusion the
  method produced gets a sunset banner; reanalysis under the replacement
  is scheduled. The method still runs, but loudly (`DeprecatedMethodWarning`).
- **Founder rejects** → `UNDER_REVIEW → ACTIVE`. The memo stays — the
  permanent record that the review happened and what it concluded.
- After the sunset timeline elapses → `DEPRECATED → RETIRED`. The
  registry now refuses calls with a typed `RetiredMethodError` that
  names the replacement.

## Invariants

These are enforced in code and pinned by `tests/test_method_retirement.py`:

- **The `UNDER_REVIEW` step is mandatory.** A method cannot move
  `ACTIVE → DEPRECATED` or `ACTIVE → RETIRED` directly. Every retirement
  passes through a founder review that produces a permanent memo.
- **`RETIRED` is terminal.** A retired method is never un-retired.
  Reviving the *idea* means registering a new method; the retired one
  stays as history.
- **Retired methods stay importable.** Retirement refuses *calls* — it
  does not delete source. `REGISTRY.get(name, include_retired=True)`
  still resolves a retired method for historical re-analysis.
- **Public-side, retired methods do not vanish.** They render on the
  public methodology surface with tombstone styling. What the firm has
  stopped trusting is part of the firm's record, and readers can see it.
