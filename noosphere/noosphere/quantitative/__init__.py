"""Quantitative formalisation of principles.

Bridges the firm's logical principles to numerical, falsifiable tests:
each Principle gets a ``QuantitativeFormalisation`` spec (null
hypothesis, metrics, statistical tests, data sources, decision
thresholds). Prompt 63 produces the SPEC layer; prompt 64 will run the
specs against real data.

This package exposes:

* ``formalisation`` — schema validation helpers and few-shot loader.
* ``drafter`` — the LLM-assisted drafter that proposes specs for
  principles without one. Refuses with a structured reason rather than
  fabricating data sources. Never marks rows APPROVED — founder review
  is required for that.
"""

from noosphere.quantitative.drafter import (
    DrafterRefusal,
    QuantitativeFormalisationDrafter,
)
from noosphere.quantitative.formalisation import (
    FewShotExample,
    SchemaConformanceError,
    enforce_approval_invariants,
    load_fewshot_examples,
    parse_drafter_json,
    validate_schema,
)

__all__ = [
    "DrafterRefusal",
    "FewShotExample",
    "QuantitativeFormalisationDrafter",
    "SchemaConformanceError",
    "enforce_approval_invariants",
    "load_fewshot_examples",
    "parse_drafter_json",
    "validate_schema",
]
