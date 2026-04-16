"""Rigor gate — publication-gate infrastructure for Theseus/Noosphere."""

from noosphere.rigor_gate.checks import all_checks, register
from noosphere.rigor_gate.decorator import GateBlocked, configure_store, gated
from noosphere.rigor_gate.gate import Gate
from noosphere.rigor_gate.override import create_override
from noosphere.rigor_gate.refusal_dashboard import (
    DashboardData,
    monthly_stats,
    overrides_for_display,
)

__all__ = [
    "DashboardData",
    "Gate",
    "GateBlocked",
    "all_checks",
    "configure_store",
    "create_override",
    "gated",
    "monthly_stats",
    "overrides_for_display",
    "register",
]
