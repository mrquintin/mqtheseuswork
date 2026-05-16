"""Prompt 09 — Oracle / synthesis provenance_filter tests.

Three checklist rows from the prompt's K block:

* Oracle filter includes/excludes correctly per checkbox.
* Synthesis weights are applied in the order they're declared
  (proprietary 2.0× ≥ endorsed 1.0× > studied 0.5× > opposing 0.1×).
* Contradiction engine respects ``provenance_policy`` by default;
  override works.

The Oracle FastAPI surface lives in ``current_events_api.routes.oracle``
— a separate package. We add it to ``sys.path`` so the test runs
under the noosphere test session (the prompt scope places this test
file in ``noosphere/tests/``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the current_events_api package importable from the noosphere
# test session. Mirrors what the FastAPI conftest does in the other
# direction.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CURRENT_EVENTS_API = _REPO_ROOT / "current_events_api"
if str(_CURRENT_EVENTS_API) not in sys.path:
    sys.path.insert(0, str(_CURRENT_EVENTS_API))

from current_events_api.routes.oracle import (  # noqa: E402
    OracleAnswer,
    OracleQuery,
    ProvenanceFilter,
)
from noosphere.coherence.contradiction_scheduler import (  # noqa: E402
    DEFAULT_PROVENANCE_POLICY,
    PERMISSIVE_PROVENANCE_POLICY,
    ProvenancePolicy,
    _pair_allowed_by_policy,
)
from noosphere.models import Artifact, ProvenanceKind  # noqa: E402
from noosphere.store import Store  # noqa: E402


# ── ProvenanceFilter shape + defaults ───────────────────────────────────────


def test_provenance_filter_defaults_match_prompt() -> None:
    pf = ProvenanceFilter()
    # Checkboxes default ON for proprietary + endorsed only.
    assert pf.include_proprietary is True
    assert pf.include_endorsed_external is True
    assert pf.include_studied_external is False
    assert pf.include_opposing_external is False
    # Weights: proprietary 2×, endorsed 1×, studied 0.5×, opposing 0.1×.
    assert pf.proprietary_weight == 2.0
    assert pf.endorsed_external_weight == 1.0
    assert pf.studied_external_weight == 0.5
    assert pf.opposing_external_weight == 0.1


def test_included_kinds_excludes_unchecked() -> None:
    pf = ProvenanceFilter()
    kinds = pf.included_kinds()
    assert ProvenanceKind.PROPRIETARY in kinds
    assert ProvenanceKind.ENDORSED_EXTERNAL in kinds
    assert ProvenanceKind.STUDIED_EXTERNAL not in kinds
    assert ProvenanceKind.OPPOSING_EXTERNAL not in kinds


def test_included_kinds_respects_opt_in() -> None:
    pf = ProvenanceFilter(
        include_proprietary=False,
        include_endorsed_external=False,
        include_studied_external=True,
        include_opposing_external=True,
    )
    kinds = pf.included_kinds()
    assert kinds == [
        ProvenanceKind.STUDIED_EXTERNAL,
        ProvenanceKind.OPPOSING_EXTERNAL,
    ]


def test_weights_dict_returns_active_weights_in_declared_order() -> None:
    """Synthesizer logging contract: weights are returned in the same
    order they're declared in the filter (proprietary → opposing).
    """
    pf = ProvenanceFilter(
        include_proprietary=True,
        include_endorsed_external=True,
        include_studied_external=True,
        include_opposing_external=True,
    )
    keys = list(pf.weights_dict().keys())
    assert keys == [
        "PROPRIETARY",
        "ENDORSED_EXTERNAL",
        "STUDIED_EXTERNAL",
        "OPPOSING_EXTERNAL",
    ]


def test_weight_for_returns_per_kind_weight() -> None:
    pf = ProvenanceFilter()
    assert pf.weight_for(ProvenanceKind.PROPRIETARY) == 2.0
    assert pf.weight_for(ProvenanceKind.ENDORSED_EXTERNAL) == 1.0
    assert pf.weight_for(ProvenanceKind.STUDIED_EXTERNAL) == 0.5
    assert pf.weight_for(ProvenanceKind.OPPOSING_EXTERNAL) == 0.1


# ── End-to-end through the FastAPI Oracle route ─────────────────────────────


@pytest.fixture()
def oracle_client(tmp_path, monkeypatch):
    """Spin up the Currents FastAPI app pointed at a fresh sqlite DB."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'oracle.db'}")
    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("THESEUS_SKIP_BOOT_CHECK", "1")
    from fastapi.testclient import TestClient

    from current_events_api.main import app

    with TestClient(app) as client:
        yield client


def _seed_corpus(store: Store) -> None:
    """One artifact per provenance kind so the route has something to return."""
    store.put_artifact(Artifact(id="art_prop", title="firm memo"))
    store.put_artifact(
        Artifact(
            id="art_end",
            title="Thiel essay",
            provenance=ProvenanceKind.ENDORSED_EXTERNAL,
            provenance_rationale="canonical statement of the monopoly thesis we share",
        )
    )
    store.put_artifact(
        Artifact(
            id="art_studied",
            title="Strauss reader",
            provenance=ProvenanceKind.STUDIED_EXTERNAL,
            provenance_rationale="useful reference for adversarial reasoning patterns",
        )
    )
    store.put_artifact(
        Artifact(
            id="art_opposing",
            title="Land piece",
            provenance=ProvenanceKind.OPPOSING_EXTERNAL,
            provenance_rationale="material we want to be able to argue against fluently",
        )
    )


