"""Shared fixtures and helpers for the Round-19 integration tests.

The integration tests in this directory walk the full algorithm-layer
pipeline against a real in-memory ``Store`` so the seams between
modules — drafter → runtime → synthesizer → memo → portfolio agent →
bet → resolution → calibration → contradiction engine — are exercised
end-to-end. The hermetic mocks live here so the test module can stay
focused on the assertions.

Key seams faked here, by design:

* **LLM** — every drafter/runtime/synthesizer call is served by a
  scripted :class:`noosphere.llm.MockLLMClient`. The fake records its
  prompts; tests assert on the number and order of calls. This is the
  only way the test stays under the 30-second budget and remains
  deterministic.
* **Principles** — the real ``Store.list_principles`` reads from the
  Codex Prisma schema. For a noosphere-only sqlite the helper returns
  ``[]``, which would short-circuit every test. The :class:`_IntegrationStore`
  shim below subclasses the real ``Store`` and exposes
  ``list_principles`` from an in-memory dict the test populates, plus
  ``get_principle`` for the drafter. Every other method delegates to
  the real ``Store``.
* **Embedder** — the canonical ``ContradictionEngine`` needs vectors;
  the test fixtures attach deterministic embeddings to the ``Principle``
  rows so the engine never has to call out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import pytest
import yaml

from noosphere.llm import MockLLMClient
from noosphere.models import (
    Discipline,
    Principle,
    ProvenanceKind,
)
from noosphere.store import Store


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Fake LLM ──────────────────────────────────────────────────────


@dataclass
class CountingMockLLM:
    """Scriptable LLM client that also tracks call counts per stage.

    Thin wrapper around :class:`MockLLMClient` — same interface (the
    drafter / runtime / synthesizer call ``complete(...)``), with a
    per-stage tag the test passes via :meth:`stage` so the test can
    assert the number of LLM calls each stage actually consumed.
    """

    responses: list[str] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    stage_counts: dict[str, int] = field(default_factory=dict)
    _current_stage: str = "unstaged"

    def stage(self, name: str) -> None:
        self._current_stage = name

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        if not self.responses:
            raise AssertionError(
                "CountingMockLLM: no scripted response left for stage "
                f"{self._current_stage!r}"
            )
        self.calls.append(
            {
                "stage": self._current_stage,
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        self.stage_counts[self._current_stage] = (
            self.stage_counts.get(self._current_stage, 0) + 1
        )
        return self.responses.pop(0)


# ── Store shim ────────────────────────────────────────────────────


class _IntegrationStore(Store):
    """Real ``Store`` with an in-process principle registry.

    The real ``list_principles`` reads from the Codex Prisma schema —
    in a noosphere-only sqlite it returns ``[]`` and the drafter /
    synthesizer cannot do their work. This subclass exposes an
    in-memory principle dict the test populates via
    :meth:`add_principle`; every other store helper is inherited
    unchanged, so the rest of the pipeline still hits real SQL rows.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._principles: dict[str, Principle] = {}
        self._contradictions: list[Any] = []
        self._lifecycles: dict[str, Any] = {}

    # ── Principles ────────────────────────────────────────────

    def add_principle(self, principle: Principle) -> None:
        self._principles[principle.id] = principle

    def list_principles(self) -> list[Principle]:  # type: ignore[override]
        return list(self._principles.values())

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        return self._principles.get(principle_id)

    # ── Contradictions ────────────────────────────────────────

    def seed_contradiction(
        self,
        *,
        contradiction_id: str,
        principle_a_id: str,
        principle_b_id: str,
        score: float,
        verdict: str,
        lifecycle_status: str,
    ) -> None:
        self._contradictions.append(
            _IntegrationContradictionResult(
                id=contradiction_id,
                principle_a_id=principle_a_id,
                principle_b_id=principle_b_id,
                score=score,
                verdict=verdict,
            )
        )
        self._lifecycles[contradiction_id] = _IntegrationLifecycle(
            current_status=lifecycle_status
        )

    def list_contradiction_results(  # type: ignore[override]
        self,
        *,
        method: Optional[str] = None,
        verdict: Optional[str] = None,
        limit: int = 200,
    ) -> list[Any]:
        out = list(self._contradictions)
        if verdict is not None:
            out = [r for r in out if r.verdict == verdict]
        return out[:limit]

    def get_contradiction_lifecycle(  # type: ignore[override]
        self, contradiction_id: str
    ) -> Optional[Any]:
        return self._lifecycles.get(contradiction_id)


