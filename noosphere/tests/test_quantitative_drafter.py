"""Tests for the quantitative-formalisation drafter and schema.

Coverage:

* Drafter produces JSON that validates against the schema on a
  fixture of 5 principles, including 2 expected refusals.
* Drafter is idempotent — re-running it does not duplicate work.
* Drafter is forbidden from self-approving; any APPROVED status the
  LLM emits is rejected.
* APPROVED schema invariants are enforced (non-empty null hypothesis,
  ≥ 1 metric, ≥ 1 test) — both at construction and on the explicit
  ``enforce_approval_invariants`` check.
* UNFORMALISABLE invariants are enforced (reason required).
* Triage-style workflow round-trips: draft → approve with edits
  produces a row whose APPROVED invariants hold.
"""

from __future__ import annotations

import json
from typing import Iterable

import pytest

from noosphere.llm import MockLLMClient
from noosphere.models import (
    DataSourceSpec,
    FormalisationStatus,
    MetricSpec,
    Principle,
    QuantitativeFormalisation,
    StatisticalTestKind,
    StatisticalTestSpec,
)
from noosphere.quantitative.drafter import (
    QuantitativeFormalisationDrafter,
)
from noosphere.quantitative.formalisation import (
    SchemaConformanceError,
    enforce_approval_invariants,
    parse_drafter_json,
    validate_schema,
)


# ── Fixtures ────────────────────────────────────────────────────────


def _principle(text: str, *, id_: str | None = None) -> Principle:
    return Principle(id=id_ or text[:8], text=text)


FIXTURE_PRINCIPLES: list[Principle] = [
    _principle(
        "Markets overreact to surprise inflation prints in the first 30 minutes.",
        id_="p-infl",
    ),
    _principle(
        "Founders who delay shipping lose more in option value than they "
        "gain in product polish.",
        id_="p-ship",
    ),
    _principle(
        "Power-law funding distributions imply concentration in top "
        "decile of returns.",
        id_="p-power",
    ),
    # Two expected-refusal cases.
    _principle(
        "Beauty is its own justification.",
        id_="p-norm",
    ),
    _principle(
        "Insider counterparties' private positions reveal the true "
        "market sentiment.",
        id_="p-private",
    ),
]


def _quantifiable_response(
    *,
    null_hypothesis: str,
    metric_name: str,
    dataset_name: str,
    provenance: str,
) -> str:
    return json.dumps(
        {
            "status": "DRAFT",
            "null_hypothesis": null_hypothesis,
            "metrics": [
                {
                    "name": metric_name,
                    "definition": "Concrete and reproducible definition.",
                    "unit": "ratio",
                    "source_dataset": dataset_name,
                    "update_cadence": "daily",
                }
            ],
            "tests": [
                {
                    "kind": "regression",
                    "dependent": "y",
                    "independents": ["x"],
                    "controls": [],
                    "dataset_filter": "",
                    "expected_sign_or_magnitude": "positive coefficient",
                    "expected_p_threshold": 0.05,
                }
            ],
            "data_sources": [
                {
                    "name": dataset_name,
                    "provenance": provenance,
                    "license": "public",
                    "refresh_cadence": "daily",
                }
            ],
            "decision_thresholds": [
                "if R^2 < 0.05 across 3 windows → principle weakens"
            ],
            "drafter_notes": "",
        }
    )


def _refusal_response(reason: str) -> str:
    return json.dumps(
        {
            "status": "UNFORMALISABLE",
            "unformalisable_reason": reason,
            "null_hypothesis": "",
            "metrics": [],
            "tests": [],
            "data_sources": [],
            "decision_thresholds": [],
        }
    )


DRAFTER_RESPONSES: list[str] = [
    _quantifiable_response(
        null_hypothesis="Surprise inflation prints are not followed by 30-minute equity moves greater than baseline volatility.",
        metric_name="ES_30min_post_CPI_return",
        dataset_name="FRED CPIAUCSL + Polygon SPY minute bars",
        provenance="https://fred.stlouisfed.org/series/CPIAUCSL",
    ),
    _quantifiable_response(
        null_hypothesis="Shipping delay duration is uncorrelated with subsequent option-value erosion.",
        metric_name="days_to_first_release",
        dataset_name="Crunchbase + GitHub release tags",
        provenance="internal table: portfolio_company_releases",
    ),
    _quantifiable_response(
        null_hypothesis="Top-decile return concentration is not greater than chance in venture portfolios.",
        metric_name="top_decile_return_share",
        dataset_name="Preqin venture fund returns",
        provenance="https://www.preqin.com",
    ),
    _refusal_response(
        "pure-normative principle; 'beauty' has no observable referent the firm can measure without smuggling in interpretation"
    ),
    _refusal_response(
        "principle requires non-public insider position data the firm cannot access; refusing rather than fabricating a proxy"
    ),
]


# ── Fake store for drafter tests ────────────────────────────────────


