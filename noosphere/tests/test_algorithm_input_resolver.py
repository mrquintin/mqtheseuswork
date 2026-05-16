"""Tests for ``InputResolver`` and its adapter registry."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from noosphere.algorithms.adapters import (
    AdapterRegistry,
    InputObservation,
    StaticAdapter,
)
from noosphere.algorithms.adapters.manual_source import (
    ArtifactFieldAdapter,
    ManualOperatorAdapter,
)
from noosphere.algorithms.input_resolver import InputResolver
from noosphere.algorithms.schemas import (
    AlgorithmInput,
    AlgorithmInputType,
)


def _spec(name: str, source: str) -> AlgorithmInput:
    return AlgorithmInput(
        name=name,
        type=AlgorithmInputType.NUMBER,
        observability_source=source,
    )


def test_resolver_dispatches_to_longest_prefix():
    registry = AdapterRegistry()
    registry.register(
        StaticAdapter(
            prefix="currents.",
            values={"currents.x.escalation_index": 0.71},
        )
    )
    registry.register(
        StaticAdapter(
            prefix="currents.x.",
            values={"currents.x.escalation_index": 0.82},
            source_label="narrow",
        )
    )
    resolver = InputResolver(registry)

    obs = asyncio.run(
        resolver.resolve(_spec("escalation_index", "currents.x.escalation_index"))
    )
    assert obs is not None
    assert obs.value == 0.82


def test_resolver_returns_none_for_unknown_source():
    registry = AdapterRegistry()
    registry.register(StaticAdapter(prefix="currents.", values={}))
    resolver = InputResolver(registry)

    obs = asyncio.run(
        resolver.resolve(_spec("x", "markets.polymarket.foo.price"))
    )
    assert obs is None


def test_resolver_returns_none_for_blank_source():
    registry = AdapterRegistry()
    resolver = InputResolver(registry)
    obs = asyncio.run(resolver.resolve(_spec("x", "")))
    assert obs is None


def test_resolver_returns_none_when_value_missing():
    registry = AdapterRegistry()
    registry.register(
        StaticAdapter(prefix="currents.", values={"currents.x.other": 1.0})
    )
    resolver = InputResolver(registry)
    obs = asyncio.run(resolver.resolve(_spec("x", "currents.x.missing")))
    assert obs is None


def test_manual_operator_adapter_reads_provider():
    values: dict[str, object] = {"mediator_present": False}
    adapter = ManualOperatorAdapter(provider=lambda: values)
    registry = AdapterRegistry()
    registry.register(adapter)
    resolver = InputResolver(registry)

    obs = asyncio.run(
        resolver.resolve(
            _spec("mediator_present", "manual.operator.mediator_present")
        )
    )
    assert obs is not None
    assert obs.value is False

    values["mediator_present"] = True
    obs2 = asyncio.run(
        resolver.resolve(
            _spec("mediator_present", "manual.operator.mediator_present")
        )
    )
    assert obs2 is not None
    assert obs2.value is True


def test_artifact_field_adapter_pulls_from_cell_provider():
    cells = {("artifact_42", "side_a_spending"): 0.13}

    def lookup(artifact_id: str, field: str):
        return cells.get((artifact_id, field))

    adapter = ArtifactFieldAdapter(cell_provider=lookup)
    registry = AdapterRegistry()
    registry.register(adapter)
    resolver = InputResolver(registry)

    obs = asyncio.run(
        resolver.resolve(
            _spec("spending", "artifact.field.artifact_42.side_a_spending")
        )
    )
    assert obs is not None
    assert obs.value == 0.13
    assert obs.source_artifact_id == "artifact_42"

    miss = asyncio.run(
        resolver.resolve(_spec("spending", "artifact.field.artifact_42.unknown"))
    )
    assert miss is None


def test_static_adapter_preserves_existing_observation_metadata():
    custom = InputObservation(
        value=3.14,
        observed_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
        source="x.pi",
        source_url="https://example.com/data",
        source_artifact_id="artifact_pi",
    )
    adapter = StaticAdapter(prefix="x.", values={"x.pi": custom})
    registry = AdapterRegistry()
    registry.register(adapter)
    resolver = InputResolver(registry)

    obs = asyncio.run(resolver.resolve(_spec("pi", "x.pi")))
    assert obs is custom
