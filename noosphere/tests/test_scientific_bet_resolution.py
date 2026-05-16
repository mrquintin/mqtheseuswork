"""SCIENTIFIC_BET resolver tests with fixture data feeds.

Confirms the resolver compares observed feed values to
``expected_value ± tolerance`` and stamps CORRECT / INCORRECT
accordingly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from noosphere.bets.lifecycle import run_lifecycle_once
from noosphere.bets.resolvers.scientific import (
    ScientificFeedProbe,
    resolve_scientific,
)
from noosphere.bets.spec import (
    BetKind,
    BetOutcome,
    BetSpec,
    BetStatus,
    ScientificBetSpec,
    ScientificDataSource,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _make_spec(*, expected: float, tolerance: float) -> BetSpec:
    return BetSpec(
        organization_id="org_a",
        kind=BetKind.SCIENTIFIC_BET,
        proposition="FRED series ABC > 1.4",
        resolution_criterion="observed >= 1.4 ± tolerance",
        horizon_at=NOW - timedelta(days=2),
        created_by_memo_id="memo_sci",
        scientific_bet=ScientificBetSpec(
            data_source=ScientificDataSource.FRED,
            metric_query={"series_id": "ABC"},
            expected_value=expected,
            tolerance=tolerance,
        ),
        status=BetStatus.OPEN,
    )


def test_resolves_correct_when_observed_within_tolerance() -> None:
    spec = _make_spec(expected=1.40, tolerance=0.05)
    probes = {
        ScientificDataSource.FRED: ScientificFeedProbe(
            fetch=lambda _q: 1.42,
            source_label="FRED-stub",
        )
    }
    resolution = resolve_scientific(spec, store=None, probes=probes)
    assert resolution is not None
    assert resolution.outcome == BetOutcome.CORRECT
    assert resolution.accuracy_score is not None
    assert abs(resolution.accuracy_score - 0.02) < 1e-9


def test_resolves_incorrect_outside_tolerance() -> None:
    spec = _make_spec(expected=1.40, tolerance=0.05)
    probes = {
        ScientificDataSource.FRED: ScientificFeedProbe(
            fetch=lambda _q: 1.60,
            source_label="FRED-stub",
        )
    }
    resolution = resolve_scientific(spec, store=None, probes=probes)
    assert resolution is not None
    assert resolution.outcome == BetOutcome.INCORRECT
    assert abs((resolution.accuracy_score or 0.0) - 0.20) < 1e-9


def test_resolver_defers_when_probe_returns_none() -> None:
    spec = _make_spec(expected=1.40, tolerance=0.05)
    probes = {
        ScientificDataSource.FRED: ScientificFeedProbe(fetch=lambda _q: None)
    }
    resolution = resolve_scientific(spec, store=None, probes=probes)
    assert resolution is None


def test_lifecycle_resolves_scientific_bet_against_fixture_feed() -> None:
    store = _store()
    spec = _make_spec(expected=2.50, tolerance=0.10)
    store.put_bet_spec(spec)
    probes = {
        ScientificDataSource.FRED: ScientificFeedProbe(
            fetch=lambda _q: 2.45,
            source_label="FRED-stub",
        )
    }
    report = run_lifecycle_once(
        store,
        organization_id="org_a",
        now=NOW,
        scientific_probes=probes,
    )
    assert report.resolved == 1
    refetched = store.get_bet_spec(spec.id)
    assert refetched is not None
    assert refetched.status == BetStatus.RESOLVED.value
    assert refetched.outcome == BetOutcome.CORRECT.value
    resolutions = store.list_bet_resolutions(bet_spec_id=spec.id)
    assert resolutions[0].accuracy_score is not None
    # observed - expected = -0.05; abs <= 0.10 → CORRECT
    assert abs(resolutions[0].accuracy_score + 0.05) < 1e-9
