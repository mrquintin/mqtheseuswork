"""Currents embedding enrichment and relevance gate tests."""

from __future__ import annotations

from datetime import datetime
from math import sqrt

import numpy as np

from noosphere.currents import enrich, relevance
from noosphere.currents.relevance import RelevanceDecision
from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    Topic,
)
from noosphere.store import Store


ORG_ID = "org_enrich_relevance"


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _event(event_id: str, text: str, dedupe_hash: str) -> CurrentEvent:
    return CurrentEvent(
        id=event_id,
        organization_id=ORG_ID,
        source=CurrentEventSource.MANUAL,
        external_id=event_id,
        text=text,
        observed_at=datetime.now(),
        dedupe_hash=dedupe_hash,
    )


def _patch_embeddings(monkeypatch, mapping: dict[str, list[float]]) -> None:
    def fake_embed(text: str) -> np.ndarray:
        return np.asarray(mapping[text], dtype=float)

    monkeypatch.setattr(enrich, "embed_text", fake_embed)
    monkeypatch.setattr(relevance, "embed_text", fake_embed)


def test_enrich_flags_second_event_when_cosine_is_095(monkeypatch) -> None:
    st = _store()
    st.put_topic_cluster(
        Topic(id="topic_rates", label="Rates"),
        centroid=[1.0, 0.0],
        params_hash="test",
    )
    st.add_current_event(_event("event_a", "fed cuts rates", "hash_a"))
    st.add_current_event(_event("event_b", "fomc quarter point cut", "hash_b"))
    _patch_embeddings(
        monkeypatch,
        {
            "fed cuts rates": [1.0, 0.0],
            "fomc quarter point cut": [0.95, sqrt(1.0 - 0.95**2)],
        },
    )

    first = enrich.enrich_event(st, "event_a")
    second = enrich.enrich_event(st, "event_b")

    loaded_first = st.get_current_event("event_a")
    loaded_second = st.get_current_event("event_b")
    assert first.is_near_duplicate is False
    assert second.is_near_duplicate is True
    assert second.topic_id == "topic_rates"
    assert loaded_first is not None
    assert loaded_first.status == CurrentEventStatus.ENRICHED
    assert loaded_second is not None
    assert loaded_second.is_near_duplicate is True
    assert loaded_second.status == CurrentEventStatus.REVOKED
    assert loaded_second.topic_hint == "topic_rates"


def test_enrich_does_not_flag_events_when_cosine_is_05(monkeypatch) -> None:
    st = _store()
    st.add_current_event(_event("event_a", "rates decision", "hash_a"))
    st.add_current_event(_event("event_b", "chip supply news", "hash_b"))
    _patch_embeddings(
        monkeypatch,
        {
            "rates decision": [1.0, 0.0],
            "chip supply news": [0.5, sqrt(1.0 - 0.5**2)],
        },
    )

    first = enrich.enrich_event(st, "event_a")
    second = enrich.enrich_event(st, "event_b")

    loaded_first = st.get_current_event("event_a")
    loaded_second = st.get_current_event("event_b")
    assert first.is_near_duplicate is False
    assert second.is_near_duplicate is False
    assert loaded_first is not None
    assert loaded_first.status == CurrentEventStatus.ENRICHED
    assert loaded_second is not None
    assert loaded_second.is_near_duplicate is False
    assert loaded_second.status == CurrentEventStatus.ENRICHED


def test_relevance_abstains_when_event_is_orthogonal_to_seeded_conclusion(
    monkeypatch,
) -> None:
    st = _store()
    st.put_conclusion(
        Conclusion(id="conclusion_unrelated", text="Durable compounding matters.")
    )
    st.add_current_event(
        _event("event_orthogonal", "A short-term regulatory headline.", "hash_o")
    )
    _patch_embeddings(
        monkeypatch,
        {
            "A short-term regulatory headline.": [0.0, 1.0],
            "Durable compounding matters.": [1.0, 0.0],
        },
    )

    decision = relevance.check_relevance(st, "event_orthogonal")

    loaded = st.get_current_event("event_orthogonal")
    assert decision == RelevanceDecision.ABSTAIN_INSUFFICIENT_SOURCES
    assert loaded is not None
    assert loaded.status == CurrentEventStatus.ABSTAINED


def test_relevance_opines_when_two_conclusions_clear_threshold(monkeypatch) -> None:
    st = _store()
    st.put_conclusion(
        Conclusion(id="conclusion_one", text="Rate cuts loosen financial conditions.")
    )
    st.put_conclusion(
        Conclusion(id="conclusion_two", text="Policy easing changes discount rates.")
    )
    st.put_conclusion(
        Conclusion(
            id="conclusion_three",
            text="Supply chains depend on inventory buffers.",
        )
    )
    st.add_current_event(
        _event("event_relevant", "The Fed cut interest rates.", "hash_r")
    )
    _patch_embeddings(
        monkeypatch,
        {
            "The Fed cut interest rates.": [1.0, 0.0],
            "Rate cuts loosen financial conditions.": [0.95, sqrt(1.0 - 0.95**2)],
            "Policy easing changes discount rates.": [0.8, 0.6],
            "Supply chains depend on inventory buffers.": [0.0, 1.0],
        },
    )

    decision = relevance.check_relevance(st, "event_relevant")

    assert decision == RelevanceDecision.OPINE