@dataclass
class _IntegrationContradictionResult:
    id: str
    principle_a_id: str
    principle_b_id: str
    score: float
    verdict: str


@dataclass
class _IntegrationLifecycle:
    current_status: str


# ── Fixture loaders ──────────────────────────────────────────────


_DISCIPLINE_LOOKUP = {d.name: d for d in Discipline}


def _principle_from_yaml(row: dict[str, Any], *, embedding: Sequence[float]) -> Principle:
    return Principle(
        id=str(row["id"]),
        text=str(row["text"]).strip(),
        disciplines=[
            _DISCIPLINE_LOOKUP[name]
            for name in row.get("disciplines", [])
            if name in _DISCIPLINE_LOOKUP
        ],
        tags=list(row.get("tags", [])),
        embedding=list(embedding),
        provenance=ProvenanceKind.PROPRIETARY,
    )


def _seeded_embedding(seed: int, *, dim: int = 64) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(float).tolist()


def load_principles_yaml(path: Path, *, embedding_seed_base: int) -> list[Principle]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        _principle_from_yaml(row, embedding=_seeded_embedding(embedding_seed_base + idx))
        for idx, row in enumerate(payload.get("principles", []))
    ]


def load_events_yaml(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(payload.get("events", []))


def load_polymarket_resolution(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Pytest fixtures ──────────────────────────────────────────────


@pytest.fixture
def integration_store() -> _IntegrationStore:
    return _IntegrationStore.from_database_url("sqlite:///:memory:")


@pytest.fixture
def arms_race_principles() -> list[Principle]:
    return load_principles_yaml(
        FIXTURES_DIR / "arms_race_principles.yml",
        embedding_seed_base=101,
    )


@pytest.fixture
def normative_principles() -> list[Principle]:
    return load_principles_yaml(
        FIXTURES_DIR / "normative_principles.yml",
        embedding_seed_base=201,
    )


@pytest.fixture
def arms_race_events() -> list[dict[str, Any]]:
    return load_events_yaml(FIXTURES_DIR / "arms_race_events.yml")


@pytest.fixture
def polymarket_resolution() -> dict[str, Any]:
    return load_polymarket_resolution(
        FIXTURES_DIR / "polymarket_resolution.json"
    )


@pytest.fixture
def contradiction_fixture() -> dict[str, Any]:
    return yaml.safe_load(
        (FIXTURES_DIR / "contradiction_pair.yml").read_text(encoding="utf-8")
    )


# ── Scripted LLM payloads ────────────────────────────────────────


def arms_race_drafter_payload(principle_ids: Sequence[str]) -> dict[str, Any]:
    """A valid DRAFTED payload for the drafter to parse.

    Wired to the arms-race principles fixture: every APPLY_PRINCIPLE
    step cites a principle in the cluster, every input declares a
    known observability provider, and the trigger predicate is
    syntactically the sandboxed-safe shape the validator accepts.
    """

    return {
        "outcome": "DRAFTED",
        "name": "Arms-Race Escalation Predictor",
        "description": (
            "Detects bilateral arms-race onset between two states from "
            "spending acceleration, rhetoric, and mediator presence."
        ),
        "inputs": [
            {
                "name": "side_a_spending_delta",
                "type": "RATIO",
                "description": "State A YoY military spending delta.",
                "observability_source": "currents.macro.defense_spending.side_a",
            },
            {
                "name": "side_b_spending_delta",
                "type": "RATIO",
                "description": "State B YoY military spending delta.",
                "observability_source": "currents.macro.defense_spending.side_b",
            },
            {
                "name": "escalation_index",
                "type": "INDEX",
                "description": "Composite rhetoric escalation index.",
                "observability_source": "currents.x.rhetoric_index",
            },
            {
                "name": "mediator_present",
                "type": "BOOL",
                "description": "Whether a credible mediator is engaged.",
                "observability_source": "manual.operator.entered",
            },
        ],
        "output": {
            "name": "arms_race_projection",
            "type": "STRUCTURED",
            "description": "Per-side projected spending increase.",
            "fields": [
                {"name": "side_a_pct", "type": "RATIO"},
                {"name": "side_b_pct", "type": "RATIO"},
            ],
        },
        "reasoning_chain": [
            {
                "step_kind": "DETECT",
                "predicate": (
                    "input.side_a_spending_delta > 0 and "
                    "input.side_b_spending_delta > 0 and "
                    "input.escalation_index > 0.6 and "
                    "input.mediator_present == False"
                ),
                "derived_fact": (
                    "Both states accelerating under rising rhetoric "
                    "without a mediator."
                ),
            },
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": principle_ids[0],
                "derived_fact": "Security-dilemma feedback projects growth.",
            },
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": principle_ids[1],
                "derived_fact": (
                    "Domestic lock-in lowers reversal probability."
                ),
            },
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": principle_ids[2],
                "derived_fact": (
                    "Second-derivative signal confirms escalation onset."
                ),
            },
            {
                "step_kind": "SYNTHESIZE",
                "derived_fact": "Compound per-side increases over horizon.",
            },
            {
                "step_kind": "OUTPUT",
                "derived_fact": "Emit per-side projection with band.",
            },
        ],
        "trigger_predicate": (
            "input.side_a_spending_delta > 0 and "
            "input.side_b_spending_delta > 0 and "
            "input.escalation_index > 0.6 and "
            "input.mediator_present == False"
        ),
        "confidence_note": "Rhetoric index drift is the weakest leg.",
    }


