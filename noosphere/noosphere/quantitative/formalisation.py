"""Schema-validation utilities for quantitative formalisations.

The drafter (``noosphere.quantitative.drafter``) outputs JSON; the
founder triage UI persists what the drafter emitted alongside whatever
the founder edits. This module is the single place those JSON payloads
are parsed and validated, so the contract is enforced identically on
the drafter side and the persistence side.

Conventions:

* The canonical schema is the Pydantic ``QuantitativeFormalisation`` in
  ``noosphere.models``. ``validate_schema`` is the only public entry to
  build one from arbitrary JSON-shaped data.
* APPROVED rows have stricter invariants (non-empty null hypothesis,
  ≥ 1 metric, ≥ 1 test). The model validator enforces them at
  construction time; ``enforce_approval_invariants`` re-checks an
  already-built row before persistence.
* ``UNFORMALISABLE`` is a first-class drafter outcome, not an error
  state — the drafter is required to refuse rather than fabricate data
  sources. The founder still triages refusals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from noosphere.models import (
    FormalisationStatus,
    QuantitativeFormalisation,
)


class SchemaConformanceError(ValueError):
    """Raised when drafter JSON does not match the formalisation schema."""


def parse_drafter_json(raw: str) -> dict[str, Any]:
    """Tolerantly parse the drafter's JSON output.

    Some LLMs wrap JSON in code fences or prose; this strips fenced
    blocks before parsing so the drafter does not need a perfect
    response harness. Raises ``SchemaConformanceError`` on any
    unparseable payload.
    """

    text = (raw or "").strip()
    if not text:
        raise SchemaConformanceError("empty drafter response")

    if text.startswith("```"):
        # Drop opening fence (``` or ```json) and any closing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # If the model included explanatory prose around a JSON object,
    # extract the first balanced { ... } substring.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise SchemaConformanceError("no JSON object found in drafter response")
        text = text[start : end + 1]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaConformanceError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SchemaConformanceError("drafter JSON must be an object at top level")
    return payload


def validate_schema(
    data: dict[str, Any],
    *,
    principle_id: str,
) -> QuantitativeFormalisation:
    """Build a validated ``QuantitativeFormalisation`` from raw JSON.

    The drafter must never set ``APPROVED`` — enforced here so a
    misbehaving LLM cannot self-approve.
    """

    payload = dict(data)
    payload.setdefault("principle_id", principle_id)
    # Coerce common drafter shapes that violate the contract.
    if payload.get("status") == FormalisationStatus.APPROVED.value:
        raise SchemaConformanceError(
            "drafter is not permitted to mark formalisations APPROVED"
        )
    try:
        return QuantitativeFormalisation(**payload)
    except ValidationError as exc:
        raise SchemaConformanceError(str(exc)) from exc


def enforce_approval_invariants(formalisation: QuantitativeFormalisation) -> None:
    """Re-check APPROVED invariants before persistence.

    The model validator already runs these at construction time. This
    function is the documented, callable invariant for triage code
    paths that mutate ``status`` after construction (e.g. the founder
    accept handler).
    """

    if formalisation.status not in {
        FormalisationStatus.APPROVED.value,
        FormalisationStatus.APPROVED,
    }:
        return
    if not (formalisation.null_hypothesis or "").strip():
        raise SchemaConformanceError(
            "APPROVED formalisation requires a non-empty null_hypothesis"
        )
    if not formalisation.metrics:
        raise SchemaConformanceError(
            "APPROVED formalisation requires at least one metric"
        )
    if not formalisation.tests:
        raise SchemaConformanceError(
            "APPROVED formalisation requires at least one test"
        )


@dataclass(frozen=True)
class FewShotExample:
    """A founder-approved formalisation rendered for the drafter prompt."""

    principle_text: str
    formalisation_json: str


def load_fewshot_examples(
    approved: list[QuantitativeFormalisation],
    principle_text_by_id: dict[str, str],
    *,
    max_examples: int = 3,
) -> list[FewShotExample]:
    """Render up to ``max_examples`` approved formalisations as few-shot.

    The drafter benefits from seeing the firm's own house style for
    metric definitions and test specs, not generic textbook examples.
    Falls back to an empty list if no approved rows exist yet — the
    drafter prompt then leans only on its system instructions.
    """

    out: list[FewShotExample] = []
    for f in approved:
        principle_text = principle_text_by_id.get(f.principle_id)
        if not principle_text:
            continue
        out.append(
            FewShotExample(
                principle_text=principle_text,
                formalisation_json=f.model_dump_json(indent=2),
            )
        )
        if len(out) >= max_examples:
            break
    return out


SYSTEM_PROMPT_PATH = (
    Path(__file__).parent / "_prompts" / "drafter_system.md"
)


def load_system_prompt() -> str:
    """Read the drafter's system prompt from the bundled markdown file."""

    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
