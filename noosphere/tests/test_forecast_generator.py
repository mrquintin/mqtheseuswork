from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import sqrt
from typing import Any

import pytest

from noosphere.currents._llm_client import LLMResponse
from noosphere.currents.budget import BudgetExhausted
from noosphere.forecasts import budget as forecast_budget
from noosphere.forecasts import forecast_generator as subject
from noosphere.forecasts.forecast_generator import ForecastOutcome
from noosphere.forecasts.retrieval_adapter import RetrievedSource
from noosphere.models import (
    ForecastMarket,
    ForecastMarketStatus,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastSource,
)
from noosphere.store import Store


ORG_ID = "org_forecast_generator"
SOURCE_A_TEXT = "The bill sponsorship has broadened after committee negotiations."
SOURCE_B_TEXT = "Committee leaders scheduled a markup for the policy bill next week."
SOURCE_C_TEXT = "Opponents still argue the floor calendar remains crowded."


@dataclass
class RecordingBudget:
    authorizes: list[tuple[int, int]]
    charges: list[tuple[int, int]]

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        self.authorizes.append((est_prompt, est_completion))

    def charge(self, prompt: int, completion: int) -> None:
        self.charges.append((prompt, completion))


class FakeLLMClient:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if not self.script:
            raise AssertionError("no scripted forecast response left")
        item = self.script.pop(0)
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(
            text=json.dumps(item),
            prompt_tokens=int(item.get("_prompt_tokens", 240)),
            completion_tokens=int(item.get("_completion_tokens", 90)),
            model=str(item.get("_model", "claude-haiku-4-5-test")),
        )


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _market(
    *,
    market_id: str = "forecast_market_generator",
    close_delta: timedelta = timedelta(days=7),
    title: str = "Will the policy bill pass before June?",
    status: ForecastMarketStatus = ForecastMarketStatus.OPEN,
) -> ForecastMarket:
    now = datetime.now(timezone.utc)
    return ForecastMarket(
        id=market_id,
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id=market_id,
        title=title,
        description="A public binary market on whether the policy bill passes.",
        resolution_criteria="Resolves YES if the bill passes before June 1.",
        category="policy",
        current_yes_price=Decimal("0.410000"),
        close_time=now + close_delta,
        status=status,
        raw_payload={"fixture": True},
    )


def _sources() -> list[RetrievedSource]:
    return [
        RetrievedSource(
            source_type="CONCLUSION",
            source_id="conclusion_policy_a",
            text=SOURCE_A_TEXT,
            relevance=0.94,
            surfaceable=True,
            visibility="PUBLIC",
            metadata={},
        ),
        RetrievedSource(
            source_type="CLAIM",
            source_id="claim_policy_b",
            text=SOURCE_B_TEXT,
            relevance=0.89,
            surfaceable=True,
            visibility="PUBLIC",
            metadata={},
        ),
        RetrievedSource(
            source_type="CONCLUSION",
            source_id="conclusion_policy_c",
            text=SOURCE_C_TEXT,
            relevance=0.71,
            surfaceable=True,
            visibility="PUBLIC",
            metadata={},
        ),
    ]


def _valid_payload() -> dict[str, Any]:
    return {
        "probability_yes": 0.64,
        "confidence_low": 0.52,
        "confidence_high": 0.74,
        "headline": "Sources put passage modestly above even odds",
        "reasoning_markdown": (
            "conclusion_policy_a shows legislative support has widened, while "
            "claim_policy_b adds timing evidence."
        ),
        "uncertainty_notes": "The floor calendar remains the main unresolved risk.",
        "topic_hint": "policy",
        "citations": [
            {
                "source_type": "CONCLUSION",
                "source_id": "conclusion_policy_a",
                "quoted_span": "bill sponsorship has broadened",
                "support_label": "DIRECT",
            },
            {
                "source_type": "CLAIM",
                "source_id": "claim_policy_b",
                "quoted_span": "scheduled a markup",
                "support_label": "INDIRECT",
            },
        ],
    }