def runtime_apply_principle_response(principle_id: str) -> str:
    return (
        f"Applying {principle_id}: the input pattern reinforces the "
        "principle's prediction."
    )


def runtime_output_response(
    *,
    side_a_pct: float = 0.12,
    side_b_pct: float = 0.14,
    horizon_months: int = 12,
    confidence_low: float = 0.55,
    confidence_high: float = 0.78,
) -> str:
    return json.dumps(
        {
            "output": {
                "side_a_pct": side_a_pct,
                "side_b_pct": side_b_pct,
                "horizon_months": horizon_months,
            },
            "confidence_low": confidence_low,
            "confidence_high": confidence_high,
            "predicted_horizon_seconds": 86400.0 * 365,
        }
    )


def synthesizer_chain_response(
    *,
    principle_ids: Sequence[str],
    confidence_low: float = 0.55,
    confidence_high: float = 0.75,
    include_implied_bet: bool = True,
) -> str:
    chain = [
        {
            "step_kind": "DETECT",
            "principle_id": principle_ids[0],
            "observation_id": None,
            "derived_fact": (
                "Bilateral spending acceleration crosses the threshold."
            ),
        },
        {
            "step_kind": "APPLY_PRINCIPLE",
            "principle_id": principle_ids[1],
            "observation_id": None,
            "derived_fact": (
                "Domestic lock-in lowers the probability of reversal."
            ),
        },
        {
            "step_kind": "SYNTHESIZE",
            "principle_id": principle_ids[0],
            "observation_id": None,
            "derived_fact": (
                "Combine principles into a forward projection."
            ),
        },
    ]
    payload: dict[str, Any] = {
        "abstain": False,
        "assertion": (
            "Bilateral defense spending grows >10% over the next year "
            "under the cited regime."
        ),
        "confidence_low": confidence_low,
        "confidence_high": confidence_high,
        "reasoning_chain": chain,
    }
    if include_implied_bet:
        payload["implied_bet"] = {
            "venue": "polymarket",
            "exchange": "POLYMARKET",
            "prediction_id": None,
            "side": "YES",
            "stake": 50.0,
            "stake_range": [25.0, 50.0],
            "entry_price": 0.42,
            "horizon_days": 365,
            "rationale": (
                "Memo's confidence is concentrated above the market price."
            ),
        }
    else:
        payload["implied_bet"] = None
    return json.dumps(payload)


__all__ = [
    "CountingMockLLM",
    "FIXTURES_DIR",
    "MockLLMClient",
    "_IntegrationStore",
    "arms_race_drafter_payload",
    "load_events_yaml",
    "load_polymarket_resolution",
    "load_principles_yaml",
    "runtime_apply_principle_response",
    "runtime_output_response",
    "synthesizer_chain_response",
]
