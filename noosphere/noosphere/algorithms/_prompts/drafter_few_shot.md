# Few-shot examples for the Logical Algorithm drafter

These examples show what a well-formed draft looks like, what the
firm's name / description style is, and — critically — what a refusal
looks like when the cluster cannot honor the no-fabrication rules.

---

## Example 1 — Arms-Race Escalation Predictor (DRAFTED)

### Cluster

- `principle_security_dilemma`: "States in mutual threat perception
  engage in security-dilemma escalation absent credible commitment
  devices."
- `principle_domestic_lockin`: "Domestic political incentives reinforce
  external escalation once initiated; reversal requires elite cost."
- `principle_second_derivative`: "Arms races are predicted by the
  second derivative of military spending, not the first."

### Draft

```
{
  "outcome": "DRAFTED",
  "name": "Arms-Race Escalation Predictor",
  "description": "Detects bilateral arms-race onset between two states from spending acceleration, rhetoric, and mediator presence, and projects per-side spending growth over a fixed horizon.",
  "inputs": [
    {
      "name": "side_a_spending_accel",
      "type": "RATIO",
      "description": "State A's YoY change in military-spending growth rate (second derivative).",
      "observability_source": "currents.macro.defense_spending.side_a"
    },
    {
      "name": "side_b_spending_accel",
      "type": "RATIO",
      "description": "State B's YoY change in military-spending growth rate (second derivative).",
      "observability_source": "currents.macro.defense_spending.side_b"
    },
    {
      "name": "rhetoric_escalation_index",
      "type": "INDEX",
      "description": "Composite rhetoric escalation index over public statements.",
      "observability_source": "currents.x.rhetoric_index"
    },
    {
      "name": "mediator_present",
      "type": "BOOL",
      "description": "Whether a credible third-party mediator with leverage is engaged.",
      "observability_source": "manual.operator.entered"
    }
  ],
  "output": {
    "name": "arms_race_projection",
    "type": "STRUCTURED",
    "description": "Per-side projected spending increase and confidence band over a fixed horizon.",
    "fields": [
      {"name": "side_a_spending_increase_pct", "type": "RATIO"},
      {"name": "side_b_spending_increase_pct", "type": "RATIO"},
      {"name": "horizon_months", "type": "NUMBER"},
      {"name": "confidence_low", "type": "RATIO"},
      {"name": "confidence_high", "type": "RATIO"}
    ]
  },
  "reasoning_chain": [
    {
      "step_kind": "DETECT",
      "predicate": "input.side_a_spending_accel > 0 and input.side_b_spending_accel > 0 and input.rhetoric_escalation_index > 0.6 and input.mediator_present == False",
      "derived_fact": "Both states are accelerating spending under rising rhetoric with no mediator."
    },
    {
      "step_kind": "APPLY_PRINCIPLE",
      "principle_id": "principle_security_dilemma",
      "derived_fact": "Security-dilemma feedback projects continued mutual growth absent a commitment device."
    },
    {
      "step_kind": "APPLY_PRINCIPLE",
      "principle_id": "principle_domestic_lockin",
      "derived_fact": "Domestic lock-in reduces probability of unilateral reversal absent elite cost."
    },
    {
      "step_kind": "APPLY_PRINCIPLE",
      "principle_id": "principle_second_derivative",
      "derived_fact": "Acceleration — not level — is the leading signal; projection should compound on the observed second derivative."
    },
    {
      "step_kind": "SYNTHESIZE",
      "derived_fact": "Compound projected per-side increases over horizon, widened by rhetoric severity."
    },
    {
      "step_kind": "OUTPUT",
      "derived_fact": "Emit per-side projection with horizon and confidence band."
    }
  ],
  "trigger_predicate": "input.side_a_spending_accel > 0 and input.side_b_spending_accel > 0 and input.rhetoric_escalation_index > 0.6 and input.mediator_present == False",
  "confidence_note": "The rhetoric index is the weakest leg — provider drift in source mix can move the threshold; recalibrate quarterly."
}
```

---

## Example 2 — Hyperstition Onset Detector (DRAFTED)

### Cluster

- `principle_narrative_consensus`: "A narrative crosses into
  hyperstition when elite consensus and crowd consensus both pass
  threshold while disagreement collapses."
- `principle_velocity_over_level`: "Narrative virality is predicted by
  the rate of new adopters per day, not the cumulative adopter count."

### Draft

