"""Equity signal generator tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import sqrt
from typing import Any

from noosphere.currents._llm_client import LLMResponse
from noosphere.equities import signal_generator as subject
from noosphere.equities.retrieval_adapter import RetrievedEquitySource
from noosphere.equities.signal_generator import SignalOutcome
from noosphere.models import (
    EquityAssetClass,
    EquityInstrument,
    EquitySignal,
    EquitySignalDirection,
    EquitySignalStatus,
)
from noosphere.store import Store


ORG_ID = "org_equities_test"
PRINCIPLE_A_TEXT = (
    "Durable platform businesses with high services revenue compound "
    "operating margins through subscriber retention."
)
PRINCIPLE_B_TEXT = (
    "Concentrated supply-chain exposure to a single geography is a "
    "structural risk that compresses long-run multiples."
)
CONCLUSION_TEXT = "Apple's services revenue grew 14% year over year last quarter."
CLAIM_TEXT = "An analyst note today described the trade desk as cautious."


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
            raise AssertionError("no scripted signal response left")
        item = self.script.pop(0)
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(
            text=json.dumps(item),
            prompt_tokens=int(item.get("_prompt_tokens", 320)),
            completion_tokens=int(item.get("_completion_tokens", 120)),
            model=str(item.get("_model", "claude-haiku-4-5-test")),
        )


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _instrument(*, instrument_id: str = "equity_instr_aapl") -> EquityInstrument:
    instrument = EquityInstrument(
        id=instrument_id,
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
        last_price=Decimal("182.500000"),
    )
    instrument.__dict__["sector"] = "Consumer Electronics"
    return instrument


def _seed_instrument(store: Store) -> EquityInstrument:
    instrument = _instrument()
    store.put_equity_instrument(instrument)
    return instrument


def _principle_sources() -> list[RetrievedEquitySource]:
    return [
        RetrievedEquitySource(
            source_type="PRINCIPLE",
            source_id="principle_platform_margins",
            text=PRINCIPLE_A_TEXT,
            relevance=0.92,
            surfaceable=True,
            visibility="PUBLIC",
            domain_of_applicability="consumer electronics",
            metadata={"principle_kind": "RULE"},
        ),
        RetrievedEquitySource(
            source_type="PRINCIPLE",
            source_id="principle_supply_chain",
            text=PRINCIPLE_B_TEXT,
            relevance=0.87,
            surfaceable=True,
            visibility="PUBLIC",
            domain_of_applicability="consumer electronics",
            metadata={"principle_kind": "RULE"},
        ),
        RetrievedEquitySource(
            source_type="CONCLUSION",
            source_id="conclusion_services_growth",
            text=CONCLUSION_TEXT,
            relevance=0.81,
            surfaceable=True,
            visibility="PUBLIC",
            domain_of_applicability=None,
            metadata={},
        ),
    ]


def _claim_only_sources() -> list[RetrievedEquitySource]:
    return [
        RetrievedEquitySource(
            source_type="CLAIM",
            source_id="claim_analyst_a",
            text=CLAIM_TEXT,
            relevance=0.65,
            surfaceable=True,
            visibility="PUBLIC",
            domain_of_applicability=None,
            metadata={},
        ),
        RetrievedEquitySource(
            source_type="CLAIM",
            source_id="claim_analyst_b",
            text="A separate desk reported similar caution overnight.",
            relevance=0.61,
            surfaceable=True,
            visibility="PUBLIC",
            domain_of_applicability=None,
            metadata={},
        ),
    ]


def _valid_payload() -> dict[str, Any]:
    return {
        "direction": "BULLISH",
        "confidence_low": 0.55,
        "confidence_high": 0.72,
        "target_price_low": 195.0,
        "target_price_high": 210.0,
        "horizon_days": 60,
        "headline": "Platform margins principle implies Apple's services tailwind is underpriced",
        "reasoning_markdown": (
            "Applying the platform-services principle to Apple's "
            "services trajectory gives a bullish read."
        ),
        "uncertainty_notes": "Supply chain concentration remains a tail risk.",
        "citations": [
            {
                "source_type": "PRINCIPLE",
                "source_id": "principle_platform_margins",
                "quoted_span": "Durable platform businesses with high services revenue compound",
                "support_label": "DIRECT",
            },
            {
                "source_type": "CONCLUSION",
                "source_id": "conclusion_services_growth",
                "quoted_span": "Apple's services revenue grew 14% year over year",
                "support_label": "INDIRECT",
            },
        ],
    }


def _claim_only_payload() -> dict[str, Any]:
    payload = _valid_payload()
    payload["citations"] = [
        {
            "source_type": "CLAIM",
            "source_id": "claim_analyst_a",
            "quoted_span": "the trade desk as cautious",
            "support_label": "DIRECT",
        }
    ]
    payload["headline"] = "Analyst caution dominates the read"
    payload["reasoning_markdown"] = (
        "Claim-only evidence is not enough but produces a candidate read."
    )
    return payload


# ── tests ────────────────────────────────────────────────────────────────────


def test_publishes_with_principle_citation(monkeypatch) -> None:
    store = _store()
    instrument = _seed_instrument(store)
    fake_llm = FakeLLMClient([_valid_payload()])
    budget = RecordingBudget(authorizes=[], charges=[])

    monkeypatch.setattr(
        subject, "retrieve_for_instrument", lambda *_a, **_k: _principle_sources()
    )
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_signal(
            store,
            instrument.id,
            budget=budget,
            organization_id=ORG_ID,
        )
    )

    assert outcome == SignalOutcome.PUBLISHED
    open_signals = store.list_open_signals(organization_id=ORG_ID)
    assert len(open_signals) == 1
    signal = open_signals[0]
    assert signal.direction == EquitySignalDirection.BULLISH
    assert signal.status == EquitySignalStatus.PUBLISHED
    assert signal.horizon_days == 60
    citations = store.list_equity_signal_citations(signal.id)
    assert {c.source_type for c in citations} == {"PRINCIPLE", "CONCLUSION"}
    assert budget.charges == [(320, 120)]
    assert subject.PROMPT_SEPARATOR_BEGIN in fake_llm.calls[0]["user"]


def test_refuses_when_only_claim_citations(monkeypatch) -> None:
    """The generator must refuse to publish a directional signal that cites
    no principle — even if retrieval surfaced principles, the LLM's chosen
    citations decide the code-level refusal contract."""

    store = _store()
    instrument = _seed_instrument(store)
    fake_llm = FakeLLMClient([_claim_only_payload()])

    monkeypatch.setattr(
        subject,
        "retrieve_for_instrument",
        lambda *_a, **_k: _principle_sources() + _claim_only_sources(),
    )
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_signal(
            store,
            instrument.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
            organization_id=ORG_ID,
        )
    )

    assert outcome == SignalOutcome.ABSTAINED_INSUFFICIENT_PRINCIPLES
    assert store.list_open_signals(organization_id=ORG_ID) == []


def test_abstains_when_retrieval_returns_no_principles(monkeypatch) -> None:
    store = _store()
    instrument = _seed_instrument(store)
    fake_llm = FakeLLMClient([_valid_payload()])

    monkeypatch.setattr(
        subject, "retrieve_for_instrument", lambda *_a, **_k: _claim_only_sources()
    )
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_signal(
            store,
            instrument.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
            organization_id=ORG_ID,
        )
    )

    assert outcome == SignalOutcome.ABSTAINED_INSUFFICIENT_PRINCIPLES
    assert fake_llm.calls == []


def test_abstains_when_retrieval_is_empty(monkeypatch) -> None:
    """Empty retrieval surfaces as ABSTAINED_NO_DOMAIN_MATCH — the adapter
    drops principles whose domain does not match the instrument."""

    store = _store()
    instrument = _seed_instrument(store)
    fake_llm = FakeLLMClient([_valid_payload()])

    monkeypatch.setattr(subject, "retrieve_for_instrument", lambda *_a, **_k: [])
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_signal(
            store,
            instrument.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
            organization_id=ORG_ID,
        )
    )

    assert outcome == SignalOutcome.ABSTAINED_NO_DOMAIN_MATCH
    assert fake_llm.calls == []


def test_abstains_on_near_duplicate(monkeypatch) -> None:
    store = _store()
    instrument = _seed_instrument(store)
    store.put_equity_signal(
        EquitySignal(
            instrument_id=instrument.id,
            organization_id=ORG_ID,
            direction=EquitySignalDirection.BULLISH,
            confidence_low=Decimal("0.55"),
            confidence_high=Decimal("0.70"),
            horizon_days=45,
            headline="Apple platform margins look mispriced",
            reasoning="seed",
            model_name="fixture",
            status=EquitySignalStatus.PUBLISHED,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    instrument_query = f"{instrument.symbol} {instrument.name}".strip()
    mapping = {
        instrument_query: [1.0, 0.0],
        "Apple platform margins look mispriced": [
            0.95,
            sqrt(1.0 - 0.95**2),
        ],
    }
    fake_llm = FakeLLMClient([_valid_payload()])
    monkeypatch.setattr(
        subject, "retrieve_for_instrument", lambda *_a, **_k: _principle_sources()
    )
    monkeypatch.setattr(subject, "embed_text", lambda text: mapping[text])
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_signal(
            store,
            instrument.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
            organization_id=ORG_ID,
        )
    )

    assert outcome == SignalOutcome.ABSTAINED_NEAR_DUPLICATE
    assert fake_llm.calls == []


def test_abstains_on_citation_fabrication(monkeypatch) -> None:
    store = _store()
    instrument = _seed_instrument(store)
    fabricated = _valid_payload()
    fabricated["citations"] = [
        {
            "source_type": "PRINCIPLE",
            "source_id": "principle_platform_margins",
            "quoted_span": "this span does not appear in the source",
            "support_label": "DIRECT",
        }
    ]
    fake_llm = FakeLLMClient([fabricated, fabricated])
    monkeypatch.setattr(
        subject, "retrieve_for_instrument", lambda *_a, **_k: _principle_sources()
    )
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_signal(
            store,
            instrument.id,
            budget=RecordingBudget(authorizes=[], charges=[]),
            organization_id=ORG_ID,
        )
    )

    assert outcome == SignalOutcome.ABSTAINED_CITATION_FABRICATION
    assert len(fake_llm.calls) == 2
    assert "failed exact citation validation" in fake_llm.calls[1]["system"]
    assert store.list_open_signals(organization_id=ORG_ID) == []


def test_abstains_on_budget_exhausted(monkeypatch) -> None:
    from noosphere.equities import budget as equities_budget

    store = _store()
    instrument = _seed_instrument(store)
    fake_llm = FakeLLMClient([_valid_payload()])

    budget = equities_budget.HourlyBudgetGuard(
        max_prompt_tokens=50_000,
        max_completion_tokens=50_000,
    )
    budget.charge(45_000, 49_000)

    monkeypatch.setattr(
        subject, "retrieve_for_instrument", lambda *_a, **_k: _principle_sources()
    )
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(
        subject.generate_signal(
            store,
            instrument.id,
            budget=budget,
            organization_id=ORG_ID,
        )
    )

    assert outcome == SignalOutcome.ABSTAINED_BUDGET
    assert fake_llm.calls == []
