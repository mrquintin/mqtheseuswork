"""Build example narrations for MethodDoc bundles.

Uses a strict template to narrate chosen test cases and de-identified ledger
invocations. The ``reviewed_by`` field must be set before publication.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from noosphere.models import MethodInvocation


def narrate_example(
    title: str,
    input_data: Any,
    output_data: Any,
    description: str = "",
) -> dict[str, Any]:
    """Create a structured example dict suitable for the compiler."""
    return {
        "title": title,
        "input": input_data if isinstance(input_data, dict) else {"value": input_data},
        "output": output_data if isinstance(output_data, dict) else {"value": output_data},
        "narrative": description,
    }


def narrate_invocations(
    invocations: list[MethodInvocation],
    *,
    max_items: int = 10,
) -> list[str]:
    """Produce de-identified invocation summaries."""
    summaries: list[str] = []
    for inv in invocations[:max_items]:
        status = "succeeded" if inv.succeeded else f"failed ({inv.error_kind or 'unknown'})"
        summaries.append(
            f"Invocation {inv.id[:8]}: {status}, "
            f"input_hash={inv.input_hash[:8]}, output_hash={inv.output_hash[:8]}"
        )
    return summaries


class ExamplesBuilder:
    """Accumulates examples for a method and enforces the review gate."""

    def __init__(self) -> None:
        self._examples: list[dict[str, Any]] = []
        self._invocation_summaries: list[str] = []
        self.reviewed_by: Optional[str] = None

    def add_example(
        self,
        title: str,
        input_data: Any,
        output_data: Any,
        description: str = "",
    ) -> None:
        self._examples.append(narrate_example(title, input_data, output_data, description))

    def add_invocation_summaries(
        self, invocations: list[MethodInvocation], *, max_items: int = 10
    ) -> None:
        self._invocation_summaries.extend(narrate_invocations(invocations, max_items=max_items))

    def set_reviewed_by(self, reviewer: str) -> None:
        self.reviewed_by = reviewer

    @property
    def examples(self) -> list[dict[str, Any]]:
        return list(self._examples)

    @property
    def invocation_summaries(self) -> list[str]:
        return list(self._invocation_summaries)

    def check_review_gate(self) -> None:
        """Raise if examples exist but no reviewer is set."""
        if (self._examples or self._invocation_summaries) and not self.reviewed_by:
            raise ValueError(
                "Examples require a reviewed_by field before publication. "
                "Call set_reviewed_by() or pass --require-review to compile."
            )