```
{
  "outcome": "DRAFTED",
  "name": "Hyperstition Onset Detector",
  "description": "Detects when a narrative crosses from contested to consensus-driven self-fulfilling by combining elite alignment, crowd alignment, disagreement collapse, and adoption velocity.",
  "inputs": [
    {
      "name": "elite_consensus_score",
      "type": "INDEX",
      "description": "Share of tracked elite voices endorsing the narrative.",
      "observability_source": "currents.x.elite_consensus"
    },
    {
      "name": "crowd_consensus_score",
      "type": "INDEX",
      "description": "Share of tracked crowd discourse endorsing the narrative.",
      "observability_source": "currents.x.crowd_consensus"
    },
    {
      "name": "disagreement_ratio",
      "type": "RATIO",
      "description": "Ratio of disagreeing posts to total posts in the window.",
      "observability_source": "currents.x.disagreement_ratio"
    },
    {
      "name": "adopter_velocity",
      "type": "RATIO",
      "description": "New adopters per day, normalised to the prior week.",
      "observability_source": "currents.x.adopter_velocity"
    }
  ],
  "output": {
    "name": "hyperstition_onset",
    "type": "SCORE",
    "description": "Composite onset score; values near 1 indicate hyperstition.",
    "range": [0.0, 1.0]
  },
  "reasoning_chain": [
    {
      "step_kind": "DETECT",
      "predicate": "input.elite_consensus_score > 0.7 and input.crowd_consensus_score > 0.6 and input.disagreement_ratio < 0.2",
      "derived_fact": "Elite and crowd alignment cross threshold while disagreement collapses."
    },
    {
      "step_kind": "APPLY_PRINCIPLE",
      "principle_id": "principle_narrative_consensus",
      "derived_fact": "The dual-consensus + collapsed-disagreement signature is the necessary precondition for hyperstition."
    },
    {
      "step_kind": "APPLY_PRINCIPLE",
      "principle_id": "principle_velocity_over_level",
      "derived_fact": "Adopter velocity weights the onset score more heavily than cumulative adoption."
    },
    {
      "step_kind": "SYNTHESIZE",
      "derived_fact": "Score is a velocity-weighted composite of consensus and disagreement-collapse."
    },
    {
      "step_kind": "OUTPUT",
      "derived_fact": "Emit hyperstition onset score in [0, 1]."
    }
  ],
  "trigger_predicate": "input.elite_consensus_score > 0.7 and input.crowd_consensus_score > 0.6 and input.disagreement_ratio < 0.2",
  "confidence_note": "The crowd-consensus score is noisy on Currents pulls under 24h — prefer windows of ≥48h."
}
```

---

## Example 3 — Founder-Quality Discriminator (DRAFTED)

### Cluster

- `principle_sustained_obsession`: "Founders with ≥3 years of
  sustained obsession on a problem outperform founders chasing
  themes."
- `principle_track_record_prior`: "Prior exits update the prior on
  competence multiplicatively, not additively."

### Draft

```
{
  "outcome": "DRAFTED",
  "name": "Founder-Quality Discriminator",
  "description": "Scores a founder on sustained obsession, domain mastery, and prior outcomes to inform investment recommendations.",
  "inputs": [
    {
      "name": "years_on_problem",
      "type": "NUMBER",
      "description": "Years the founder has been working on the problem.",
      "observability_source": "manual.operator.entered",
      "units": "years"
    },
    {
      "name": "domain_mastery_score",
      "type": "INDEX",
      "description": "Heuristic 0..1 score for domain-mastery signals.",
      "observability_source": "manual.operator.entered"
    },
    {
      "name": "prior_exits",
      "type": "NUMBER",
      "description": "Number of prior companies the founder has exited.",
      "observability_source": "manual.operator.entered"
    }
  ],
  "output": {
    "name": "founder_quality_score",
    "type": "SCORE",
    "description": "Composite founder-quality score in [0, 1].",
    "range": [0.0, 1.0]
  },
  "reasoning_chain": [
    {
      "step_kind": "DETECT",
      "predicate": "input.years_on_problem >= 3",
      "derived_fact": "Founder has at least three years on the problem."
    },
    {
      "step_kind": "APPLY_PRINCIPLE",
      "principle_id": "principle_sustained_obsession",
      "derived_fact": "Sustained-obsession principle elevates the prior on competence."
    },
    {
      "step_kind": "APPLY_PRINCIPLE",
      "principle_id": "principle_track_record_prior",
      "derived_fact": "Prior exits update the prior multiplicatively."
    },
    {
      "step_kind": "SYNTHESIZE",
      "derived_fact": "Combine signals into a composite founder-quality score."
    },
    {
      "step_kind": "OUTPUT",
      "derived_fact": "Emit composite score in [0, 1] with an implied investment recommendation."
    }
  ],
  "trigger_predicate": "input.years_on_problem >= 3",
  "confidence_note": "Prior exits are coarse — a 2x exit and a 200x exit collapse to the same integer; this is the leg most worth manual review."
}
```

---

## Example 4 — Normative-only cluster (UNFORMALISABLE)

### Cluster

- `principle_dignity`: "Every person is owed dignity."
- `principle_truthfulness`: "Honesty is a duty independent of
  consequence."
- `principle_humility`: "Strong opinions held loosely is the only
  honest epistemic posture."

### Draft

```
{
  "outcome": "UNFORMALISABLE",
  "reason": "Normative-only cluster: every principle is a value judgment with no observable input. No real provider can supply 'dignity', 'duty-honesty', or 'epistemic-humility' as a measurable quantity, and inventing a proxy would smuggle interpretation into the algorithm. Founder should review whether this cluster belongs in the algorithm layer at all."
}
```

This refusal is the correct response.  The drafter is forbidden from
inventing inputs to make a normative principle look operational.
