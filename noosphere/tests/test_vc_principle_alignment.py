"""Tests for the VC firm preset's principle-alignment runner.

Covers:

* Preset descriptor (`theseus-template/presets/vc_firm.yml`) validates
  against the preset schema.
* `select_relevant_principles` filters by domain/sector affinity but
  keeps universal-domain principles for every deal.
* The runner produces one row per relevant principle.
* The runner is idempotent on (deal_id, principle_id) — re-running on
  the same inputs upserts in place rather than creating duplicates.
* The deterministic fallback flips MATCH → CONFLICT when the deal
  excerpt negates the principle vocabulary.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from noosphere.vc import (
    AlignmentVerdict,
    DealPayload,
    PrincipleAlignmentRunner,
    PrinciplePayload,
    select_relevant_principles,
)
from noosphere.vc.principle_alignment import alignments_as_upserts


# ── Preset descriptor ───────────────────────────────────────────────────────

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PRESET_PATH = _REPO_ROOT / "theseus-template" / "presets" / "vc_firm.yml"
_SCHEMA_PATH = (
    _REPO_ROOT / "theseus-template" / "presets" / "schema" / "preset.schema.json"
)


def test_vc_firm_preset_file_exists() -> None:
    assert _PRESET_PATH.is_file(), f"missing preset at {_PRESET_PATH}"


def test_vc_firm_preset_validates_against_schema() -> None:
    yaml = pytest.importorskip("yaml")
    jsonschema = pytest.importorskip("jsonschema")
    data = yaml.safe_load(_PRESET_PATH.read_text())
    schema = json.loads(_SCHEMA_PATH.read_text())
    jsonschema.validate(data, schema)
    # Spot-check the contract.
    assert data["modules"]["forecasts"] is False
    assert data["modules"]["equities"] is False
    assert data["modules"]["principles"] is True
    assert "founder_quality" in data["default_principle_domains"]
    primary = data["decision_surface"]["primary"]
    assert primary == "/deals"
    hidden = data["decision_surface"]["hidden"]
    assert "/forecasts" in hidden and "/equities" in hidden


# ── select_relevant_principles ──────────────────────────────────────────────


def _p(principle_id: str, *domains: str) -> PrinciplePayload:
    return PrinciplePayload(
        id=principle_id,
        text=f"Principle {principle_id}",
        domains=domains,
    )


def test_select_relevant_keeps_universal_domains_for_any_sector() -> None:
    principles = [_p("founder", "founder_quality")]
    deal = DealPayload(id="d1", name="X", sector="fintech")
    chosen = select_relevant_principles(principles, deal=deal)
    assert [p.id for p in chosen] == ["founder"]


def test_select_relevant_filters_by_sector_affinity() -> None:
    principles = [
        _p("reg", "regulatory"),
        _p("market", "market_size"),
    ]
    # consumer sector → market_size is in-affinity; regulatory is not.
    deal = DealPayload(id="d1", name="X", sector="consumer")
    chosen = {p.id for p in select_relevant_principles(principles, deal=deal)}
    assert "market" in chosen
    assert "reg" not in chosen


def test_select_relevant_keeps_all_for_unknown_sector() -> None:
    principles = [_p("reg", "regulatory"), _p("moats", "moats")]
    deal = DealPayload(id="d1", name="X", sector="quantum-cheese")
    chosen = {p.id for p in select_relevant_principles(principles, deal=deal)}
    assert chosen == {"reg", "moats"}


def test_select_relevant_keeps_untagged_principles() -> None:
    principles = [PrinciplePayload(id="bare", text="any")]
    deal = DealPayload(id="d1", name="X", sector="fintech")
    chosen = select_relevant_principles(principles, deal=deal)
    assert [p.id for p in chosen] == ["bare"]


# ── Runner: shape + idempotency ─────────────────────────────────────────────


def _runner() -> PrincipleAlignmentRunner:
    return PrincipleAlignmentRunner(llm=None)


def test_runner_emits_one_row_per_relevant_principle() -> None:
    principles = [
        _p("p1", "founder_quality"),
        _p("p2", "moats"),
        _p("p3", "regulatory"),
    ]
    deal = DealPayload(
        id="deal-1",
        name="Acme",
        description="Acme builds enterprise tooling with strong moats.",
        sector="enterprise",
        source_excerpts=("The team has built moats around their pipeline.",),
    )
    rows = _runner().run(deal=deal, principles=principles)
    # founder_quality (universal) + moats (enterprise affinity).
    # regulatory has no affinity with enterprise → dropped.
    principle_ids = {r.principle_id for r in rows}
    assert principle_ids == {"p1", "p2"}
    for row in rows:
        assert row.deal_id == "deal-1"
        assert isinstance(row.verdict, AlignmentVerdict)


def test_runner_is_idempotent_on_dealid_principleid() -> None:
    principles = [_p("p1", "founder_quality")]
    deal = DealPayload(
        id="deal-1",
        name="Acme",
        description="The founders have shipped this product to thousands.",
        sector="enterprise",
        source_excerpts=("Founders shipped product to thousands of users.",),
    )
    runner = _runner()
    first = runner.run(deal=deal, principles=principles)
    second = runner.run(deal=deal, principles=principles)
    # Same key set; verdict + rationale stable.
    keys_first = {(r.deal_id, r.principle_id) for r in first}
    keys_second = {(r.deal_id, r.principle_id) for r in second}
    assert keys_first == keys_second
    by_key_first = {(r.deal_id, r.principle_id): r for r in first}
    by_key_second = {(r.deal_id, r.principle_id): r for r in second}
    for key in keys_first:
        assert by_key_first[key].verdict == by_key_second[key].verdict
        assert by_key_first[key].rationale == by_key_second[key].rationale
    # Re-running yields a fresh run_id (the audit trail differentiates
    # snapshots) but produces the same upsert payload count.
    assert first[0].run_id != second[0].run_id
    merged = alignments_as_upserts(first + second)
    assert len(merged) == len(keys_first)


def test_runner_detects_negation_for_conflict_verdict() -> None:
    principles = [
        PrinciplePayload(
            id="reg",
            text="Founders must have regulatory experience.",
            domains=("founder_quality",),
        )
    ]
    deal = DealPayload(
        id="deal-conflict",
        name="Acme",
        description="No regulatory experience among the founders.",
        sector="enterprise",
        source_excerpts=("Founders have no regulatory experience.",),
    )
    rows = _runner().run(deal=deal, principles=principles)
    assert len(rows) == 1
    assert rows[0].verdict is AlignmentVerdict.CONFLICT


def test_runner_returns_unclear_when_no_overlap() -> None:
    principles = [
        PrinciplePayload(
            id="moats",
            text="Defensible technical moats are required.",
            domains=("moats",),
        )
    ]
    deal = DealPayload(
        id="deal-thin",
        name="Acme",
        description="A pitch about cats.",
        sector="enterprise",
        source_excerpts=("A pitch about cats.",),
    )
    rows = _runner().run(deal=deal, principles=principles)
    assert len(rows) == 1
    assert rows[0].verdict is AlignmentVerdict.UNCLEAR
    assert rows[0].confidence <= 0.5


def test_runner_upsert_payload_round_trips_dict() -> None:
    principles = [_p("p1", "founder_quality")]
    deal = DealPayload(
        id="deal-1",
        name="Acme",
        description="Founders shipped product.",
        sector="enterprise",
        source_excerpts=("Founders shipped product.",),
    )
    rows = _runner().run(deal=deal, principles=principles)
    payloads = alignments_as_upserts(rows)
    assert payloads, "expected at least one upsert payload"
    p = payloads[0]
    assert p["deal_id"] == "deal-1"
    assert p["principle_id"] == "p1"
    # Verdict is serialised as its string value.
    assert p["verdict"] in {"MATCH", "CONFLICT", "UNCLEAR"}
