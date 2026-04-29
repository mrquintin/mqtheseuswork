from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from fakes.fake_anthropic_client import FakeAnthropicClient
from noosphere.currents import followup as subject
from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    FollowUpSession,
    OpinionCitation,
    OpinionStance,
)
from noosphere.store import Store


ORG_ID = "org_followup_fresh"
OPINION_ID = "opinion_followup_fresh"
SOURCE_A = "Conclusion A says durable compounding depends on disciplined evidence."
SOURCE_B = "Conclusion B says public deployment must be independently retrieved."


@dataclass(frozen=True)
class Hit:
    source_kind: str
    source_id: str
    text: str
    score: float
    topic_hint: str | None = None
    origin: str | None = None


class NoopBudget:
    def authorize(self, est_prompt: int, est_completion: int) -> None:
        return None

    def charge(self, prompt: int, completion: int) -> None:
        return None


async def _collect(iterator) -> list[subject.FollowupAnswerChunk]:
    return [chunk async for chunk in iterator]


def test_followup_retrieves_again_for_the_question(monkeypatch) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    conclusion_a = Conclusion(id="conclusion_followup_a", text=SOURCE_A)
    conclusion_b = Conclusion(id="conclusion_followup_b", text=SOURCE_B)
    store.put_conclusion(conclusion_a)
    store.put_conclusion(conclusion_b)
    event_id = store.add_current_event(
        CurrentEvent(
            id="event_followup_fresh",
            organization_id=ORG_ID,
            source=CurrentEventSource.MANUAL,
            external_id="event_followup_fresh",
            text="A deployment event.",
            observed_at=datetime(2026, 4, 29, 12, 0, 0),
            dedupe_hash="event_followup_fresh_hash",
        )
    )
    store.add_event_opinion(
        EventOpinion(
            id=OPINION_ID,
            organization_id=ORG_ID,
            event_id=event_id,
            stance=OpinionStance.COMPLICATES,
            confidence=0.71,
            headline="Deployment complicates the original view",
            body_markdown="The original opinion cites Conclusion A.",
            uncertainty_notes=[],
            topic_hint="deployment",
            model_name="claude-haiku-4-5-test",
        ),
        [
            OpinionCitation(
                opinion_id="",
                source_kind="conclusion",
                conclusion_id=conclusion_a.id,
                quoted_span="durable compounding",
                retrieval_score=0.91,
            )
        ],
    )
    session_id = store.add_followup_session(
        FollowUpSession(opinion_id=OPINION_ID, client_fingerprint="fresh")
    )
    retrieved_questions: list[str] = []
    hit_b = Hit("conclusion", conclusion_b.id, SOURCE_B, 0.94)
    fake_llm = FakeAnthropicClient(
        script=[
            {
                "answer_markdown": "The deployment source is the relevant one.",
                "citations": [
                    {
                        "source_kind": "conclusion",
                        "source_id": conclusion_b.id,
                        "quoted_span": "public deployment must be independently retrieved",
                    }
                ],
            }
        ]
    )

    def fake_retrieve(_store, question_event, *, top_k: int) -> list[Hit]:
        del top_k
        retrieved_questions.append(question_event.text)
        return [hit_b]

    monkeypatch.setattr(subject, "retrieve_for_event", fake_retrieve)
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    chunks = asyncio.run(
        _collect(
            subject.answer_followup(
                store,
                OPINION_ID,
                session_id,
                "What does the deployment source imply?",
                budget=NoopBudget(),
            )
        )
    )

    assert retrieved_questions == ["What does the deployment source imply?"]
    assembled_prompt = fake_llm.calls[0]["user"]
    assert "source_id: conclusion_followup_b" in assembled_prompt
    assert SOURCE_B in assembled_prompt
    assert any(chunk.kind == "citation" for chunk in chunks)