def _seed_market(store: Store, market: ForecastMarket | None = None) -> ForecastMarket:
    market = market or _market()
    store.put_forecast_market(market)
    return market


def _predictions(store: Store) -> list[ForecastPrediction]:
    return store.list_recent_forecast_predictions(since=datetime(1970, 1, 1), limit=20)


def test_publishes_with_valid_citations(monkeypatch) -> None:
    store = _store()
    market = _seed_market(store)
    fake_llm = FakeLLMClient([_valid_payload()])
    budget = RecordingBudget(authorizes=[], charges=[])
    monkeypatch.setattr(subject, "retrieve_for_market", lambda *_args, **_kwargs: _sources())
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(subject.generate_forecast(store, market.id, budget=budget))

    assert outcome == ForecastOutcome.PUBLISHED
    predictions = _predictions(store)
    assert len(predictions) == 1
    prediction = predictions[0]
    assert prediction.status == ForecastPredictionStatus.PUBLISHED
    assert prediction.probability_yes == Decimal("0.640000")
    citations = store.list_forecast_citations(prediction.id)
    assert len(citations) == 2
    assert {citation.source_id for citation in citations} == {
        "conclusion_policy_a",
        "claim_policy_b",
    }
    assert budget.charges == [(240, 90)]
    assert subject.PROMPT_SEPARATOR_BEGIN in fake_llm.calls[0]["user"]
    assert subject.PROMPT_SEPARATOR_END in fake_llm.calls[0]["user"]


def test_abstains_on_insufficient_sources(monkeypatch) -> None:
    store = _store()
    market = _seed_market(store)
    fake_llm = FakeLLMClient([_valid_payload()])
    monkeypatch.setattr(subject, "retrieve_for_market", lambda *_args, **_kwargs: _sources()[:1])
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_forecast(
            store,
            market.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
        )
    )

    assert outcome == ForecastOutcome.ABSTAINED_INSUFFICIENT_SOURCES
    assert len(fake_llm.calls) == 0
    assert _predictions(store) == []


def test_abstains_on_near_duplicate(monkeypatch) -> None:
    store = _store()
    market = _seed_market(
        store,
        _market(title="Policy bill passage is increasingly likely"),
    )
    store.put_forecast_prediction(
        ForecastPrediction(
            market_id=market.id,
            organization_id=ORG_ID,
            probability_yes=Decimal("0.620000"),
            confidence_low=Decimal("0.520000"),
            confidence_high=Decimal("0.710000"),
            headline="Policy bill passage is increasingly likely after committee action",
            reasoning="seed",
            status=ForecastPredictionStatus.PUBLISHED,
            topic_hint="policy",
            model_name="fixture",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
    )
    fake_llm = FakeLLMClient([_valid_payload()])
    mapping = {
        market.title: [1.0, 0.0],
        "Policy bill passage is increasingly likely after committee action": [
            0.95,
            sqrt(1.0 - 0.95**2),
        ],
    }
    monkeypatch.setattr(subject, "retrieve_for_market", lambda *_args, **_kwargs: _sources())
    monkeypatch.setattr(subject, "embed_text", lambda text: mapping[text])
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_forecast(
            store,
            market.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
        )
    )

    assert outcome == ForecastOutcome.ABSTAINED_NEAR_DUPLICATE
    assert len(fake_llm.calls) == 0


def test_abstains_on_market_expired(monkeypatch) -> None:
    store = _store()
    market = _seed_market(store, _market(close_delta=timedelta(minutes=30)))
    monkeypatch.setattr(
        subject,
        "make_client",
        lambda: pytest.fail("LLM must not be called for expired markets"),
    )

    outcome = asyncio.run(
        subject.generate_forecast(
            store,
            market.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
        )
    )

    assert outcome == ForecastOutcome.ABSTAINED_MARKET_EXPIRED
    assert _predictions(store) == []


