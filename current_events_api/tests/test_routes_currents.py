from __future__ import annotations

from current_events_api_tests_support import (
    CONCLUSION_ID,
    OPINION_ID,
    SOURCE_TEXT,
    seed_opinion,
)

from noosphere.currents.status import write_status


def test_healthz_returns_ok(client) -> None:
    assert client.get("/healthz").json() == {"ok": True}


def test_currents_health_reports_config_status_and_recent_counts(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "test-secret")
    monkeypatch.setenv("CURRENTS_X_CURATED_ACCOUNTS", "111,222")
    monkeypatch.setenv("CURRENTS_X_SEARCH_QUERIES", "education,truth")
    write_status(
        {
            "cycle_id": "cycle_health_test",
            "started_at": "2026-04-30T12:34:56Z",
            "errors": [],
        }
    )
    seed_opinion(client.app.state.store)

    response = client.get("/v1/currents/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["x_bearer_present"] is True
    assert payload["curated_count"] == 2
    assert payload["search_count"] == 2
    assert payload["last_cycle_at"] == "2026-04-30T12:34:56Z"
    assert payload["events_last_24h"] == 1
    assert payload["opinions_last_24h"] == 1
    assert payload["disabled_reasons"] == []


def test_currents_health_reports_disabled_reasons(client, monkeypatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("CURRENTS_X_CURATED_ACCOUNTS", raising=False)
    monkeypatch.delenv("CURRENTS_X_SEARCH_QUERIES", raising=False)

    response = client.get("/v1/currents/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["x_bearer_present"] is False
    assert payload["curated_count"] == 0
    assert payload["search_count"] == 0
    assert payload["disabled_reasons"] == [
        "missing_x_bearer_token",
        "missing_x_sources",
    ]


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
    assert item["event"]["text"] == "A public event raises questions about compounding."
    assert item["event"]["url"] == "https://example.test/event"
    assert item["event"]["external_id"] == "external_currents_api"
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
