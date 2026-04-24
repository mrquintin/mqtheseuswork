# Conclusions Registry — API Reference

Complete API documentation for `noosphere.conclusions`.

## Enums

### ReasoningMethod
```python
class ReasoningMethod(str, Enum):
    DEDUCTION = "deduction"
    INDUCTION = "induction"
    ANALOGY = "analogy"
    EMPIRICAL = "empirical"
    BASE_RATE = "base_rate"
    FIRST_PRINCIPLES = "first_principles"
    AUTHORITY = "authority"
    PATTERN_MATCHING = "pattern_matching"
    THOUGHT_EXPERIMENT = "thought_experiment"
    ABDUCTION = "abduction"
    UNKNOWN = "unknown"
```

### ResolutionStatus
```python
class ResolutionStatus(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED_CORRECT = "resolved_correct"
    RESOLVED_INCORRECT = "resolved_incorrect"
    PARTIALLY_CORRECT = "partially_correct"
    UNRESOLVABLE = "unresolvable"
```

## Models

### Conclusion

Substantive claim with method attribution.

**Fields:**
- `id: str` — UUID (auto-generated)
- `text: str` — The substantive claim
- `speaker_id: str` — Founder ID
- `speaker_name: str` — Founder name
- `episode_id: str` — Episode identifier
- `episode_date: date` — When the episode aired
- `domain: str` — Topic domain (technology, macro_economics, investing, geopolitics, science)
- `method_used: ReasoningMethod` — Reasoning method (default: UNKNOWN)
- `confidence_expressed: float` — Speaker confidence (0.0-1.0)
- `is_prediction: bool` — Falsifiable about future (default: False)
- `falsification_condition: Optional[str]` — What would prove it wrong
- `resolution_date: Optional[date]` — When to check if correct
- `resolved: Optional[bool]` — True/False/None (None = unresolved)
- `resolution_evidence: Optional[str]` — Evidence for resolution
- `created_at: datetime` — When registered (auto-set)
- `methodological_context: str` — Surrounding reasoning discourse
- `linked_methodology_ids: List[str]` — Principle IDs

**Methods:**
```python
def status(self) -> ResolutionStatus:
    """Return current resolution status."""
```

**Example:**
```python
from noosphere.conclusions import Conclusion, ReasoningMethod
from datetime import date

c = Conclusion(
    text="AI will transform healthcare by 2028",
    speaker_id="michael-001",
    speaker_name="Michael",
    episode_id="ep-042",
    episode_date=date(2026, 2, 15),
    domain="technology",
    method_used=ReasoningMethod.ANALOGY,
    confidence_expressed=0.65,
    is_prediction=True,
    falsification_condition="No major AI diagnostic tools adopted",
    resolution_date=date(2028, 12, 31),
)
```

### MethodAccuracyRecord

Accuracy statistics for a method in a domain.

**Fields:**
- `method_name: ReasoningMethod` — Which method
- `domain: str` — Which domain (or "all")
- `total_conclusions: int` — Total predictions made
- `resolved_conclusions: int` — Predictions checked
- `correct_count: int` — Number correct
- `incorrect_count: int` — Number incorrect
- `accuracy_rate: Optional[float]` — Proportion correct (0.0-1.0)
- `brier_score: Optional[float]` — Mean squared confidence error
- `average_confidence: float` — Mean confidence (0.0-1.0)
- `calibration_error: Optional[float]` — |avg_confidence - accuracy_rate|

### ConclusionSummary

Lightweight summary for display.

**Fields:**
- `id: str`
- `text: str`
- `speaker_name: str`
- `domain: str`
- `method_used: str`
- `confidence_expressed: float`
- `is_prediction: bool`
- `resolved: Optional[bool]`
- `created_at: datetime`

## ConclusionsRegistry

Persistent store for substantive conclusions.

### Constructor
```python
def __init__(self, data_path: str = "conclusions_registry.json"):
    """Initialize registry, auto-loads from disk if exists."""
```

### Methods

#### register
```python
def register(self, conclusion: Conclusion) -> str:
    """
    Register a new conclusion.
    
    Args:
        conclusion: Conclusion object
    
    Returns:
        The conclusion's ID
    """
```

