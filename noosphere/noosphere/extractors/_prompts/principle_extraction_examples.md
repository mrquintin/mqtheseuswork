# Principle extraction — worked examples

The examples below are appended to the system prompt so the model
sees concrete shapes of both successful extractions and refusals.

## Positive examples (first-person source → extracted principle)

### Example 1 — RULE (quantifiable trigger)

**Source span (verbatim)**: "I think the right move when a portfolio
company is below product-market-fit but burning under 12 months of
runway is to cut not raise."

**Extraction**:
```json
{
  "text": "When a portfolio company is below product-market-fit and has under 12 months of cash, cut spend before raising — additional capital amplifies an unvalidated GTM rather than buying time to find one.",
  "source_span": "I think the right move when a portfolio company is below product-market-fit but burning under 12 months of runway is to cut not raise.",
  "principle_kind": "RULE",
  "domain_of_applicability": "Early-stage portfolio companies pre-PMF with measurable runway; does not apply to PMF-validated companies or to deep-tech with capex-driven J-curves.",
  "quantifiable_proxies": ["months_of_runway", "Sean Ellis PMF score", "burn multiple"],
  "decision_examples": [
    "Q3 board: company at 9 months runway, retention < 30%; recommend RIF before bridge round.",
    "Reject founder ask to top-up at flat valuation when burn multiple > 3 and ICP still drifting."
  ]
}
```

### Example 2 — CRITERION (admissibility test)

**Source span**: "I just feel that if a thesis isn't falsifiable
inside two years, it's not a thesis, it's a vibe."

**Extraction**:
```json
{
  "text": "A thesis is admissible to the firm corpus only if it carries a falsification condition resolving within 24 months; theses without that horizon are routed to the open-questions queue, not the firm corpus.",
  "source_span": "I just feel that if a thesis isn't falsifiable inside two years, it's not a thesis, it's a vibe.",
  "principle_kind": "CRITERION",
  "domain_of_applicability": "Firm-level investment / methodology theses being proposed for the published corpus; does not apply to research notes or speculative drafts.",
  "quantifiable_proxies": ["months_to_resolution", "resolution_evidence_specified"],
  "decision_examples": [
    "Reject 'AI will reshape healthcare' as a firm thesis; accept 'large hospital systems will sign >2 generative-AI deals by Q2 2027'.",
    "Move 'crypto-native finance wins' from corpus to open-questions queue until a 24-month resolution clause is attached."
  ]
}
```

### Example 3 — MECHANISM (causal claim)

**Source span**: "We've found that scaled coherence checks tend to
miss the cases where two claims agree on surface words but disagree
on the underlying causal model."

**Extraction**:
```json
{
  "text": "Coherence checks based on lexical or geometric similarity alone accept surface-word agreement on contradictory causal models; any pair flagged by S₁ (consistency) but cleared by S₄ (geometric) must be routed to the judge layer before being treated as coherent.",
  "source_span": "We've found that scaled coherence checks tend to miss the cases where two claims agree on surface words but disagree on the underlying causal model.",
  "principle_kind": "MECHANISM",
  "domain_of_applicability": "Pairwise coherence evaluation inside the six-layer coherence engine; not relevant to single-claim freshness or solo confidence scoring.",
  "quantifiable_proxies": ["S1_consistency_score", "S4_geometric_score", "judge_layer_override_rate"],
  "decision_examples": [
    "Add a queue rule: S₁ verdict=contradict + S₄ ≥ 0.85 → judge override required.",
    "Audit the last 30 days of accepted-coherent pairs for S₁/S₄ disagreement and re-judge."
  ]
}
```

## Refusal examples (first-person source, no principle extractable)

### Refusal 1 — autobiographical reflection

**Source span**: "I have been thinking a lot lately about how much
of our edge is just patience."

**Refusal**:
```json
{
  "refusal": "NO_PRINCIPLE_EXTRACTABLE",
  "source_span": "I have been thinking a lot lately about how much of our edge is just patience.",
  "reason": "Autobiographical reflection with no decision rule, criterion, or testable claim. Generalising to 'patience is valuable' would be a tautology."
}
```

### Refusal 2 — preference statement without rule content

**Source span**: "I have since become a fan of Peter Thiel's idea."

**Refusal**:
```json
{
  "refusal": "NO_PRINCIPLE_EXTRACTABLE",
  "source_span": "I have since become a fan of Peter Thiel's idea.",
  "reason": "Stance update with no propositional content quoted; the idea itself is not in the span, so no rule can be extracted without inventing one."
}
```

Note: if the chunk DOES quote Thiel's idea elsewhere
("the most contrarian question is …"), THAT span is extractable
as a CRITERION (see Example 4 in the regression fixtures).

### Refusal 3 — mood / aesthetic statement

**Source span**: "Honestly, I just love this stuff."

**Refusal**:
```json
{
  "refusal": "NO_PRINCIPLE_EXTRACTABLE",
  "source_span": "Honestly, I just love this stuff.",
  "reason": "Aesthetic / affective statement. No rule, criterion, or comparison."
}
```