def test_provenance_counts_endpoint_returns_one_row_per_kind(
    oracle_client, monkeypatch, tmp_path
) -> None:
    # Seed the store the route will read.
    from current_events_api.deps import make_store

    store = make_store()
    _seed_corpus(store)
    res = oracle_client.get("/v1/oracle/provenance-counts")
    assert res.status_code == 200
    rows = res.json()
    assert {r["provenance"] for r in rows} == {
        "PROPRIETARY",
        "ENDORSED_EXTERNAL",
        "STUDIED_EXTERNAL",
        "OPPOSING_EXTERNAL",
    }
    by_kind = {r["provenance"]: r["count"] for r in rows}
    assert by_kind["PROPRIETARY"] == 1
    assert by_kind["ENDORSED_EXTERNAL"] == 1
    assert by_kind["STUDIED_EXTERNAL"] == 1
    assert by_kind["OPPOSING_EXTERNAL"] == 1


def test_oracle_ask_excludes_unchecked_provenance(oracle_client) -> None:
    from current_events_api.deps import make_store

    store = make_store()
    _seed_corpus(store)

    # Defaults: proprietary + endorsed only.
    res = oracle_client.post(
        "/v1/oracle/ask",
        json={"question": "what do we believe about monopolies?"},
    )
    assert res.status_code == 200
    data = res.json()
    sources = {s["id"] for s in data["sources"]}
    assert sources == {"art_prop", "art_end"}
    assert set(data["active_provenance_kinds"]) == {
        "PROPRIETARY",
        "ENDORSED_EXTERNAL",
    }
    # Proprietary is weighted 2× so it sorts first.
    assert data["sources"][0]["id"] == "art_prop"
    assert data["sources"][0]["weight"] == 2.0
    assert data["sources"][1]["weight"] == 1.0


def test_oracle_ask_includes_opt_in_kinds(oracle_client) -> None:
    from current_events_api.deps import make_store

    store = make_store()
    _seed_corpus(store)
    res = oracle_client.post(
        "/v1/oracle/ask",
        json={
            "question": "argue against Land",
            "provenance_filter": {
                "include_proprietary": False,
                "include_endorsed_external": False,
                "include_studied_external": True,
                "include_opposing_external": True,
            },
        },
    )
    assert res.status_code == 200
    data = res.json()
    sources = {s["id"] for s in data["sources"]}
    assert sources == {"art_studied", "art_opposing"}


def test_oracle_ask_rejects_empty_filter(oracle_client) -> None:
    res = oracle_client.post(
        "/v1/oracle/ask",
        json={
            "question": "x",
            "provenance_filter": {
                "include_proprietary": False,
                "include_endorsed_external": False,
                "include_studied_external": False,
                "include_opposing_external": False,
            },
        },
    )
    assert res.status_code == 400


# ── Contradiction scheduler policy ──────────────────────────────────────────


def test_default_policy_blocks_studied_against_proprietary() -> None:
    assert _pair_allowed_by_policy(
        ProvenanceKind.PROPRIETARY,
        ProvenanceKind.PROPRIETARY,
        DEFAULT_PROVENANCE_POLICY,
    ) is True
    assert _pair_allowed_by_policy(
        ProvenanceKind.PROPRIETARY,
        ProvenanceKind.ENDORSED_EXTERNAL,
        DEFAULT_PROVENANCE_POLICY,
    ) is True
    assert _pair_allowed_by_policy(
        ProvenanceKind.PROPRIETARY,
        ProvenanceKind.STUDIED_EXTERNAL,
        DEFAULT_PROVENANCE_POLICY,
    ) is False
    assert _pair_allowed_by_policy(
        ProvenanceKind.PROPRIETARY,
        ProvenanceKind.OPPOSING_EXTERNAL,
        DEFAULT_PROVENANCE_POLICY,
    ) is False


def test_default_policy_blocks_pure_external_pairs() -> None:
    """Two non-proprietary kinds are excluded by default — the firm
    doesn't want to spend cycles checking Thiel vs. Strauss for
    contradictions.
    """
    assert _pair_allowed_by_policy(
        ProvenanceKind.ENDORSED_EXTERNAL,
        ProvenanceKind.STUDIED_EXTERNAL,
        DEFAULT_PROVENANCE_POLICY,
    ) is False


def test_permissive_policy_overrides_block() -> None:
    """The operator override (cost monitor surface from prompt 07) lifts
    the gate so every pair is testable.
    """
    for a in ProvenanceKind:
        for b in ProvenanceKind:
            assert _pair_allowed_by_policy(
                a, b, PERMISSIVE_PROVENANCE_POLICY
            ) is True


def test_custom_policy_can_widen_one_kind_only() -> None:
    """The policy is a structured override, not a binary on/off. The
    operator can re-include just OPPOSING_EXTERNAL without also
    enabling pure-external pairs.
    """
    widened = ProvenancePolicy(
        allowed_against_proprietary=frozenset(
            {
                ProvenanceKind.PROPRIETARY,
                ProvenanceKind.ENDORSED_EXTERNAL,
                ProvenanceKind.OPPOSING_EXTERNAL,
            }
        )
    )
    assert _pair_allowed_by_policy(
        ProvenanceKind.PROPRIETARY,
        ProvenanceKind.OPPOSING_EXTERNAL,
        widened,
    ) is True
    # STUDIED is still blocked — the operator only widened OPPOSING.
    assert _pair_allowed_by_policy(
        ProvenanceKind.PROPRIETARY,
        ProvenanceKind.STUDIED_EXTERNAL,
        widened,
    ) is False
    # Pure-external pairs remain blocked.
    assert _pair_allowed_by_policy(
        ProvenanceKind.ENDORSED_EXTERNAL,
        ProvenanceKind.OPPOSING_EXTERNAL,
        widened,
    ) is False
