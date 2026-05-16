"""Validators for the Logical Algorithm layer.

Two contracts are enforced here:

1. **Trigger predicate sandbox.** Algorithms carry a string predicate
   evaluated by the runtime (prompt 03) over their declared inputs.
   The string is parsed with :mod:`ast` and walked against an
   allow-list of node kinds and identifiers. Anything that could
   reach beyond ``input.<name>`` is rejected at promotion time so
   the runtime can ``eval`` confidently later.

2. **Promotion to ACTIVE.** An algorithm cannot be promoted past
   ``UNDER_REVIEW`` while any source-principle is revoked. The
   notion of "revoked" is supplied by the caller — the store helper
   threads a set of revoked principle ids gathered from the
   Codex-side ``Principle`` table.
"""

from __future__ import annotations

import ast
from typing import Iterable

from noosphere.algorithms.schemas import (
    AlgorithmInput,
    AlgorithmOutput,
    AlgorithmOutputType,
    AlgorithmStatus,
    ReasoningStep,
    ReasoningStepKind,
)


class AlgorithmValidationError(ValueError):
    """Raised when an algorithm definition or transition is invalid."""


# ── Trigger predicate sandbox ───────────────────────────────────────────────

# AST node kinds we will tolerate inside a trigger predicate. The list
# is deliberately narrow: predicates exist to gate firing, not to do
# computation. Anything outside this set raises.
_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
    ast.Constant,
    ast.Name,
    ast.Attribute,
    ast.Load,
    ast.Tuple,
    ast.List,
)

# The only bare identifier we allow is ``input`` — the runtime binds
# this name to a mapping of observed values keyed by input name.
_ALLOWED_NAMES: frozenset[str] = frozenset({"input"})


def validate_trigger_predicate(
    predicate: str, *, input_names: Iterable[str]
) -> None:
    """Sandbox-evaluate the predicate against the declared input names.

    Raises :class:`AlgorithmValidationError` on any of:

    - the string is not parseable as a Python expression,
    - it contains any AST node outside the allow-list (calls, comprehensions,
      lambdas, ``__import__`` shenanigans),
    - it references a bare name other than ``input``,
    - it dereferences ``input.<name>`` for a name not declared in the
      algorithm's inputs,
    - it uses any attribute access beyond a single ``input.<attr>`` hop.
    """

    if not isinstance(predicate, str) or not predicate.strip():
        raise AlgorithmValidationError("trigger_predicate must be a non-empty string")

    allowed_inputs = set(input_names)

    try:
        tree = ast.parse(predicate, mode="eval")
    except SyntaxError as exc:
        raise AlgorithmValidationError(
            f"trigger_predicate is not a valid Python expression: {exc.msg}"
        ) from exc

    for node in ast.walk(tree):
        if isinstance(node, _ALLOWED_NODES):
            # Name nodes need extra scrutiny.
            if isinstance(node, ast.Name):
                if node.id not in _ALLOWED_NAMES:
                    raise AlgorithmValidationError(
                        f"trigger_predicate references disallowed identifier "
                        f"{node.id!r}; only 'input' is permitted"
                    )
            # Attribute access must be a single hop off ``input``.
            if isinstance(node, ast.Attribute):
                if not (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "input"
                ):
                    raise AlgorithmValidationError(
                        "trigger_predicate may only reference attributes of "
                        "'input' (e.g. input.escalation_index)"
                    )
                if node.attr not in allowed_inputs:
                    raise AlgorithmValidationError(
                        f"trigger_predicate references unknown input "
                        f"{node.attr!r}; declared inputs: "
                        f"{sorted(allowed_inputs)}"
                    )
            continue
        raise AlgorithmValidationError(
            f"trigger_predicate contains disallowed construct "
            f"{type(node).__name__}"
        )


# ── Output schema validator ─────────────────────────────────────────────────


def validate_output_schema(output: AlgorithmOutput) -> None:
    """Reject outputs that are not committed to a structured shape.

    The output's ``type`` must be one of the concrete kinds declared
    in :class:`AlgorithmOutputType`. ``STRING`` is intentionally
    absent from that enum — but we double-guard here in case a stray
    string slips through validation upstream.
    """

    type_value = (
        output.type.value if hasattr(output.type, "value") else str(output.type)
    )
    if type_value.upper() == "STRING":
        raise AlgorithmValidationError(
            "Algorithm output type 'STRING' is not allowed — pick a "
            "structured type (NUMBER, RATIO, INDEX, BOOL, ENUM, SCORE, "
            "STRUCTURED)"
        )
    try:
        AlgorithmOutputType(type_value)
    except ValueError as exc:
        raise AlgorithmValidationError(
            f"Algorithm output type {type_value!r} is not a known "
            f"AlgorithmOutputType"
        ) from exc