class _FakeStore:
    """Minimal in-memory ``_FormalisationStore`` for drafter tests."""

    def __init__(self, principles: Iterable[Principle]) -> None:
        self._principles = list(principles)
        self._rows: dict[str, QuantitativeFormalisation] = {}

    def list_principles(self) -> list[Principle]:
        return list(self._principles)

    def list_quantitative_formalisations(self) -> list[QuantitativeFormalisation]:
        return list(self._rows.values())

    def get_quantitative_formalisations_for_principle(
        self, principle_id: str
    ) -> list[QuantitativeFormalisation]:
        return [r for r in self._rows.values() if r.principle_id == principle_id]

    def put_quantitative_formalisation(
        self, formalisation: QuantitativeFormalisation
    ) -> None:
        self._rows[formalisation.id] = formalisation


# ── Schema validation tests ────────────────────────────────────────


def test_validate_schema_round_trips_a_valid_draft() -> None:
    raw = _quantifiable_response(
        null_hypothesis="N",
        metric_name="m",
        dataset_name="d",
        provenance="https://x",
    )
    payload = parse_drafter_json(raw)
    f = validate_schema(payload, principle_id="p")
    assert f.principle_id == "p"
    assert f.status == FormalisationStatus.DRAFT.value
    assert len(f.metrics) == 1
    assert len(f.tests) == 1


def test_validate_schema_rejects_drafter_setting_approved() -> None:
    raw = _quantifiable_response(
        null_hypothesis="N",
        metric_name="m",
        dataset_name="d",
        provenance="https://x",
    )
    payload = parse_drafter_json(raw)
    payload["status"] = "APPROVED"
    with pytest.raises(SchemaConformanceError):
        validate_schema(payload, principle_id="p")


def test_parse_drafter_json_strips_code_fences_and_prose() -> None:
    inner = _quantifiable_response(
        null_hypothesis="N",
        metric_name="m",
        dataset_name="d",
        provenance="https://x",
    )
    wrapped = f"here is your spec:\n```json\n{inner}\n```\n"
    out = parse_drafter_json(wrapped)
    assert isinstance(out, dict)
    assert out["status"] == "DRAFT"


def test_parse_drafter_json_raises_on_empty() -> None:
    with pytest.raises(SchemaConformanceError):
        parse_drafter_json("")


def test_unformalisable_requires_reason() -> None:
    with pytest.raises(Exception):
        QuantitativeFormalisation(
            principle_id="p", status=FormalisationStatus.UNFORMALISABLE
        )


def test_approved_invariants_at_construction() -> None:
    # Empty null hypothesis: rejected.
    with pytest.raises(Exception):
        QuantitativeFormalisation(
            principle_id="p", status=FormalisationStatus.APPROVED
        )
    # Missing tests: rejected.
    with pytest.raises(Exception):
        QuantitativeFormalisation(
            principle_id="p",
            status=FormalisationStatus.APPROVED,
            null_hypothesis="N",
            metrics=[
                MetricSpec(
                    name="m",
                    definition="d",
                    unit="u",
                    source_dataset="s",
                    update_cadence="daily",
                )
            ],
        )


def test_enforce_approval_invariants_explicit() -> None:
    # Build as DRAFT, flip to APPROVED in-place, then re-check.
    f = QuantitativeFormalisation(
        principle_id="p",
        null_hypothesis="N",
        metrics=[
            MetricSpec(
                name="m",
                definition="d",
                unit="u",
                source_dataset="s",
                update_cadence="daily",
            )
        ],
        tests=[
            StatisticalTestSpec(
                kind=StatisticalTestKind.REGRESSION,
                dependent="y",
                independents=["x"],
                expected_sign_or_magnitude="positive",
                expected_p_threshold=0.05,
            )
        ],
        data_sources=[
            DataSourceSpec(
                name="s",
                provenance="https://x",
                license="public",
                refresh_cadence="daily",
            )
        ],
        decision_thresholds=["if R^2<0.05 → weaken"],
    )
    f.status = FormalisationStatus.APPROVED.value
    enforce_approval_invariants(f)


# ── Drafter tests ──────────────────────────────────────────────────


def test_drafter_produces_valid_json_on_five_principles() -> None:
    store = _FakeStore(FIXTURE_PRINCIPLES)
    llm = MockLLMClient(responses=list(DRAFTER_RESPONSES))
    drafter = QuantitativeFormalisationDrafter(
        store=store,
        llm=llm,
        system_prompt_loader=lambda: "TEST SYSTEM PROMPT",
        max_fewshot=0,
    )
    report = drafter.draft_missing()
    assert len(report.drafted_ids) == 3
    assert len(report.refused_ids) == 2
    assert len(report.skipped_ids) == 0

    persisted = store.list_quantitative_formalisations()
    assert len(persisted) == 5
    by_pid = {r.principle_id: r for r in persisted}

    # Drafted rows pass schema and never carry APPROVED.
    for pid in ("p-infl", "p-ship", "p-power"):
        r = by_pid[pid]
        assert r.status == FormalisationStatus.DRAFT.value
        assert r.null_hypothesis
        assert r.metrics
        assert r.tests
        assert r.data_sources
        assert r.decision_thresholds

    # Refusals carry a structured reason.
    for pid in ("p-norm", "p-private"):
        r = by_pid[pid]
        assert r.status == FormalisationStatus.UNFORMALISABLE.value
        assert r.unformalisable_reason


