# Conclusions Registry — Usage Guide

The Conclusions Registry is a separate store for **SUBSTANTIVE claims** (conclusions about the world) that Theseus founders make. It creates a closed-loop system: substantive track records calibrate the Noosphere's methodological brain.

## Architecture

The firm's Noosphere has two layers:

1. **Methodological Brain** (noosphere.models, noosphere.principles) — How to think
2. **Conclusions Registry** (noosphere.conclusions) — What we've concluded about the world

When predictions resolve, accuracy data feeds back to calibrate methodology.

## Core Components

### Enums

- **ReasoningMethod**: deduction, induction, analogy, empirical, base_rate, first_principles, authority, pattern_matching, thought_experiment, abduction, unknown
- **ResolutionStatus**: unresolved, resolved_correct, resolved_incorrect, partially_correct, unresolvable

### Data Models

**Conclusion**: A substantive claim with method attribution
- text: The claim itself
- speaker_id, speaker_name: Who said it
- episode_id, episode_date: When/where
- domain: Topic area (technology, macro_economics, investing, geopolitics, science)
- method_used: Which reasoning method produced it
- confidence_expressed: Speaker's confidence (0-1)
- is_prediction: Whether falsifiable about the future
- falsification_condition: What would prove it wrong
- resolution_date: When to check
- resolved: True/False/None
- resolution_evidence: Supporting evidence
- methodological_context: Surrounding reasoning discourse
- linked_methodology_ids: IDs of methodological principles that produced this

**MethodAccuracyRecord**: Aggregate statistics for a method in a domain
- accuracy_rate: Proportion correct
- brier_score: Mean squared confidence error
- calibration_error: |average_confidence - accuracy_rate|

### Main Classes

**ConclusionsRegistry**
```python
from noosphere.conclusions import ConclusionsRegistry, Conclusion, ReasoningMethod
from datetime import date

registry = ConclusionsRegistry("path/to/registry.json")

# Register a conclusion
conclusion = Conclusion(
    text="AI will transform healthcare delivery by 2028",
    speaker_id="michael-001",
    speaker_name="Michael Quintin",
    episode_id="ep-042",
    episode_date=date(2026, 2, 15),
    domain="technology",
    method_used=ReasoningMethod.ANALOGY,
    confidence_expressed=0.65,
    is_prediction=True,
    falsification_condition="No major AI-powered diagnostic tools adopted by 50% of hospitals",
    resolution_date=date(2028, 12, 31),
    methodological_context="Drew analogy to prior tech adoption curves...",
)

conclusion_id = registry.register(conclusion)

# Query conclusions
tech_conclusions = registry.get_by_domain("technology")
analogy_conclusions = registry.get_by_method("analogy")
unresolved = registry.get_unresolved()
overdue = registry.get_predictions_due()  # Past resolution_date but not resolved

# Resolve a prediction
registry.resolve(
    conclusion_id,
    outcome=True,
    evidence="FDA approved 5 major AI diagnostic tools; adoption reached 45% by Nov 2028"
)

# Calculate method accuracy
accuracy = registry.method_accuracy("analogy", domain="technology")
print(f"Analogy accuracy in tech: {accuracy.accuracy_rate:.1%}")

# Get all accuracy records
all_records = registry.all_method_accuracies()

# Search conclusions
results = registry.search("healthcare", k=10)

# Persistence
registry.save()  # Automatic on register/resolve, but you can save explicitly
registry.load()  # Load from disk on init, but you can reload
```

**CalibrationAnalyzer** — Transforms accuracy data into methodological feedback

```python
from noosphere.conclusions import CalibrationAnalyzer

analyzer = CalibrationAnalyzer(registry)

# Method reliability report
report = analyzer.method_reliability_report()
# Returns: {
#   "analogy": {
#     "total_conclusions": 12,
#     "resolved_conclusions": 8,
#     "accuracy_rate": 0.625,
#     "average_confidence": 0.71,
#     "calibration_error": 0.085,
#     "confidence_assessment": "overconfident",
#     "best_domains": ["technology", "investing"],
#     "worst_domains": ["geopolitics"],
#     "recommendations": [...]
#   }
# }

# Domain-specific analysis
tech_report = analyzer.domain_report("technology")
# Returns: {
#   "domain": "technology",
#   "total_conclusions": 24,
#   "method_breakdown": {
#     "analogy": {"count": 8, "resolved": 6, "accuracy": 0.75},
#     "first_principles": {"count": 9, "resolved": 7, "accuracy": 0.57}
#   },
#   "best_method": "analogy",
#   "worst_method": "first_principles"
# }

# CRITICAL: Generate feedback for the methodological brain
feedback = analyzer.feedback_for_methodology()
# Returns methodological observations like:
# [
#   {
#     "feedback_type": "strength",
#     "method_involved": "analogy",
#     "observation": "Analogical reasoning demonstrates strong reliability with 62.5% accuracy...",
#     "confidence": 0.8,
#     "recommendation": "Increase reliance on analogical reasoning..."
#   },
#   {
#     "feedback_type": "calibration",
#     "method_involved": ["analogy", "pattern_matching"],
#     "observation": "The firm shows systematic overconfidence...",
#     "recommendation": "Implement confidence calibration training..."
#   }
# ]

# These feedbacks are METHODOLOGICAL CLAIMS that can feed back into the brain
# e.g., register as Principles: "Analogical reasoning is reliable in technology domains"
```

