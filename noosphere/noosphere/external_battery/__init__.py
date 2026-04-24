"""External-corpus benchmarking battery: protocol, canonicalization, failure taxonomy, runner."""

from noosphere.external_battery.adapters import CorpusAdapter
from noosphere.external_battery.canonical import canonicalize
from noosphere.external_battery.failures import FailureKind, classify_failure
from noosphere.external_battery.run import BatteryRunner

__all__ = [
    "BatteryRunner",
    "CorpusAdapter",
    "FailureKind",
    "canonicalize",
    "classify_failure",
]
