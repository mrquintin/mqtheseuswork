"""Sub-schemas and enums for the Logical Algorithm layer.

The Logical Algorithm is the third layer above principles: an
algorithm is a logical function — named inputs, named output, with
a structured reasoning body that invokes one or more principles
to derive the output from the inputs.

This module holds the *small* schemas — input / output / step
descriptors and the enums that drive validation. The top-level
``LogicalAlgorithm``, ``AlgorithmInvocation``, and
``AlgorithmInputObservation`` Pydantic models live in
``noosphere.models`` so they sit alongside the firm's other
domain entities.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AlgorithmInputType(str, Enum):
    """The shape of a single algorithm input.

    ``STRING`` is intentionally absent — algorithms must commit to
    a structured input type, not free text.
    """

    NUMBER = "NUMBER"
    RATIO = "RATIO"
    INDEX = "INDEX"
    BOOL = "BOOL"
    ENUM = "ENUM"
    TIMESERIES = "TIMESERIES"


class AlgorithmOutputType(str, Enum):
    """The shape of an algorithm's derived output.

    ``STRING`` is intentionally absent — see ``validate_output_schema``
    in ``noosphere.algorithms.validators``.
    """

    NUMBER = "NUMBER"
    RATIO = "RATIO"
    INDEX = "INDEX"
    BOOL = "BOOL"
    ENUM = "ENUM"
    SCORE = "SCORE"
    STRUCTURED = "STRUCTURED"


class ReasoningStepKind(str, Enum):
    """The role a single reasoning step plays in the algorithm body."""

    DETECT = "DETECT"
    APPLY_PRINCIPLE = "APPLY_PRINCIPLE"
    SYNTHESIZE = "SYNTHESIZE"
    OUTPUT = "OUTPUT"


class AlgorithmStatus(str, Enum):
    """Lifecycle states for a LogicalAlgorithm.

    ACTIVE means *eligible to fire*; the runtime (prompt 03) decides
    when. ``RETIRED`` is terminal and carries a ``retiredReason``.
    """

    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class AlgorithmCorrectness(str, Enum):
    """Outcome of an AlgorithmInvocation after reality is observed."""

    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    INDETERMINATE = "INDETERMINATE"


class AlgorithmInput(BaseModel):
    """One named input slot for a LogicalAlgorithm.

    ``observability_source`` names where the value will come from at
    runtime (e.g. ``"currents.x.spending_delta"``,
    ``"manual.operator.entered"``). The runtime (prompt 03) resolves
    the source string into a concrete observation.
    """

    name: str = Field(min_length=1, max_length=80)
    type: AlgorithmInputType
    description: str = Field(default="", max_length=400)
    observability_source: str = Field(default="", max_length=200)
    # Optional declaration for ENUM inputs: the allowed values.
    enum_values: list[str] = Field(default_factory=list)
    # Optional units for NUMBER/RATIO/INDEX inputs.
    units: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True, extra="forbid")


class AlgorithmOutput(BaseModel):
    """The single named output the algorithm derives.

    Outputs are structured by contract: the prompt that designed this
    layer explicitly rejects free-text outputs so downstream
    consumers (memo generator, bet expander, calibration) can
    machine-read them.
    """

    name: str = Field(min_length=1, max_length=80)
    type: AlgorithmOutputType
    description: str = Field(default="", max_length=400)
    units: Optional[str] = None
    # ``range`` is a two-tuple [low, high] for NUMBER/RATIO/INDEX/SCORE
    # outputs. Optional; not enforced numerically here — the runtime
    # uses it to render confidence bands on the public surface.
    range: Optional[list[float]] = None
    # For STRUCTURED outputs, optionally declare the keys + per-key
    # type. Not enforced as a strict JSON schema; treated as
    # documentation the synthesizer reads.
    fields: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True, extra="forbid")


class ReasoningStep(BaseModel):
    """One step in the algorithm's structured reasoning body.

    Reasoning steps are NOT free text. Each step declares its kind
    and the data it carries; the runtime (prompt 03) walks the list
    in order, threading observed inputs through ``DETECT`` /
    ``APPLY_PRINCIPLE`` / ``SYNTHESIZE`` steps to a final ``OUTPUT``.

    Fields:
        step_kind: which role this step plays.
        principle_id: required for APPLY_PRINCIPLE. References a
            principle row by its cuid.
        predicate: free-form predicate evaluated by the runtime —
            used by DETECT steps to decide whether the precondition
            for invoking principles holds. Same sandbox rules as
            ``LogicalAlgorithm.trigger_predicate``.
        derived_fact: human-readable summary of what is concluded
            after this step. Surfaces in the invocation trace.
    """

    step_kind: ReasoningStepKind
    principle_id: Optional[str] = None
    predicate: Optional[str] = None
    derived_fact: Optional[str] = Field(default=None, max_length=600)

    model_config = ConfigDict(use_enum_values=True, extra="forbid")


class AlgorithmBetImplied(BaseModel):
    """Structured bet recommendation an invocation may imply.

    Kept loose because the eventual ``polymorphic_bet_abstraction``
    (prompt 15) will own the canonical shape; this is the shipping
    placeholder so calibration can attach a bet pointer without
    waiting for that prompt.
    """

    venue: str = Field(default="", max_length=64)
    instrument: str = Field(default="", max_length=128)
    direction: str = Field(default="", max_length=32)
    sizing_hint: Optional[str] = Field(default=None, max_length=128)
    rationale: str = Field(default="", max_length=400)

    model_config = ConfigDict(extra="forbid")
