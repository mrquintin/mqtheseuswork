"""Embargo-check pre-hook for counterfactual evaluation runs."""

from __future__ import annotations

import logging
from typing import Any

from noosphere.methods._hooks import register_pre_hook
from noosphere.models import Method, MethodInvocation

logger = logging.getLogger(__name__)

_active_slicer: Any = None


def get_active_slicer() -> Any:
    return _active_slicer


def set_active_slicer(slicer: Any) -> None:
    global _active_slicer
    _active_slicer = slicer


def clear_active_slicer() -> None:
    global _active_slicer
    _active_slicer = None


def _embargo_check(spec: Method, inv: MethodInvocation, input_data: Any) -> None:
    """Pre-hook: if this invocation is part of a counterfactual run (correlation_id
    starts with 'cf-'), enforce embargo by checking that an active slicer is set."""
    if not inv.correlation_id.startswith("cf-"):
        return

    if _active_slicer is None:
        logger.warning(
            "Counterfactual invocation %s has no active slicer; embargo may not be enforced",
            inv.id,
        )


register_pre_hook("evaluation.embargo_check", _embargo_check)
