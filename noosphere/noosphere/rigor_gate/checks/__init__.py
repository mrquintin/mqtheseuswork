"""Check registry for the rigor gate. Concrete checks land in wave_6/03."""

from __future__ import annotations

from collections.abc import Callable

from noosphere.models import CheckResult, RigorSubmission

_CHECKS: dict[str, Callable[[RigorSubmission], CheckResult]] = {}


def register(name: str, fn: Callable[[RigorSubmission], CheckResult]) -> None:
    _CHECKS[name] = fn


def all_checks() -> dict[str, Callable[[RigorSubmission], CheckResult]]:
    return dict(_CHECKS)