# ── Inputs / reasoning chain coherence ──────────────────────────────────────


def validate_inputs(inputs: list[AlgorithmInput]) -> None:
    """Enforce structural rules across the input list."""

    if not inputs:
        raise AlgorithmValidationError(
            "LogicalAlgorithm requires at least one input"
        )
    seen: set[str] = set()
    for inp in inputs:
        if inp.name in seen:
            raise AlgorithmValidationError(
                f"duplicate input name {inp.name!r}"
            )
        seen.add(inp.name)


def validate_reasoning_chain(
    chain: list[ReasoningStep], *, source_principle_ids: list[str]
) -> None:
    """Enforce structural rules on the reasoning chain.

    * Must be non-empty.
    * Every ``APPLY_PRINCIPLE`` step must name a ``principle_id``
      that appears in ``source_principle_ids``.
    * Must end with an ``OUTPUT`` step (the synthesiser otherwise
      has no terminator to read).
    """

    if not chain:
        raise AlgorithmValidationError(
            "reasoning_chain must contain at least one step"
        )
    allowed_principles = set(source_principle_ids)
    for step in chain:
        kind = step.step_kind
        kind_value = kind.value if hasattr(kind, "value") else str(kind)
        if kind_value == ReasoningStepKind.APPLY_PRINCIPLE.value:
            if not step.principle_id:
                raise AlgorithmValidationError(
                    "APPLY_PRINCIPLE step requires a principle_id"
                )
            if step.principle_id not in allowed_principles:
                raise AlgorithmValidationError(
                    f"APPLY_PRINCIPLE step references principle "
                    f"{step.principle_id!r} which is not in "
                    f"sourcePrincipleIds"
                )
    last_kind = chain[-1].step_kind
    last_value = (
        last_kind.value if hasattr(last_kind, "value") else str(last_kind)
    )
    if last_value != ReasoningStepKind.OUTPUT.value:
        raise AlgorithmValidationError(
            "reasoning_chain must terminate with an OUTPUT step"
        )


# ── Status transitions ──────────────────────────────────────────────────────


def validate_promotion_to_active(
    *,
    current_status: AlgorithmStatus | str,
    new_status: AlgorithmStatus | str,
    source_principle_ids: list[str],
    revoked_principle_ids: Iterable[str],
) -> None:
    """Block ACTIVE promotion when any source principle is revoked.

    All other transitions go through ``validate_status_transition`` —
    this helper is dedicated to the revoked-principle guard because
    it is the rule founders are most likely to violate by accident.
    """

    new_value = (
        new_status.value if hasattr(new_status, "value") else str(new_status)
    )
    if new_value != AlgorithmStatus.ACTIVE.value:
        return
    revoked = set(revoked_principle_ids)
    offending = [pid for pid in source_principle_ids if pid in revoked]
    if offending:
        raise AlgorithmValidationError(
            "Cannot promote algorithm to ACTIVE while sourcePrincipleIds "
            f"include revoked principles: {offending}"
        )


_TERMINAL_STATES: frozenset[str] = frozenset({AlgorithmStatus.RETIRED.value})


def validate_status_transition(
    *, current_status: AlgorithmStatus | str, new_status: AlgorithmStatus | str
) -> None:
    """Validate a status transition independent of principle state.

    RETIRED is terminal; transitions out of it are rejected. All
    other transitions are permitted — the founder UI is the source
    of truth for the workflow.
    """

    current_value = (
        current_status.value
        if hasattr(current_status, "value")
        else str(current_status)
    )
    new_value = (
        new_status.value if hasattr(new_status, "value") else str(new_status)
    )
    if current_value in _TERMINAL_STATES and new_value != current_value:
        raise AlgorithmValidationError(
            f"Algorithm in terminal state {current_value!r} cannot "
            f"transition to {new_value!r}"
        )
    try:
        AlgorithmStatus(new_value)
    except ValueError as exc:
        raise AlgorithmValidationError(
            f"Unknown AlgorithmStatus {new_value!r}"
        ) from exc
