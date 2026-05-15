"""Equities retrieval adapter tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from noosphere.equities import retrieval_adapter as adapter
from noosphere.equities.retrieval_adapter import (
    PRINCIPLE_SCORE_BOOST,
    build_query_from_instrument,
    retrieve_for_instrument,
)
from noosphere.models import (
    Conclusion,
    EquityAssetClass,
    EquityInstrument,
    PrincipleKind,
)


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


def _instrument(
    *,
    symbol: str = "AAPL",
    name: str = "Apple Inc.",
    sector: str = "Consumer Electronics",
    asset_class: EquityAssetClass = EquityAssetClass.STOCK,
    recent_news_blurb: str | None = None,
) -> EquityInstrument:
    instrument = EquityInstrument(
        id=f"equity_instr_{symbol.lower()}",
        symbol=symbol,
        exchange="NASDAQ",
        asset_class=asset_class,
        name=name,
    )
    instrument.__dict__["sector"] = sector
    if recent_news_blurb is not None:
        instrument.__dict__["recent_news_blurb"] = recent_news_blurb
    return instrument


def _conclusion(
    conclusion_id: str,
    text: str,
    *,
    principle_kind: PrincipleKind | None = None,
    domain_of_applicability: str | None = None,
    visibility: str = "PUBLIC",
    surfaceable: bool | None = None,
    is_revoked: bool = False,
    score: float = 0.85,
    created_at: datetime | None = None,
) -> Conclusion:
    conclusion = Conclusion(
        id=conclusion_id,
        text=text,
        created_at=created_at or datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        updated_at=created_at or datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        principle_kind=principle_kind,
        domain_of_applicability=domain_of_applicability,
    )
    conclusion.__dict__["visibility"] = visibility
    if surfaceable is not None:
        conclusion.__dict__["surfaceable"] = surfaceable
    if is_revoked:
        conclusion.__dict__["is_revoked"] = True
    conclusion.__dict__["_retrieval_score"] = score
    return conclusion


def _patch_retrieval(monkeypatch) -> None:
    def fake_retrieve_for_event(store: MemoryStore, _event, top_k: int):
        return [
            SimpleNamespace(
                source_kind="conclusion",
                source_id=conclusion.id,
                text=conclusion.text,
                score=conclusion.__dict__.get("_retrieval_score", 0.85),
            )
            for conclusion in store.list_conclusions()[:top_k]
        ]

    monkeypatch.setattr(adapter, "retrieve_for_event", fake_retrieve_for_event)


# ── tests ────────────────────────────────────────────────────────────────────


def test_build_query_includes_symbol_name_sector_and_blurb() -> None:
    instrument = _instrument(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Consumer Electronics",
        recent_news_blurb="Q1 services revenue beat consensus.",
    )
    query = build_query_from_instrument(instrument)
    assert "AAPL Apple Inc." in query
    assert "Sector: Consumer Electronics" in query
    assert "Asset class: STOCK" in query
    assert "Recent: Q1 services revenue beat consensus." in query


def test_build_query_omits_optional_fields() -> None:
    instrument = EquityInstrument(
        id="i1",
        symbol="SPY",
        exchange="NYSE",
        asset_class=EquityAssetClass.ETF,
        name="SPDR S&P 500 ETF Trust",
    )
    # No sector or recent_news_blurb attached.
    query = build_query_from_instrument(instrument)
    assert "SPY SPDR S&P 500 ETF Trust" in query
    assert "Sector:" not in query
    assert "Recent:" not in query


def test_principle_score_boost_outranks_plain_conclusion(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    instrument = _instrument()
    store = MemoryStore(
        [
            _conclusion(
                "plain",
                "A plain conclusion.",
                score=0.80,
            ),
            _conclusion(
                "principle",
                "A principle about consumer electronics.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
                score=0.74,
            ),
        ]
    )

    sources = retrieve_for_instrument(store, instrument, top_k=4)

    by_id = {source.source_id: source for source in sources}
    assert "principle" in by_id
    assert by_id["principle"].source_type == "PRINCIPLE"
    assert by_id["plain"].source_type == "CONCLUSION"
    # Principle gets +0.10 boost so it ends up ranked above the plain conclusion.
    assert by_id["principle"].relevance >= by_id["plain"].relevance
    assert abs(by_id["principle"].relevance - (0.74 + PRINCIPLE_SCORE_BOOST)) < 1e-6


def test_filters_non_surfaceable_founder_principle(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    store = MemoryStore(
        [
            _conclusion(
                "public_principle",
                "Public principle.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
            ),
            _conclusion(
                "founder_private_principle",
                "Founder-private principle that must not surface.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
                visibility="FOUNDER",
                surfaceable=False,
            ),
            _conclusion(
                "founder_public_principle",
                "Founder principle deliberately cleared for public use.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
                visibility="FOUNDER",
                surfaceable=True,
            ),
        ]
    )

    sources = retrieve_for_instrument(store, _instrument(), top_k=8)

    surfaced = {source.source_id for source in sources}
    assert "public_principle" in surfaced
    assert "founder_public_principle" in surfaced
    assert "founder_private_principle" not in surfaced


def test_domain_mismatch_drops_principle(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    store = MemoryStore(
        [
            _conclusion(
                "principle_match",
                "Principle that matches the sector.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics hardware",
            ),
            _conclusion(
                "principle_off_domain",
                "Principle that belongs to an unrelated domain.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="agricultural commodity futures",
            ),
        ]
    )

    sources = retrieve_for_instrument(store, _instrument(), top_k=8)

    ids = {source.source_id for source in sources}
    assert "principle_match" in ids
    assert "principle_off_domain" not in ids


def test_legacy_principle_without_domain_passes(monkeypatch) -> None:
    """Founder-approved principles created before prompt 56 have no domain.
    Filtering them out would silently drop load-bearing knowledge, so the
    adapter treats an empty domain as universal."""

    _patch_retrieval(monkeypatch)
    store = MemoryStore(
        [
            _conclusion(
                "legacy_principle",
                "Legacy principle text.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability=None,
            )
        ]
    )

    sources = retrieve_for_instrument(store, _instrument(), top_k=8)
    assert any(s.source_id == "legacy_principle" for s in sources)


def test_drops_revoked_principle(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    store = MemoryStore(
        [
            _conclusion(
                "active",
                "Active principle.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
            ),
            _conclusion(
                "revoked",
                "Revoked principle.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
                is_revoked=True,
            ),
        ]
    )

    sources = retrieve_for_instrument(store, _instrument(), top_k=8)
    assert {s.source_id for s in sources} == {"active"}


def test_age_filter_drops_stale_sources(monkeypatch) -> None:
    _patch_retrieval(monkeypatch)
    old = datetime.now(timezone.utc) - timedelta(days=19 * 31)
    store = MemoryStore(
        [
            _conclusion(
                "ancient",
                "Stale source.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
                created_at=old,
            ),
            _conclusion(
                "recent",
                "Recent source.",
                principle_kind=PrincipleKind.RULE,
                domain_of_applicability="consumer electronics",
            ),
        ]
    )

    sources = retrieve_for_instrument(store, _instrument(), top_k=8)
    assert {s.source_id for s in sources} == {"recent"}


def test_returns_empty_on_retrieval_error(monkeypatch) -> None:
    def boom(*_a, **_kw):
        raise RuntimeError("retrieval blew up")

    monkeypatch.setattr(adapter, "retrieve_for_event", boom)
    store = MemoryStore([])

    sources = retrieve_for_instrument(store, _instrument(), top_k=8)
    assert sources == []