**AutoResolver** — Semi-automated resolution using Claude

```python
from noosphere.conclusions import AutoResolver

resolver = AutoResolver()  # Uses Anthropic client with API key

# Check if a prediction is resolvable now
is_resolvable, was_correct, evidence = resolver.check_resolvable(conclusion)

if is_resolvable:
    registry.resolve(conclusion.id, outcome=was_correct, evidence=evidence)
```

## Integration Pattern

The system creates a **closed-loop calibration cycle**:

1. **Ingestion**: Founders' substantive conclusions extracted with method tags
2. **Tracking**: Conclusions stored with confidence, falsification conditions, resolution dates
3. **Resolution**: As of dates pass, outcomes checked (manually or via AutoResolver)
4. **Analysis**: CalibrationAnalyzer aggregates accuracy by method × domain
5. **Feedback**: `feedback_for_methodology()` generates methodological observations
6. **Integration**: These observations registered as Principles in the main Noosphere brain
7. **Loop**: Improved methodology → better future conclusions

## Data Persistence

The registry persists to JSON:

```json
{
  "conclusions": [
    {
      "id": "uuid-here",
      "text": "AI will transform healthcare...",
      "method_used": "analogy",
      "domain": "technology",
      "accuracy_rate": null,
      "resolved": null,
      "created_at": "2026-02-15T14:30:00"
    }
  ]
}
```

## Example: Full Workflow

```python
from noosphere.conclusions import ConclusionsRegistry, Conclusion, ReasoningMethod, CalibrationAnalyzer
from datetime import date

# Initialize
registry = ConclusionsRegistry("data/conclusions.json")

# Register several predictions
conclusions = [
    Conclusion(
        text="Anthropic will release Claude 4 by end of 2027",
        speaker_id="michael", speaker_name="Michael",
        episode_id="ep-050", episode_date=date(2026, 3, 1),
        domain="technology", method_used=ReasoningMethod.PATTERN_MATCHING,
        confidence_expressed=0.7, is_prediction=True,
        resolution_date=date(2028, 1, 1)
    ),
    Conclusion(
        text="The S&P 500 will exceed 8000 by end of 2027",
        speaker_id="michael", speaker_name="Michael",
        episode_id="ep-050", episode_date=date(2026, 3, 1),
        domain="macro_economics", method_used=ReasoningMethod.BASE_RATE,
        confidence_expressed=0.6, is_prediction=True,
        resolution_date=date(2028, 1, 1)
    ),
]

for c in conclusions:
    registry.register(c)

# Time passes... resolutions happen
resolver = AutoResolver()
for conclusion in registry.get_predictions_due():
    is_resolvable, was_correct, evidence = resolver.check_resolvable(conclusion)
    if is_resolvable:
        registry.resolve(conclusion.id, outcome=was_correct, evidence=evidence)

# Analyze
analyzer = CalibrationAnalyzer(registry)
report = analyzer.method_reliability_report()

# Convert to methodological feedback
feedback = analyzer.feedback_for_methodology()

# Example output:
# "Pattern matching reasoning demonstrates strong reliability with 70% accuracy 
#  in technology domain. Recommendation: Increase reliance in tech predictions."

# This feedback becomes input to the methodological brain
print(f"Generated {len(feedback)} methodological observations")
for f in feedback:
    print(f"- {f['observation']}")
    print(f"  Recommendation: {f['recommendation']}\n")
```

## Key Insight

The Conclusions Registry is **not** a knowledge base of world facts. It's a **calibration engine** that measures the reliability of our reasoning methods. Every false prediction is evidence that a method is unreliable in a domain. Every correct prediction reinforces it.

The feedback loop works because:
- We track substantive claims tied to their reasoning methods
- We measure accuracy outcomes
- We aggregate by method and domain
- We generate methodological principles from the data
- These principles improve future reasoning

This is how intellectual capital compounds: not just by knowing things, but by learning which ways of thinking are reliable.
