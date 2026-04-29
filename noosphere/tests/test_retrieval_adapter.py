"""Currents retrieval adapter tests."""

from __future__ import annotations

from datetime import date, datetime
from math import sqrt

import numpy as np

from noosphere.currents import enrich
from noosphere.currents.retrieval_adapter import DEFAULT_TOP_K, retrieve_for_event
from noosphere.models import (
    Claim,
    ClaimOrigin,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    Speaker,
)
from noosphere.store import Store


ORG_ID = "org_retrieval_adapter"


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _event(event_id: str, text: str) -> CurrentEvent:
    return CurrentEvent(
        id=event_id,
        organization_id=ORG_ID,
        source=CurrentEventSource.MANUAL,
        external_id=event_id,
        text=text,
        observed_at=datetime(2026, 4, 29, 12, 0, 0),
        topic_hint="markets",
        dedupe_hash=f"hash_{event_id}",
    )


def _claim(
    claim_id: str,
    text: str,
    origin: ClaimOrigin,
    embedding: list[float],
) -> Claim:
    return Claim(
        id=claim_id,
        text=text,
        speaker=Speaker(name="Ada"),
        episode_id="episode_retrieval_adapter",
        episode_date=date(2026, 4, 29),
        claim_origin=origin,
        embedding=embedding,
    )


def _patch_embeddings(monkeypatch, mapping: dict[str, list[float]]) -> None:
    def fake_embed(text: str) -> np.ndarray:
        if text not in mapping:
            raise AssertionError(f"missing test embedding for {text!r}")
        return np.asarray(mapping[text], dtype=float)

    monkeypatch.setattr(enrich, "embed_text", fake_embed)


def test_default_top_k_matches_currents_adapter_contract() -> None:
    assert DEFAULT_TOP_K == 8


def test_event_retrieval_returns_conclusion_and_allowed_claim(monkeypatch) -> None:
    st = _store()
    conclusion = Conclusion(
        id="conclusion_inquiry_not_credentialing",
        text="Inquiry is not credentialing.",
    )
    founder_claim = _claim(
        "claim_founder_narrative_pricing",
        "Narrative pricing drives early markets before fundamentals are legible.",
        ClaimOrigin.FOUNDER,
        [0.98, sqrt(1.0 - 0.98**2)],
    )
    external_claim = _claim(
        "claim_external_credentialing",
        "External analysts praise credentialing as the right filter.",
        ClaimOrigin.EXTERNAL,
        [0.99, sqrt(1.0 - 0.99**2)],
    )
    adversarial_claim = _claim(
        "claim_adversarial_narrative",
        "An adversarial objection says narrative pricing is empty theatrics.",
        ClaimOrigin.ADVERSARIAL,
        [0.97, sqrt(1.0 - 0.97**2)],
    )
    st.put_conclusion(conclusion)
    for claim in (founder_claim, external_claim, adversarial_claim):
        st.put_claim(claim)

    event = _event(
        "event_narrative_pricing",
        "Narrative pricing is repricing an early market.",
    )
    _patch_embeddings(
        monkeypatch,
        {
            event.text: [1.0, 0.0],
            conclusion.text: [0.6, 0.8],
        },
    )

    hits = retrieve_for_event(st, event, top_k=4)

    by_id = {hit.source_id: hit for hit in hits}
    assert set(by_id) == {
        "claim_founder_narrative_pricing",
        "conclusion_inquiry_not_credentialing",
    }
    assert by_id["claim_founder_narrative_pricing"].source_kind == "claim"
    assert by_id["claim_founder_narrative_pricing"].origin == "FOUNDER"
    assert by_id["conclusion_inquiry_not_credentialing"].source_kind == "conclusion"
    assert by_id["conclusion_inquiry_not_credentialing"].origin is None


def test_event_retrieval_filters_claim_subsumed_by_conclusion(monkeypatch) -> None:
    st = _store()
    conclusion = Conclusion(
        id="conclusion_inquiry_not_credentialing",
        text="Inquiry is not credentialing.",
    )
    near_duplicate_claim = _claim(
        "claim_founder_inquiry_duplicate",
        "Inquiry is not credentialing; it is disciplined questioning.",
        ClaimOrigin.FOUNDER,
        [0.99, sqrt(1.0 - 0.99**2)],
    )
    external_claim = _claim(
        "claim_external_credentialing",
        "External analysts praise credentialing as the right filter.",
        ClaimOrigin.EXTERNAL,
        [0.98, sqrt(1.0 - 0.98**2)],
    )
    adversarial_claim = _claim(
        "claim_adversarial_inquiry",
        "An adversary argues inquiry should be replaced by credentialing.",
        ClaimOrigin.ADVERSARIAL,
        [0.97, sqrt(1.0 - 0.97**2)],
    )
    st.put_conclusion(conclusion)
    for claim in (near_duplicate_claim, external_claim, adversarial_claim):
        st.put_claim(claim)

    event = _event(
        "event_inquiry_not_credentialing",
        "Inquiry is not credentialing in founder judgment.",
    )
    _patch_embeddings(
        monkeypatch,
        {
            event.text: [1.0, 0.0],
            conclusion.text: [1.0, 0.0],
        },
    )

    hits = retrieve_for_event(st, event, top_k=4)

    assert [(hit.source_kind, hit.source_id) for hit in hits] == [
        ("conclusion", "conclusion_inquiry_not_credentialing")
    ]