#### resolve
```python
def resolve(
    self,
    conclusion_id: str,
    outcome: bool,
    evidence: str = ""
) -> Conclusion:
    """
    Record resolution outcome for a conclusion.
    
    Args:
        conclusion_id: ID of conclusion to resolve
        outcome: True if correct, False if incorrect
        evidence: Supporting evidence
    
    Returns:
        Updated Conclusion
    
    Raises:
        ValueError: If conclusion not found
    """
```

#### get_by_method
```python
def get_by_method(self, method: str) -> List[Conclusion]:
    """
    Get all conclusions using a given reasoning method.
    
    Args:
        method: ReasoningMethod value as string
    
    Returns:
        List of Conclusions
    """
```

#### get_by_domain
```python
def get_by_domain(self, domain: str) -> List[Conclusion]:
    """
    Get all conclusions in a domain.
    
    Args:
        domain: Domain name
    
    Returns:
        List of Conclusions
    """
```

#### get_unresolved
```python
def get_unresolved(self) -> List[Conclusion]:
    """
    Get all unresolved conclusions.
    
    Returns:
        List of Conclusions with resolved=None
    """
```

#### get_predictions_due
```python
def get_predictions_due(
    self,
    as_of: Optional[date] = None
) -> List[Conclusion]:
    """
    Get predictions whose resolution_date has passed but aren't resolved.
    
    Args:
        as_of: Date to check against (default: today)
    
    Returns:
        List of overdue Conclusions
    """
```

#### method_accuracy
```python
def method_accuracy(
    self,
    method: str,
    domain: Optional[str] = None
) -> MethodAccuracyRecord:
    """
    Calculate accuracy statistics for a method.
    
    Args:
        method: ReasoningMethod value
        domain: Optional domain filter
    
    Returns:
        MethodAccuracyRecord with stats
    """
```

#### all_method_accuracies
```python
def all_method_accuracies(self) -> List[MethodAccuracyRecord]:
    """
    Get accuracy breakdown by method x domain.
    
    Returns:
        List of MethodAccuracyRecords
    """
```

#### save
```python
def save(self) -> None:
    """Persist registry to JSON."""
```

#### load
```python
def load(self) -> None:
    """Load registry from JSON. Called automatically on init."""
```

#### search
```python
def search(self, query: str, k: int = 10) -> List[ConclusionSummary]:
    """
    Simple text search over conclusions.
    
    Args:
        query: Search term
        k: Max results to return
    
    Returns:
        List of matching ConclusionSummary objects
    """
```

## CalibrationAnalyzer

Analyzes accuracy data to generate methodological feedback.

### Constructor
```python
def __init__(self, registry: ConclusionsRegistry):
    """Initialize with a registry."""
```

### Methods

#### method_reliability_report
```python
def method_reliability_report(self) -> Dict:
    """
    Generate comprehensive reliability assessment for each method.
    
    Returns:
        Dict mapping method name to:
        {
            "total_conclusions": int,
            "resolved_conclusions": int,
            "accuracy_rate": float,
            "average_confidence": float,
            "calibration_error": float,
            "brier_score": float,
            "confidence_assessment": "well-calibrated" | "overconfident" | "underconfident",
            "best_domains": List[str],
            "worst_domains": List[str],
            "recommendations": List[str]
        }
    """
```

#### domain_report
```python
def domain_report(self, domain: str) -> Dict:
    """
    Generate performance analysis for a domain.
    
    Args:
        domain: Domain name
    
    Returns:
        Dict with:
        {
            "domain": str,
            "total_conclusions": int,
            "resolved_conclusions": int,
            "method_breakdown": {
                method: {
                    "count": int,
                    "resolved": int,
                    "accuracy": float
                }
            },
            "best_method": str,
            "worst_method": str
        }
    """
```

