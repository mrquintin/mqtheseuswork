from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from conftest import PIPELINE_EVENT_TEXT, PIPELINE_ORG_ID
from fakes.fake_anthropic_client import FakeAnthropicClient, opine_with_valid_citation
from fakes.fake_x_client import FakeTweet, FakeXClient
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.config import IngestorConfig
from noosphere.currents.enrich import enrich_event
from noosphere.currents.opinion_generator import OpinionOutcome, generate_opinion
from noosphere.currents.relevance import RelevanceDecision, check_relevance
from noosphere.currents.x_ingestor import ingest_once


@pytest.mark.asyncio
async def test_full_pipeline_opinion_is_published(
    seeded_noosphere,
    monkeypatch,
    tmp_path,
) -> None:
    del tmp_path
    fake_x = FakeXClient(
        [
            FakeTweet(
                id="1",
                text=PIPELINE_EVENT_TEXT,
                author_id="curator_1",
                author_handle="@curator_1",
                created_at="2026-04-29T12:00:00+00:00",
            )
        ]
    )
    monkeypatch.setattr("noosphere.currents.x_ingestor.make_client", lambda cfg: fake_x)
    fake_anthropic = FakeAnthropicClient(script=[opine_with_valid_citation])
    monkeypatch.setattr(
        "noosphere.currents.opinion_generator.make_client",
        lambda: fake_anthropic,
    )

    cfg = IngestorConfig(
        bearer_token="test-token",
        curated_accounts=["curator_1"],
        search_queries=[],
        organization_id=PIPELINE_ORG_ID,
        max_events_per_cycle=10,
    )
    ingest_report = await ingest_once(seeded_noosphere, cfg)
    assert len(ingest_report.new_event_ids) == 1
    eid = ingest_report.new_event_ids[0]

    enrich_event(seeded_noosphere, eid)
    assert check_relevance(seeded_noosphere, eid) == RelevanceDecision.OPINE

    budget = HourlyBudgetGuard(
        max_prompt_tokens=10_000_000,
        max_completion_tokens=10_000_000,
    )
    outcome = await generate_opinion(seeded_noosphere, eid, budget=budget)
    assert outcome is OpinionOutcome.PUBLISHED

    from current_events_api.main import app as api_app

    with TestClient(api_app) as client:
        resp = client.get("/v1/currents")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(it["id"] for it in items)
        assert any(it["event_id"] == eid for it in items)
        for forbidden in (
            "prompt_tokens",
            "completion_tokens",
            "client_fingerprint",
        ):
            assert forbidden not in items[0]
