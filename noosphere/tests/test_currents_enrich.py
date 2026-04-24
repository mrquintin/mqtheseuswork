"""Tests for noosphere.currents.enrich (prompt 03).

Embedding is never actually computed: `embed_text` and
`_load_topics_with_embeddings` are monkeypatched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from noosphere.currents import enrich as enrich_mod
from noosphere.currents.enrich import enrich_event
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
    dedupe: str,
    raw_text: str = "hello world",
    embedding=None,
    topic_hint=None,
    status: CurrentEventStatus = CurrentEventStatus.OBSERVED,
    captured_at: datetime | None = None,
) -> CurrentEvent:
    now = captured_at or _now()
    return CurrentEvent(
        id=make_event_id(dedupe),
        source=CurrentEventSource.X_POST,
        source_url=f"https://x.com/foo/status/{dedupe}",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text=raw_text,
        dedupe_hash=dedupe,
        embedding=embedding,
        topic_hint=topic_hint,
        status=status,
    )


def _patch_embed(monkeypatch: pytest.MonkeyPatch, vector: list[float]) -> None:
    monkeypatch.setattr(
        "noosphere.currents.enrich.embed_text",
        lambda text: list(vector),
    )


def _patch_topics(
    monkeypatch: pytest.MonkeyPatch,
    topics: list[tuple[str, list[float]]],
) -> None:
    monkeypatch.setattr(
        "noosphere.currents.enrich._load_topics_with_embeddings",
        lambda store: [(lbl, np.asarray(v, dtype=np.float32)) for lbl, v in topics],
    )


def test_enrich_writes_embedding_and_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    ev = _make_event(dedupe="evt-alpha", raw_text="markets move today")
    store.add_current_event(ev)

    event_vec = [1.0, 0.0, 0.0, 0.0]
    # Topic vector nearly identical to the event vector (cos ≈ 1 > 0.35).
    _patch_embed(monkeypatch, event_vec)
    _patch_topics(monkeypatch, [("capital_allocation", [0.99, 0.01, 0.0, 0.0])])

    result = enrich_event(store, ev)

    assert result.was_duplicate_of is None
    assert result.topic_hint == "capital_allocation"

    got = store.get_current_event(ev.id)
    assert got is not None
    assert got.embedding is not None
    assert len(got.embedding) == 4
    assert got.topic_hint == "capital_allocation"
    assert got.status == CurrentEventStatus.OBSERVED


def test_enrich_collapses_near_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    # A: already embedded.
    base = [1.0, 0.0, 0.0, 0.0]
    a = _make_event(
        dedupe="evt-A",
        raw_text="same news, phrasing one",
        embedding=base,
        topic_hint="ai_policy",
    )
    store.add_current_event(a)

    # B: to-be-enriched; its embedding is 0.99*base + tiny noise → cos ≈ 1.
    b = _make_event(dedupe="evt-B", raw_text="same news, phrasing two")
    store.add_current_event(b)

    near = [0.99, 0.001, 0.0, 0.0]
    _patch_embed(monkeypatch, near)
    # Topics shouldn't be consulted, but stub them out defensively.
    _patch_topics(monkeypatch, [])

    result = enrich_event(store, b)

    assert result.was_duplicate_of == a.id
    got_b = store.get_current_event(b.id)
    assert got_b is not None
    assert got_b.status == CurrentEventStatus.SUPPRESSED
    assert got_b.status_reason is not None
    assert got_b.status_reason.startswith("near_duplicate_of:")
    assert a.id in got_b.status_reason


def test_enrich_keeps_distinct_events_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    a = _make_event(
        dedupe="evt-A2",
        raw_text="topic one",
        embedding=[1.0, 0.0, 0.0, 0.0],
        topic_hint="",
    )
    store.add_current_event(a)

    b = _make_event(dedupe="evt-B2", raw_text="completely different topic")
    store.add_current_event(b)

    # Orthogonal → cosine = 0 < 0.92.
    _patch_embed(monkeypatch, [0.0, 1.0, 0.0, 0.0])
    _patch_topics(monkeypatch, [])

    result = enrich_event(store, b)
    assert result.was_duplicate_of is None

    got_a = store.get_current_event(a.id)
    got_b = store.get_current_event(b.id)
    assert got_a is not None and got_a.status == CurrentEventStatus.OBSERVED
    assert got_b is not None and got_b.status == CurrentEventStatus.OBSERVED
    assert got_b.embedding is not None


def test_topic_hint_none_when_no_topic_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()
    ev = _make_event(dedupe="evt-weak", raw_text="edge-case text")
    store.add_current_event(ev)

    # Event vector orthogonal to every candidate topic vector → cos = 0 < 0.35.
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0, 0.0])
    _patch_topics(
        monkeypatch,
        [
            ("unrelated_one", [0.0, 1.0, 0.0, 0.0]),
            ("unrelated_two", [0.0, 0.0, 1.0, 0.0]),
        ],
    )

    result = enrich_event(store, ev)

    assert result.was_duplicate_of is None
    assert result.topic_hint is None

    got = store.get_current_event(ev.id)
    assert got is not None
    # Store persists "" when topic_hint is None (per the signature), which
    # the Pydantic Optional field round-trips either as "" or None. Accept
    # both — the contract is "no meaningful topic assigned".
    assert got.topic_hint in (None, "")
    assert got.embedding is not None
    assert got.status == CurrentEventStatus.OBSERVED


def test_enrich_skips_already_embedded_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Idempotency: events arriving with an embedding short-circuit."""
    store = _store()
    ev = _make_event(
        dedupe="evt-preembedded",
        embedding=[0.1, 0.2, 0.3, 0.4],
        topic_hint="prior",
    )
    store.add_current_event(ev)

    # If enrich attempted to embed, this would blow up.
    def _boom(text: str) -> list[float]:
        raise AssertionError("embed_text should not be called for pre-embedded event")

    monkeypatch.setattr("noosphere.currents.enrich.embed_text", _boom)

    result = enrich_event(store, ev)
    assert result.topic_hint == "prior"
    assert result.was_duplicate_of is None


def test_enrich_ignores_events_outside_24h_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'duplicate' older than 24h must NOT cause suppression because
    list_current_event_ids(since=...) filters by source_captured_at.
    """
    store = _store()
    now = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)

    old = _make_event(
        dedupe="evt-old",
        embedding=[1.0, 0.0, 0.0, 0.0],
        captured_at=now - timedelta(hours=48),
    )
    store.add_current_event(old)

    fresh = _make_event(
        dedupe="evt-fresh",
        raw_text="fresh news",
        captured_at=now - timedelta(minutes=5),
    )
    store.add_current_event(fresh)

    _patch_embed(monkeypatch, [1.0, 0.0, 0.0, 0.0])  # matches `old`
    _patch_topics(monkeypatch, [])

    result = enrich_event(store, fresh, now=now)

    assert result.was_duplicate_of is None
    got_fresh = store.get_current_event(fresh.id)
    assert got_fresh is not None
    assert got_fresh.status == CurrentEventStatus.OBSERVED