def test_abstains_on_citation_fabrication(monkeypatch) -> None:
    store = _store()
    market = _seed_market(store)
    invalid = _valid_payload()
    invalid["citations"] = [
        {
            "source_type": "CONCLUSION",
            "source_id": "conclusion_policy_a",
            "quoted_span": "not present in the source",
            "support_label": "DIRECT",
        }
    ]
    fake_llm = FakeLLMClient([invalid, invalid])
    monkeypatch.setattr(subject, "retrieve_for_market", lambda *_args, **_kwargs: _sources())
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_forecast(
            store,
            market.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
        )
    )

    assert outcome == ForecastOutcome.ABSTAINED_CITATION_FABRICATION
    assert len(fake_llm.calls) == 2
    assert "failed exact citation validation" in fake_llm.calls[1]["system"]
    assert _predictions(store) == []


def test_abstains_on_budget_exhausted(monkeypatch) -> None:
    store = _store()
    market = _seed_market(store)
    fake_llm = FakeLLMClient([_valid_payload()])
    budget = forecast_budget.HourlyBudgetGuard(
        max_prompt_tokens=100_000,
        max_completion_tokens=100_000,
    )
    budget.charge(86_000, 96_500)
    monkeypatch.setattr(subject, "retrieve_for_market", lambda *_args, **_kwargs: _sources())
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(subject.generate_forecast(store, market.id, budget=budget))

    assert outcome == ForecastOutcome.ABSTAINED_BUDGET
    assert len(fake_llm.calls) == 0
    assert _predictions(store) == []


def test_corrective_retry_on_invalid_probability(monkeypatch) -> None:
    store = _store()
    market = _seed_market(store)
    invalid = _valid_payload()
    invalid["probability_yes"] = 0.86
    invalid["confidence_high"] = 0.74
    fake_llm = FakeLLMClient([invalid, _valid_payload()])
    monkeypatch.setattr(subject, "retrieve_for_market", lambda *_args, **_kwargs: _sources())
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_forecast(
            store,
            market.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
        )
    )

    assert outcome == ForecastOutcome.PUBLISHED
    assert len(fake_llm.calls) == 2
    assert "probability_yes" in fake_llm.calls[1]["system"]
    assert len(_predictions(store)) == 1


def test_charges_budget_with_actual_token_counts(monkeypatch) -> None:
    store = _store()
    market = _seed_market(store)
    response = LLMResponse(
        text=json.dumps(_valid_payload()),
        prompt_tokens=1234,
        completion_tokens=456,
        model="claude-haiku-4-5-test",
    )
    fake_llm = FakeLLMClient([response])
    budget = RecordingBudget(authorizes=[], charges=[])
    monkeypatch.setattr(subject, "retrieve_for_market", lambda *_args, **_kwargs: _sources())
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(subject.generate_forecast(store, market.id, budget=budget))

    assert outcome == ForecastOutcome.PUBLISHED
    assert budget.charges == [(1234, 456)]
    prediction = _predictions(store)[0]
    assert prediction.prompt_tokens == 1234
    assert prediction.completion_tokens == 456


def test_forecast_outcome_enum_has_required_cases() -> None:
    assert {case.value for case in ForecastOutcome} == {
        "PUBLISHED",
        "ABSTAINED_BUDGET",
        "ABSTAINED_INSUFFICIENT_SOURCES",
        "ABSTAINED_NEAR_DUPLICATE",
        "ABSTAINED_CITATION_FABRICATION",
        "ABSTAINED_MARKET_EXPIRED",
    }


def test_budget_exhaustion_exception_is_reused() -> None:
    with pytest.raises(BudgetExhausted):
        guard = forecast_budget.HourlyBudgetGuard(
            max_prompt_tokens=14_001,
            max_completion_tokens=3_501,
        )
        guard.authorize(2, 2)