def test_drafter_is_idempotent_per_principle() -> None:
    store = _FakeStore(FIXTURE_PRINCIPLES[:1])
    llm = MockLLMClient(responses=[DRAFTER_RESPONSES[0]])
    drafter = QuantitativeFormalisationDrafter(
        store=store,
        llm=llm,
        system_prompt_loader=lambda: "TEST",
        max_fewshot=0,
    )
    drafter.draft_missing()
    # Re-running with the same store should skip — no new LLM calls.
    extra_llm = MockLLMClient(responses=[])
    drafter2 = QuantitativeFormalisationDrafter(
        store=store,
        llm=extra_llm,
        system_prompt_loader=lambda: "TEST",
        max_fewshot=0,
    )
    report = drafter2.draft_missing()
    assert report.drafted_ids == []
    assert report.refused_ids == []
    assert report.skipped_ids == ["p-infl"]
    assert extra_llm.calls == []
    assert len(store.list_quantitative_formalisations()) == 1


def test_drafter_refuses_to_self_approve() -> None:
    # An LLM that returns APPROVED should be coerced into UNFORMALISABLE
    # via the schema-error path (drafter is forbidden from self-approval).
    bad = json.dumps(
        {
            "status": "APPROVED",
            "null_hypothesis": "N",
            "metrics": [
                {
                    "name": "m",
                    "definition": "d",
                    "unit": "u",
                    "source_dataset": "s",
                    "update_cadence": "daily",
                }
            ],
            "tests": [
                {
                    "kind": "regression",
                    "dependent": "y",
                    "independents": ["x"],
                    "controls": [],
                    "dataset_filter": "",
                    "expected_sign_or_magnitude": "+",
                    "expected_p_threshold": 0.05,
                }
            ],
            "data_sources": [
                {
                    "name": "s",
                    "provenance": "x",
                    "license": "public",
                    "refresh_cadence": "daily",
                }
            ],
            "decision_thresholds": ["t"],
        }
    )
    store = _FakeStore(FIXTURE_PRINCIPLES[:1])
    llm = MockLLMClient(responses=[bad])
    drafter = QuantitativeFormalisationDrafter(
        store=store,
        llm=llm,
        system_prompt_loader=lambda: "TEST",
        max_fewshot=0,
    )
    drafter.draft_missing()
    row = store.list_quantitative_formalisations()[0]
    # The schema rejects APPROVED-from-drafter; the drafter persists a
    # structured refusal rather than promoting the row.
    assert row.status == FormalisationStatus.UNFORMALISABLE.value
    assert row.unformalisable_reason
    assert "drafter_schema_error" in row.unformalisable_reason


def test_triage_workflow_round_trip() -> None:
    """Draft → founder accept-with-edit → APPROVED row holds invariants.

    Mirrors the founder triage UI's accept handler: the row starts as
    a DRAFT from the drafter; the founder edits the null hypothesis
    and decision thresholds; the resulting APPROVED row must pass
    ``enforce_approval_invariants``.
    """

    store = _FakeStore(FIXTURE_PRINCIPLES[:1])
    llm = MockLLMClient(responses=[DRAFTER_RESPONSES[0]])
    drafter = QuantitativeFormalisationDrafter(
        store=store,
        llm=llm,
        system_prompt_loader=lambda: "TEST",
        max_fewshot=0,
    )
    drafter.draft_missing()
    draft = store.list_quantitative_formalisations()[0]
    assert draft.status == FormalisationStatus.DRAFT.value

    # Founder edits and flips to APPROVED via the explicit path the
    # Codex UI uses.
    payload = draft.model_dump()
    payload["null_hypothesis"] = (
        "Surprise inflation prints are not followed by 30-minute moves "
        "greater than baseline volatility, even controlling for the "
        "direction of surprise."
    )
    payload["decision_thresholds"] = [
        "if R^2 < 0.05 across 3 windows → principle weakens",
        "if effect flips sign across two consecutive years → retire",
    ]
    payload["status"] = FormalisationStatus.APPROVED.value
    approved = QuantitativeFormalisation(**payload)
    enforce_approval_invariants(approved)
    assert approved.status == FormalisationStatus.APPROVED.value
    assert len(approved.decision_thresholds) == 2


def test_drafter_skips_existing_when_drafting_for_principle() -> None:
    store = _FakeStore(FIXTURE_PRINCIPLES[:1])
    llm = MockLLMClient(responses=[DRAFTER_RESPONSES[0]])
    drafter = QuantitativeFormalisationDrafter(
        store=store,
        llm=llm,
        system_prompt_loader=lambda: "TEST",
        max_fewshot=0,
    )
    first = drafter.draft_for_principle(FIXTURE_PRINCIPLES[0])
    second = drafter.draft_for_principle(FIXTURE_PRINCIPLES[0])
    assert first.id == second.id
    assert len(store.list_quantitative_formalisations()) == 1
