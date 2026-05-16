"""Prompt 09 — Provenance demarcation tests (model + store + ingestion + CLI).

Each test covers one row from the prompt's K-block test checklist:

* Upload helper persists each provenance choice correctly.
* Provenance propagates from artifact to derived rows.
* External provenance requires a ≥30-character rationale.
* The agent cannot change provenance without an explicit caller
  (i.e. no inference path; only the store helper / CLI moves it).
* Migration backfill: rows that don't set provenance land at
  PROPRIETARY.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from noosphere.ingestion import apply_upload_provenance
from noosphere.models import (
    PROVENANCE_RATIONALE_MIN_LEN,
    Artifact,
    Claim,
    ClaimType,
    Conclusion,
    InputSourceType,
    ProvenanceKind,
    Speaker,
    coerce_provenance,
    validate_provenance_rationale,
)
from noosphere.store import Store


_EXTERNAL_KINDS = (
    ProvenanceKind.ENDORSED_EXTERNAL,
    ProvenanceKind.STUDIED_EXTERNAL,
    ProvenanceKind.OPPOSING_EXTERNAL,
)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _speaker() -> Speaker:
    return Speaker(id="spk_1", name="Founder", role="founder")


# ── A. enum + helpers ───────────────────────────────────────────────────────


def test_provenance_kind_is_a_closed_set_of_four() -> None:
    assert {k.value for k in ProvenanceKind} == {
        "PROPRIETARY",
        "ENDORSED_EXTERNAL",
        "STUDIED_EXTERNAL",
        "OPPOSING_EXTERNAL",
    }


def test_coerce_provenance_defaults_to_proprietary() -> None:
    assert coerce_provenance(None) == ProvenanceKind.PROPRIETARY
    assert coerce_provenance("") == ProvenanceKind.PROPRIETARY
    assert coerce_provenance("nonsense") == ProvenanceKind.PROPRIETARY
    assert coerce_provenance("endorsed_external") == ProvenanceKind.ENDORSED_EXTERNAL


@pytest.mark.parametrize("kind", _EXTERNAL_KINDS)
def test_external_provenance_requires_rationale_min_length(kind: ProvenanceKind) -> None:
    with pytest.raises(ValueError):
        validate_provenance_rationale(kind, "")
    with pytest.raises(ValueError):
        validate_provenance_rationale(kind, "too short")
    long_enough = "x" * PROVENANCE_RATIONALE_MIN_LEN
    assert validate_provenance_rationale(kind, long_enough) == long_enough


def test_proprietary_does_not_require_rationale() -> None:
    assert validate_provenance_rationale(ProvenanceKind.PROPRIETARY, "") == ""
    assert (
        validate_provenance_rationale(ProvenanceKind.PROPRIETARY, "anything")
        == "anything"
    )


# ── B. ingestion helper stamps the founder's choice ─────────────────────────


@pytest.mark.parametrize(
    "kind",
    list(ProvenanceKind),
)
def test_apply_upload_provenance_stamps_artifact(kind: ProvenanceKind) -> None:
    artifact = Artifact(id="a_1", title="t")
    rationale = "x" * 40 if kind in _EXTERNAL_KINDS else ""
    apply_upload_provenance(artifact, provenance=kind, rationale=rationale)
    assert artifact.provenance == kind
    assert artifact.provenance_rationale == rationale


def test_apply_upload_provenance_rejects_external_without_rationale() -> None:
    artifact = Artifact(id="a_1")
    with pytest.raises(ValueError):
        apply_upload_provenance(
            artifact,
            provenance=ProvenanceKind.ENDORSED_EXTERNAL,
            rationale="too short",
        )


def test_apply_upload_provenance_rejects_unknown_kind() -> None:
    artifact = Artifact(id="a_1")
    with pytest.raises(ValueError):
        apply_upload_provenance(artifact, provenance="NEUTRAL", rationale="")


# ── C. round-trip through the store ─────────────────────────────────────────


@pytest.mark.parametrize("kind", list(ProvenanceKind))
def test_artifact_round_trip_preserves_provenance(kind: ProvenanceKind) -> None:
    store = _store()
    rationale = "thiel's essay maps onto our monopoly thesis closely" if (
        kind in _EXTERNAL_KINDS
    ) else ""
    artifact = Artifact(
        id=f"a_{kind.value}",
        uri="memo.md",
        title=f"Memo {kind.value}",
        author="founder",
        source_date=date(2026, 5, 1),
        provenance=kind,
        provenance_rationale=rationale,
    )
    store.put_artifact(artifact)
    fetched = store.get_artifact(artifact.id)
    assert fetched is not None
    assert fetched.provenance == kind
    assert fetched.provenance_rationale == rationale


def test_set_artifact_provenance_round_trip() -> None:
    """CLI / triage path: re-tag an existing row."""
    store = _store()
    artifact = Artifact(id="a_retag", title="legacy upload")
    store.put_artifact(artifact)
    assert store.get_artifact("a_retag").provenance == ProvenanceKind.PROPRIETARY

    ok = store.set_artifact_provenance(
        "a_retag",
        "ENDORSED_EXTERNAL",
        rationale="founder marked this Thiel essay as canonical for our thesis",
    )
    assert ok is True
    after = store.get_artifact("a_retag")
    assert after.provenance == ProvenanceKind.ENDORSED_EXTERNAL
    assert "Thiel" in after.provenance_rationale


def test_set_artifact_provenance_rejects_external_without_rationale() -> None:
    store = _store()
    store.put_artifact(Artifact(id="a_retag2", title="legacy"))
    with pytest.raises(ValueError):
        store.set_artifact_provenance("a_retag2", "OPPOSING_EXTERNAL", rationale="too short")


def test_set_artifact_provenance_missing_id_returns_false() -> None:
    assert _store().set_artifact_provenance("nope", "PROPRIETARY") is False


# ── D. propagation to derived rows ──────────────────────────────────────────


@pytest.mark.parametrize("kind", list(ProvenanceKind))
def test_claim_persists_provenance(kind: ProvenanceKind) -> None:
    store = _store()
    claim = Claim(
        id=f"c_{kind.value}",
        text="t",
        speaker=_speaker(),
        episode_id="ep_1",
        episode_date=date(2026, 5, 1),
        source_type=InputSourceType.WRITTEN,
        claim_type=ClaimType.FACTUAL,
        provenance=kind,
    )
    store.put_claim(claim)
    rows = store.list_claims_by_provenance({kind.value})
    assert any(c.id == claim.id for c in rows)
    # Excluding the kind hides the claim.
    other_kinds = {k.value for k in ProvenanceKind} - {kind.value}
    excluded = store.list_claims_by_provenance(other_kinds)
    assert not any(c.id == claim.id for c in excluded)


@pytest.mark.parametrize("kind", list(ProvenanceKind))
def test_conclusion_persists_provenance(kind: ProvenanceKind) -> None:
    store = _store()
    conclusion = Conclusion(
        id=f"k_{kind.value}",
        text="conclusion",
        provenance=kind,
    )
    store.put_conclusion(conclusion)
    rows = store.list_conclusions_by_provenance({kind.value})
    assert any(c.id == conclusion.id for c in rows)


# ── E. migration backfill ───────────────────────────────────────────────────


def test_existing_rows_default_to_proprietary() -> None:
    """A row inserted without an explicit provenance lands at PROPRIETARY.

    This is the post-migration invariant: every legacy artifact is
    tagged PROPRIETARY and surfaces in the founder triage queue.
    """
    store = _store()
    artifact = Artifact(id="legacy", title="from before prompt 09")
    store.put_artifact(artifact)
    fetched = store.get_artifact("legacy")
    assert fetched.provenance == ProvenanceKind.PROPRIETARY
    assert fetched.provenance_rationale == ""
    # And it shows up in the triage list.
    untagged = store.list_untagged_artifacts()
    assert any(a.id == "legacy" for a in untagged)


def test_count_artifacts_by_provenance_returns_full_breakdown() -> None:
    store = _store()
    store.put_artifact(Artifact(id="p_1", provenance=ProvenanceKind.PROPRIETARY))
    store.put_artifact(
        Artifact(
            id="e_1",
            provenance=ProvenanceKind.ENDORSED_EXTERNAL,
            provenance_rationale="founder endorsed this thiel essay as ours-in-spirit",
        )
    )
    counts = store.count_artifacts_by_provenance()
    assert counts["PROPRIETARY"] == 1
    assert counts["ENDORSED_EXTERNAL"] == 1
    assert counts["STUDIED_EXTERNAL"] == 0
    assert counts["OPPOSING_EXTERNAL"] == 0


# ── F. agent cannot infer provenance ────────────────────────────────────────


def test_no_inference_path_changes_provenance() -> None:
    """An artifact's provenance is set only by upload-time tagging or by the
    explicit store helper. Re-saving the same artifact with mutated content
    must not flip provenance back to PROPRIETARY.
    """
    store = _store()
    artifact = Artifact(
        id="immutable",
        title="endorsed",
        provenance=ProvenanceKind.ENDORSED_EXTERNAL,
        provenance_rationale="founder said this thiel essay represents our thinking",
    )
    store.put_artifact(artifact)
    # Simulate the ingester re-processing the same artifact: it edits
    # the title and re-saves. Provenance must NOT decay back to default.
    artifact.title = "endorsed (rev2)"
    store.put_artifact(artifact)
    after = store.get_artifact("immutable")
    assert after.provenance == ProvenanceKind.ENDORSED_EXTERNAL
    assert after.title == "endorsed (rev2)"
