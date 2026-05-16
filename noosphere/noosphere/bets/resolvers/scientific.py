"""SCIENTIFIC_BET resolver.

Queries a named external feed (BLS, FRED, World Bank, manual operator
entry) for the bet's metric and compares the observed value to
``expected_value`` within ``tolerance``. Data sources are pluggable via
``ScientificFeedProbe`` so tests can inject a deterministic stub
without touching the network.

Live network adapters for BLS/FRED/World Bank live behind operator
secrets and are wired separately; this module focuses on the
resolution math + the contract the probes must honour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from noosphere.bets.spec import (
    BetOutcome,
    BetResolution,
    BetSpec,
    ScientificDataSource,
)


@dataclass(frozen=True)
class ScientificFeedProbe:
    """Pluggable adapter that returns an observed value for one metric.

    ``fetch`` receives the bet's structured ``metric_query`` and
    returns either an observed numeric value or ``None`` if the feed
    cannot answer yet (the lifecycle ticker re-tries on the next
    pass).
    """

    fetch: Callable[[dict[str, Any]], Optional[float]]
    source_label: str = ""


def _default_probe_registry() -> dict[ScientificDataSource, ScientificFeedProbe]:
    """Default registry — every kind returns ``None`` (deferred).

    Production deploys override individual entries with live adapters.
    Tests inject deterministic stubs via the ``probes=`` argument to
    ``resolve_scientific``.
    """

    def _deferred(_query: dict[str, Any]) -> Optional[float]:
        return None

    return {
        source: ScientificFeedProbe(fetch=_deferred, source_label=source.value)
        for source in ScientificDataSource
    }


def resolve_scientific(
    spec: BetSpec,
    *,
    store: Any,  # noqa: ARG001
    probes: dict[ScientificDataSource, ScientificFeedProbe] | None = None,
) -> Optional[BetResolution]:
    """Attempt to resolve a SCIENTIFIC_BET against its named feed."""

    sci = spec.scientific_bet
    if sci is None:  # pragma: no cover - validator catches this
        return None
    registry = probes if probes is not None else _default_probe_registry()
    source = (
        sci.data_source
        if isinstance(sci.data_source, ScientificDataSource)
        else ScientificDataSource(sci.data_source)
    )
    probe = registry.get(source)
    if probe is None:
        return None
    observed = probe.fetch(dict(sci.metric_query))
    if observed is None:
        return None
    delta = observed - float(sci.expected_value)
    tolerance = float(sci.tolerance)
    within = abs(delta) <= tolerance
    outcome = BetOutcome.CORRECT if within else BetOutcome.INCORRECT
    return BetResolution(
        bet_spec_id=spec.id,
        outcome=outcome,
        evidence_note=(
            f"source={source.value} observed={observed} "
            f"expected={sci.expected_value} tolerance={tolerance}"
        ),
        accuracy_score=delta,
    )
