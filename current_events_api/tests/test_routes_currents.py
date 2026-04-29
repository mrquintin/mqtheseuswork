from __future__ import annotations

from current_events_api_tests_support import (
    CONCLUSION_ID,
    OPINION_ID,
    SOURCE_TEXT,
    seed_opinion,
)


def test_healthz_returns_ok(client) -> None:
    assert client.get("/healthz").json() == {"ok": True}


def test_list_currents_strips_internal_fields_and_keeps_revoked_count(client) -> None:
    store = client.app.state.store
    seed_opinion(store)
    store.revoke_citations_for_source("conclusion", CONCLUSION_ID, "source retired")

    response = client.get("/v1/currents", params={"limit": 10})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == OPINION_ID
    assert item["stance"] == "COMPLICATES"
    assert item["event"]["author_handle"] == "theseus"
    assert item["citations"][0]["source_id"] == CONCLUSION_ID
    assert item["revoked_sources_count"] == 1
    assert "prompt_tokens" not in item
    assert "completion_tokens" not in item
    assert "client_fingerprint" not in item
    assert "revoked_reason" not in item
    assert "revoked_reason" not in item["citations"][0]


def test_get_current_sources_returns_full_source_detail(client) -> None:
    store = client.app.state.store
    seed_opinion(store)
    store.revoke_citations_for_source("conclusion", CONCLUSION_ID, "source retired")

    response = client.get(f"/v1/currents/{OPINION_ID}/sources")

    assert response.status_code == 200
    sources = response.json()
    assert sources == [
        {
            "id": sources[0]["id"],
            "opinion_id": OPINION_ID,
            "source_kind": "conclusion",
            "source_id": CONCLUSION_ID,
            "source_text": SOURCE_TEXT,
            "quoted_span": "durable compounding",
            "retrieval_score": 0.91,
            "is_revoked": True,
            "revoked_reason": "source retired",
            "canonical_path": f"/c/{CONCLUSION_ID}",
        }
    ]


def test_list_currents_filters_topic_and_stance(client) -> None:
    store = client.app.state.store
    seed_opinion(store)

    kept = client.get(
        "/v1/currents",
        params={"topic": "markets", "stance": "COMPLICATES", "limit": 10},
    ).json()["items"]
    dropped = client.get(
        "/v1/currents",
        params={"topic": "other", "stance": "COMPLICATES", "limit": 10},
    ).json()["items"]

    assert [item["id"] for item in kept] == [OPINION_ID]
    assert dropped == []
