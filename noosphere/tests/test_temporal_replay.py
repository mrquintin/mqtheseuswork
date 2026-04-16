"""Temporal replay: effective-time filtering and synthesis dry-run."""

from __future__ import annotations

from datetime import date, datetime, timezone

from noosphere.models import Artifact, Claim, Conclusion, ConfidenceTier, Speaker
from noosphere.store import Store
from noosphere.synthesis import run_synthesis_pipeline
from noosphere.temporal_replay import (
    diff_belief_cutoffs,
    filter_claims_as_of,
    list_conclusions_replay_consistent,
)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def test_filter_claims_respects_superseded_and_effective() -> None:
    st = _store()
    d_old = date(2020, 1, 10)
    art = Artifact(
        id="art1",
        title="memo",
        source_date=d_old,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        effective_at_inferred=False,
    )
    st.put_artifact(art)
    c_ok = Claim(
        id="c1",
        text="long enough methodological claim text for any downstream consumer",
        speaker=Speaker(name="A"),
        episode_id="e1",
        episode_date=d_old,
        source_id="art1",
    )
    c_sup = Claim(
        id="c2",
        text="another methodological claim with sufficient length here",
        speaker=Speaker(name="B"),
        episode_id="e1",
        episode_date=d_old,
        source_id="art1",
        superseded_at=datetime(2019, 6, 1, tzinfo=timezone.utc),
    )
    st.put_claim(c_ok)
    st.put_claim(c_sup)
    as_of = date(2020, 6, 1)
    out = filter_claims_as_of(st, {"c1": c_ok, "c2": c_sup}, as_of)
    assert "c1" in out and "c2" not in out


def test_list_conclusions_replay_consistent_filters_evidence_and_time() -> None:
    st = _store()
    d = date(2021, 3, 1)
    art = Artifact(
        id="a2",
        title="doc",
        source_date=d,
        created_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
        effective_at_inferred=False,
    )
    st.put_artifact(art)
    c = Claim(
        id="ce1",
        text="methodological claim body with enough characters in total",
        speaker=Speaker(name="X"),
        episode_id="e",
        episode_date=d,
        source_id="a2",
    )
    st.put_claim(c)
    con_early = Conclusion(
        id="k1",
        text="early",
        confidence_tier=ConfidenceTier.FIRM,
        evidence_chain_claim_ids=["ce1"],
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    con_late = Conclusion(
        id="k2",
        text="late",
        confidence_tier=ConfidenceTier.FIRM,
        evidence_chain_claim_ids=["ce1"],
        created_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
    )
    st.put_conclusion(con_early)
    st.put_conclusion(con_late)
    visible = list_conclusions_replay_consistent(st, date(2021, 6, 1))
    ids = {x.id for x in visible}
    assert "k1" in ids and "k2" not in ids


def test_diff_belief_cutoffs() -> None:
    st = _store()
    da, db = date(2019, 1, 1), date(2022, 1, 1)
    diff = diff_belief_cutoffs(st, da, db)
    assert diff.date_a <= diff.date_b
    assert isinstance(diff.warnings, list)


def test_synthesis_pipeline_dry_run_returns_previews_not_persisting(tmp_path) -> None:
    from noosphere.conclusions import ConclusionsRegistry
    from noosphere.ontology import OntologyGraph

    class O:
        graph = OntologyGraph()
        conclusions = ConclusionsRegistry(data_path=str(tmp_path / "cr.json"))
        data_dir = tmp_path

    orch = O()
    st = Store.from_database_url(f"sqlite:///{tmp_path / 't.db'}")
    res = run_synthesis_pipeline(orch, store=st, dry_run=True)
    assert res.persisted_count == 0
    assert st.list_conclusions() == []
    assert isinstance(res.preview_conclusions, list)
