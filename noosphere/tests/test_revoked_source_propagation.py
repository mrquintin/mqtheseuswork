from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_EVENTS_API_SRC = REPO_ROOT / "current_events_api"
if str(CURRENT_EVENTS_API_SRC) not in sys.path:
    sys.path.insert(0, str(CURRENT_EVENTS_API_SRC))


def test_revoked_source_is_reflected_on_public_detail(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'revoked.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CURRENTS_ORG_ID", raising=False)

    from current_events_api.main import app

    with TestClient(app) as client:
        store = client.app.state.store
        conclusion = Conclusion(
            id="conclusion_revoked",
            text="Theseus says durable compounding depends on disciplined evidence.",
        )
        store.put_conclusion(conclusion)
        event_id = store.add_current_event(
            CurrentEvent(
                id="event_revoked",
                organization_id="org_revoked",
                source=CurrentEventSource.MANUAL,
                external_id="event_revoked",
                text="A headline about compounding discipline.",
                observed_at=datetime(2026, 4, 29, 12, 0, 0),
                dedupe_hash="event_revoked_hash",
            )
        )
        opinion_id = store.add_event_opinion(
            EventOpinion(
                id="opinion_revoked",
                organization_id="org_revoked",
                event_id=event_id,
                stance=OpinionStance.COMPLICATES,
                confidence=0.71,
                headline="Compounding thesis",
                body_markdown="The opinion is grounded in one source.",
                uncertainty_notes=[],
                topic_hint="markets",
                model_name="claude-haiku-4-5-test",
            ),
            [
                OpinionCitation(
                    opinion_id="",
                    source_kind="conclusion",
                    conclusion_id=conclusion.id,
                    quoted_span="durable compounding",
                    retrieval_score=0.91,
                )
            ],
        )
        store.revoke_citations_for_source(
            "conclusion",
            conclusion.id,
            "source retired",
        )

        response = client.get(f"/v1/currents/{opinion_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["revoked_sources_count"] == 1
    assert payload["citations"][0]["source_id"] == conclusion.id
    assert payload["citations"][0]["is_revoked"] is True
