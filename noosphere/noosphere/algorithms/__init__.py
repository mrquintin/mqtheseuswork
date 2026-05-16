"""The Logical Algorithm layer.

An algorithm is a logical function: named inputs, named output, with
a structured reasoning body that invokes one or more principles
to derive the output from the inputs.

This package exposes:

* :mod:`noosphere.algorithms.schemas` — small sub-schemas
  (inputs / outputs / reasoning steps) and the enums driving them.
* :mod:`noosphere.algorithms.validators` — sandbox parsers and
  promotion guards.

The top-level entities (``LogicalAlgorithm``, ``AlgorithmInvocation``,
``AlgorithmInputObservation``) live in :mod:`noosphere.models`.
"""

from noosphere.algorithms.schemas import (
    AlgorithmBetImplied,
    AlgorithmCorrectness,
    AlgorithmInput,
    AlgorithmInputType,
    AlgorithmOutput,
    AlgorithmOutputType,
    AlgorithmStatus,
    ReasoningStep,
    ReasoningStepKind,
)
from noosphere.algorithms.validators import (
    AlgorithmValidationError,
    validate_inputs,
    validate_output_schema,
    validate_promotion_to_active,
    validate_reasoning_chain,
    validate_status_transition,
    validate_trigger_predicate,
)

__all__ = [
    "AlgorithmBetImplied",
    "AlgorithmCorrectness",
    "AlgorithmInput",
    "AlgorithmInputType",
    "AlgorithmOutput",
    "AlgorithmOutputType",
    "AlgorithmStatus",
    "AlgorithmValidationError",
    "ReasoningStep",
    "ReasoningStepKind",
    "validate_inputs",
    "validate_output_schema",
    "validate_promotion_to_active",
    "validate_reasoning_chain",
    "validate_status_transition",
    "validate_trigger_predicate",
]
