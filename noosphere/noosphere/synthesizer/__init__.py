"""SynthesizerEngine — Round 19 prompt 10.

The synthesizer is the firm's reasoning organ: it consumes a question,
retrieves principles + algorithm invocations + currents, identifies
governing principles, walks a reasoning chain grounded in those
principles, checks for unresolved contradictions in the chain, and
emits a structured conclusion (with optional memo).

The synthesizer NEVER places a bet. It produces an audit-shaped
conclusion that the portfolio agent (prompt 12) acts on. Abstention is
first-class — refusing to emit a conclusion is a healthy outcome, not
a failure.

Public surface:

* :class:`SynthesizerEngine` — the engine.
* :class:`SynthesisResult` — what an engine call returns.
* :class:`SynthesisOutcome` — the closed set of outcomes.
* :class:`QuestionType` — the four canonical question types.
* :class:`Conclusion` / :class:`ReasoningChainStep` — the structured
  conclusion shape.
* :func:`identify_governing` — pure function over a principle list.
"""

from __future__ import annotations

from noosphere.synthesizer.engine import (
    SYNTHESIZER_VERSION,
    Conclusion,
    QuestionType,
    ReasoningChainStep,
    SynthesisOutcome,
    SynthesisResult,
    SynthesizerEngine,
    constitute_question,
)
from noosphere.synthesizer.governing import (
    DOMAIN_FUZZY_THRESHOLD,
    identify_governing,
)
from noosphere.synthesizer.memo_builder import (
    EIGHT_GATES,
    archive_memo,
    build_memo,
    publish_memo,
    render_memo_body,
    send_memo,
)
from noosphere.synthesizer.memo_pdf import build_memo_pdf, render_template
from noosphere.synthesizer.memo_validator import (
    MEMO_SECTIONS,
    MemoValidationError,
    SECTION_SPECS,
    ValidationResult,
    check_sections,
    validate_memo_body,
)

__all__ = [
    "Conclusion",
    "DOMAIN_FUZZY_THRESHOLD",
    "EIGHT_GATES",
    "MEMO_SECTIONS",
    "MemoValidationError",
    "QuestionType",
    "ReasoningChainStep",
    "SECTION_SPECS",
    "SYNTHESIZER_VERSION",
    "SynthesisOutcome",
    "SynthesisResult",
    "SynthesizerEngine",
    "ValidationResult",
    "archive_memo",
    "build_memo",
    "build_memo_pdf",
    "check_sections",
    "constitute_question",
    "identify_governing",
    "publish_memo",
    "render_memo_body",
    "render_template",
    "send_memo",
    "validate_memo_body",
]
