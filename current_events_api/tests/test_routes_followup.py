from __future__ import annotations

import json
from datetime import datetime, timedelta

from noosphere.currents.followup import FollowupAnswerChunk
from noosphere.models import FollowUpMessage, FollowUpRole, FollowUpSession

from current_events_api_tests_support import OPINION_ID, seed_opinion


def test_followup_post_streams_meta_tokens_citations_and_done(client, monkeypatch) -> None:
    store = client.app.state.store
    seed_opinion(store)
    from current_events_api.routes import followup as route_module

    async def fake_answer_followup(_store, opinion_id, session_id, question, *, budget):
        yield FollowupAnswerChunk(
            kind="meta",
            text=json.dumps({"opinion_id": opinion_id, "session_id": session_id}),
            citation=None,
        )
        yield FollowupAnswerChunk(kind="token", text=f"answer to {question}", citation=None)
        yield FollowupAnswerChunk(
            kind="citation",
            text=None,
            citation={"source_kind": "conclusion", "source_id": "source1"},
        )
        yield FollowupAnswerChunk(kind="done", text=None, citation=None)

    monkeypatch.setattr(route_module, "answer_followup", fake_answer_followup)

    response = client.post(
        f"/v1/currents/{OPINION_ID}/follow-up",
        headers={"x-client-id": "fingerprint-followup"},
        json={"question": "What follows?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: meta" in response.text
    assert "event: token" in response.text
    assert "answer to What follows?" in response.text
    assert "event: citation" in response.text
    assert "event: done" in response.text


def test_followup_post_returns_429_json_when_session_message_limit_hit(client, monkeypatch) -> None:
    store = client.app.state.store
    seed_opinion(store)
    session_id = store.add_followup_session(
        FollowUpSession(opinion_id=OPINION_ID, client_fingerprint="same")
    )
    now = datetime.now()
    for idx in range(8):
        store.add_followup_message(
            FollowUpMessage(
                session_id=session_id,
                role=FollowUpRole.USER,
                content=f"question {idx}",
                created_at=now - timedelta(minutes=idx + 3),
            )
        )
    from current_events_api.routes import followup as route_module

    async def should_not_run(*_args, **_kwargs):
        raise AssertionError("answer_followup should not run after rate limit")

    monkeypatch.setattr(route_module, "answer_followup", should_not_run)

    response = client.post(
        f"/v1/currents/{OPINION_ID}/follow-up",
        headers={"x-client-id": "same"},
        json={"question": "blocked?", "session_id": session_id},
    )

    assert response.status_code == 429
    assert response.json()["detail"]["reason"] == "session_message_limit"


def test_followup_messages_history_is_paginated_and_excludes_fingerprint(client) -> None:
    store = client.app.state.store
    seed_opinion(store)
    session_id = store.add_followup_session(
        FollowUpSession(opinion_id=OPINION_ID, client_fingerprint="private-fingerprint")
    )
    store.add_followup_message(
        FollowUpMessage(
            session_id=session_id,
            role=FollowUpRole.USER,
            content="question",
            created_at=datetime(2026, 4, 29, 12, 0, 0),
        )
    )
    store.add_followup_message(
        FollowUpMessage(
            session_id=session_id,
            role=FollowUpRole.ASSISTANT,
            content="answer",
            citations=[{"source_kind": "conclusion", "source_id": "source1"}],
            created_at=datetime(2026, 4, 29, 12, 0, 1),
        )
    )

    response = client.get(
        f"/v1/currents/{OPINION_ID}/follow-up/{session_id}/messages",
        params={"limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["role"] == "ASSISTANT"
    assert "client_fingerprint" not in json.dumps(payload)
    assert payload["next_before"] is not None
