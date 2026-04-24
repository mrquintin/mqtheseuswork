"""Tests for noosphere.currents.relevance (prompt 03).

The retrieval adapter is a SHIM that raises NotImplementedError. Every test
here replaces it via monkeypatch on the relevance module's import site.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.currents.relevance import check_relevance
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.ids import make_event_id
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
)
from noosphere.store import Store


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_event(
    *,
    dedupe: str = "evt-rel",
    status: CurrentEventStatus = CurrentEventStatus.OBSERVED,
    embedding: list[float] | None = None,
) -> CurrentEvent:
    now = _now()
    return CurrentEvent(
        id=make_event_id(dedupe),
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text="a news item",
        dedupe_hash=dedupe,
        embedding=embedding if embedding is not None else [0.1, 0.2, 0.3, 0.4],
        topic_hint=None,
        status=status,
    )


def _patch_hits(
    monkeypatch: pytest.MonkeyPatch, hits: list[EventRetrievalHit]
) -> None:
    monkeypatch.setattr(
        "noosphere.currents.relevance.retrieve_for_event",
        lambda store, ev: list(hits),
    )


def _hit(score: float, sid: str = "c1") -> EventRetrievalHit:
    return EventRetrievalHit(
        source_kind="conclusion",
        source_id=sid,
        text="snippet",
        score=score,
    )


def test_abstains_when_no_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    ev = _make_event(dedupe="rel-none")
    store.add_current_event(ev)

    _patch_hits(monkeypatch, [])

    result = check_relevance(store, ev)

    assert result.passed is False
    assert result.reason == "no_sources_above_threshold"
    assert result.sources_found == 0
    assert result.top_score == 0.0

    got = store.get_current_event(ev.id)
    assert got is not None
    assert got.status == CurrentEventStatus.ABSTAINED
    assert got.status_reason == "no_sources_above_threshold"


def test_abstains_when_top_score_too_low(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    ev = _make_event(dedupe="rel-lowscore")
    store.add_current_event(ev)

    _patch_hits(
        monkeypatch,
        [_hit(0.49, "c1"), _hit(0.40, "c2"), _hit(0.30, "c3")],
    )

    result = check_relevance(store, ev)

    assert result.passed is False
    assert result.reason == "no_sources_above_threshold"
    assert result.sources_found == 3
    assert result.top_score == pytest.approx(0.49)

    got = store.get_current_event(ev.id)
    assert got is not None
    assert got.status == CurrentEventStatus.ABSTAINED


def test_abstains_when_too_few_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    ev = _make_event(dedupe="rel-fewsrc")
    store.add_current_event(ev)

    # One strong hit is not enough (MIN_SOURCES_FOR_OPINION == 2).
    _patch_hits(monkeypatch, [_hit(0.90, "c1")])

    result = check_relevance(store, ev)

    assert result.passed is False
    assert result.reason == "no_sources_above_threshold"
    assert result.sources_found == 1

    got = store.get_current_event(ev.id)
    assert got is not None
    assert got.status == CurrentEventStatus.ABSTAINED


def test_passes_when_sufficient_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    ev = _make_event(dedupe="rel-pass")
    store.add_current_event(ev)

    _patch_hits(monkeypatch, [_hit(0.70, "c1"), _hit(0.62, "c2")])

    result = check_relevance(store, ev)

    assert result.passed is True
    assert result.reason is None
    assert result.sources_found == 2
    assert result.top_score == pytest.approx(0.70)

    got = store.get_current_event(ev.id)
    assert got is not None
    # Must remain OBSERVED — only the opinion generator (later prompt) flips
    # the status to OPINED.
    assert got.status == CurrentEventStatus.OBSERVED


def test_relevance_skips_events_without_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()
    ev = _make_event(dedupe="rel-noemb", embedding=None)
    # embedding=None round-trips as None; bypass our default helper above
    # by constructing manually.
    ev = ev.model_copy(update={"embedding": None})
    store.add_current_event(ev)

    # retrieve_for_event must NOT be called — the shim raises. Do not patch;
    # if relevance tried to call it, this test would blow up.

    result = check_relevance(store, ev)
    assert result.passed is False
    assert result.reason == "skipped_no_embedding"
    assert result.sources_found == 0
    assert result.top_score == 0.0

    got = store.get_current_event(ev.id)
    assert got is not None
    # Status unchanged.
    assert got.status == CurrentEventStatus.OBSERVED
    assert got.status_reason is None


def test_relevance_skips_non_observed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Already SUPPRESSED events should not be re-evaluated."""
    store = _store()
    ev = _make_event(dedupe="rel-suppr", status=CurrentEventStatus.SUPPRESSED)
    store.add_current_event(ev)

    result = check_relevance(store, ev)
    assert result.passed is False
    assert result.reason is not None
    assert result.reason.startswith("skipped_status:")

    got = store.get_current_event(ev.id)
    assert got is not None
    assert got.status == CurrentEventStatus.SUPPRESSED
