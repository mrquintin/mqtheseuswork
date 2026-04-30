"""Forecast retrieval adapter tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from noosphere.forecasts import retrieval_adapter as adapter
from noosphere.forecasts.retrieval_adapter import (
    build_query_from_market,
    retrieve_for_market,
)
from noosphere.models import Conclusion, ForecastMarket, ForecastSource


ORG_ID = "org_forecast_retrieval"


@dataclass
class MemoryStore:
    conclusions: list[Conclusion]

    def list_conclusions(self) -> list[Conclusion]:
        return self.conclusions

    def get_conclusion(self, conclusion_id: str) -> Conclusion | None:
        for conclusion in self.conclusions:
            if conclusion.id == conclusion_id:
                return conclusion
        return None

    def get_claim(self, _claim_id: str) -> None:
        return None


class CapturingLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **fields: object) -> None:
        self.entries.append((event, fields))


def _market(
    *,
    market_id: str = "forecast_market_test",
    title: str = "Will AI lab revenue exceed expectations?",
    description: str = "A binary market on whether AI lab revenue beats consensus.",
    resolution_criteria: str = "Resolves YES if reported revenue exceeds consensus.",
    category: str = "technology",
) -> ForecastMarket:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
    return ForecastMarket(
        id=market_id,
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id=market_id,
        title=title,
        description=description,
        resolution_criteria=resolution_criteria,
        category=category,
        raw_payload={"fixture": True},
        created_at=now,
        updated_at=now,
    )


def _conclusion(
    conclusion_id: str,
    text: str,
    *,
    created_at: datetime | None = None,
    visibility: str = "PUBLIC",
    surfaceable: bool | None = None,
    is_revoked: bool = False,
    is_load_bearing: bool = False,
    score: float = 0.95,
) -> Conclusion:
    conclusion = Conclusion(
        id=conclusion_id,
        text=text,
        created_at=created_at or datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
        updated_at=created_at or datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
    )
    conclusion.__dict__["visibility"] = visibility
    if surfaceable is not None:
        conclusion.__dict__["surfaceable"] = surfaceable
    if is_revoked:
        conclusion.__dict__["is_revoked"] = True
    if is_load_bearing:
        conclusion.__dict__["is_load_bearing"] = True
    conclusion.__dict__["_retrieval_score"] = score
    return conclusion


def _patch_retrieval(monkeypatch) -> None:
    def fake_retrieve_for_event(store: MemoryStore, _event, top_k: int):
        return [
            SimpleNamespace(
                source_kind="conclusion",
                source_id=conclusion.id,
                text=conclusion.text,
                score=conclusion.__dict__.get("_retrieval_score", 0.9),
            )
            for conclusion in store.list_conclusions()[:top_k]
        ]

    monkeypatch.setattr(adapter, "retrieve_for_event", fake_retrieve_for_event)


def test_build_query_recipe() -> None:
    description = "D" * 650
    criteria = "R" * 450
    market = _market(
        title="Will the bill pass?",
        description=description,
        resolution_criteria=criteria,
        category="policy",
    )

    query = build_query_from_market(market)

    assert query.startswith("Will the bill pass?\n\n")
    assert "\n\n" + ("D" * 600) + "\n\n" in query
    assert "D" * 601 not in query
    assert "Resolution criteria: " + ("R" * 400) in query
    assert "R" * 401 not in query
    assert query.endswith("\n\nCategory: policy")


def test_filters_non_surfaceable_founder_sources(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    store = MemoryStore(
        [
            _conclusion("public_a", "Public source A."),
            _conclusion("public_b", "Public source B."),
            _conclusion(
                "founder_public",
                "Founder source deliberately cleared for public use.",
                visibility="FOUNDER",
                surfaceable=True,
            ),
            _conclusion(
                "founder_private",
                "Founder source that must not surface publicly.",
                visibility="FOUNDER",
                surfaceable=False,
            ),
        ]
    )

    sources = retrieve_for_market(store, _market(), top_k=8)

    by_id = {source.source_id: source for source in sources}
    assert set(by_id) == {"public_a", "public_b", "founder_public"}
    assert by_id["founder_public"].visibility == "FOUNDER"
    assert by_id["founder_public"].surfaceable is True


def test_drops_revoked(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    store = MemoryStore(
        [
            _conclusion("active", "Active source."),
            _conclusion("revoked", "Revoked source.", is_revoked=True),
        ]
    )

    sources = retrieve_for_market(store, _market(), top_k=8)

    assert [source.source_id for source in sources] == ["active"]


def test_age_filter(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    old = datetime.now(timezone.utc) - timedelta(days=19 * 31)
    stale_store = MemoryStore(
        [_conclusion("old_not_load_bearing", "Old source.", created_at=old)]
    )
    load_bearing_store = MemoryStore(
        [
            _conclusion(
                "old_load_bearing",
                "Old source retained because it is load-bearing.",
                created_at=old,
                is_load_bearing=True,
            )
        ]
    )

    assert retrieve_for_market(stale_store, _market(), top_k=8) == []
    assert [
        source.source_id
        for source in retrieve_for_market(load_bearing_store, _market(), top_k=8)
    ] == ["old_load_bearing"]


def test_returns_empty_on_retriever_failure(monkeypatch) -> None:
    def fail_retrieve_for_event(_store, _event, *, top_k):
        assert top_k == 32
        raise RuntimeError("retriever failed")

    log = CapturingLog()
    monkeypatch.setattr(adapter, "retrieve_for_event", fail_retrieve_for_event)
    monkeypatch.setattr(adapter, "log", log)

    assert retrieve_for_market(MemoryStore([]), _market(), top_k=8) == []
    assert len(log.entries) == 1
    assert log.entries[0][0] == "forecasts.retrieval.error"
    assert log.entries[0][1]["market_id"] == "forecast_market_test"
    assert "retriever failed" in str(log.entries[0][1]["error"])


def test_top_k_respected(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    store = MemoryStore(
        [
            _conclusion(
                f"source_{i:02d}",
                f"High relevance source {i:02d}.",
                score=1.0 - i * 0.001,
            )
            for i in range(30)
        ]
    )

    sources = retrieve_for_market(store, _market(), top_k=8)

    assert len(sources) <= 8
    assert [source.source_id for source in sources] == [
        f"source_{i:02d}" for i in range(8)
    ]