#### feedback_for_methodology
```python
def feedback_for_methodology(self) -> List[Dict]:
    """
    CRITICAL INTEGRATION METHOD.
    Generate methodological observations from accuracy data.
    
    Returns:
        List of feedback dicts, each with:
        {
            "feedback_type": "strength" | "weakness" | "calibration" | "combination" | "domain_strength",
            "method_involved": str or List[str],
            "observation": str,  # The methodological claim
            "domain": str,       # "all" or specific domain
            "confidence": float, # How confident in this feedback
            "evidence": Dict,    # Supporting statistics
            "recommendation": str
        }
    
    These outputs are METHODOLOGICAL CLAIMS about which methods work.
    They can be registered as Principles in the main Noosphere brain.
    """
```

## AutoResolver

Semi-automatic resolution using Claude with web search context.

### Constructor
```python
def __init__(self, client: Optional[Anthropic] = None):
    """
    Initialize resolver.
    
    Args:
        client: Optional Anthropic client (creates one if not provided)
    """
```

### Methods

#### check_resolvable
```python
def check_resolvable(
    self,
    conclusion: Conclusion
) -> Tuple[bool, Optional[bool], str]:
    """
    Determine if a prediction can be resolved and, if so, its accuracy.
    
    Uses Claude to reason about:
    1. Can this be checked yet? (based on resolution_date)
    2. If yes, was it correct?
    3. What evidence supports the determination?
    
    Args:
        conclusion: The Conclusion to check
    
    Returns:
        Tuple of:
        - is_resolvable (bool): Can check now?
        - was_correct (Optional[bool]): Correct if resolvable, None otherwise
        - reasoning (str): Explanation
    """
```

## Usage Pattern

```python
from noosphere.conclusions import (
    ConclusionsRegistry,
    Conclusion,
    ReasoningMethod,
    CalibrationAnalyzer,
    AutoResolver
)
from datetime import date

# 1. Create registry
registry = ConclusionsRegistry("data/conclusions.json")

# 2. Register conclusions
conclusion = Conclusion(
    text="Prediction about the world",
    speaker_id="...", speaker_name="...",
    episode_id="...", episode_date=date(...),
    domain="technology",
    method_used=ReasoningMethod.ANALOGY,
    confidence_expressed=0.7,
    is_prediction=True,
    resolution_date=date(2028, 1, 1)
)
registry.register(conclusion)

# 3. Track overdue predictions
due = registry.get_predictions_due()

# 4. Resolve using AutoResolver
resolver = AutoResolver()
for c in due:
    is_resolvable, correct, evidence = resolver.check_resolvable(c)
    if is_resolvable:
        registry.resolve(c.id, outcome=correct, evidence=evidence)

# 5. Analyze and generate feedback
analyzer = CalibrationAnalyzer(registry)
feedback = analyzer.feedback_for_methodology()

# 6. Feed back to methodological brain
for f in feedback:
    # Register as Principle: "Method X is reliable in domain Y"
    principle = create_principle_from_feedback(f)
    principle_registry.register(principle)
```

## Error Handling

All methods include logging and error handling. Exceptions are logged but allow graceful degradation.

```python
try:
    registry.resolve(conclusion_id, True, "Evidence")
except ValueError as e:
    logger.error(f"Resolution failed: {e}")
```

## Performance Notes

- **Search** is O(n) text scanning; for large registries, consider full-text search indexing
- **Accuracy calculation** is O(n) where n = conclusions; cache results if needed
- **JSON persistence** loads entire registry into memory; suitable for thousands of conclusions
- **AutoResolver** makes API calls to Claude; cache resolution results to avoid redundant calls

## Data Format (JSON)

```json
{
  "conclusions": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "text": "Substantive claim here",
      "speaker_id": "speaker-001",
      "speaker_name": "Name",
      "episode_id": "ep-042",
      "episode_date": "2026-02-15",
      "domain": "technology",
      "method_used": "analogy",
      "confidence_expressed": 0.65,
      "is_prediction": true,
      "falsification_condition": "Condition for falsity",
      "resolution_date": "2028-12-31",
      "resolved": null,
      "resolution_evidence": null,
      "created_at": "2026-02-15T14:30:00",
      "methodological_context": "Reasoning context",
      "linked_methodology_ids": ["principle-id-1", "principle-id-2"]
    }
  ]
}
```
