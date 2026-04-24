"""Phase 4: temporal stance series, meta gates, synthesis assembly, founder view."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np

from noosphere.conclusions import ConclusionsRegistry
from noosphere.founders import compute_founder_intellectual_view
from noosphere.meta_analysis import ClaimClusterMeta, evaluate_five_meta_criteria
from noosphere.models import Claim, DriftEvent, FounderProfile, Speaker
from noosphere.ontology import OntologyGraph
from noosphere.store import Store
from noosphere.temporal import (
    build_stance_embedding_series,
    compute_drift_velocity_acceleration,
    detect_drift_events_zscore,
    surface_drift_events,
)


def _topic_resolver(topic: str):
    return lambda _c: topic


def test_stance_series_velocity_and_surface() -> None:
    t0 = date(2024, 1, 1)
    base = np.array([1.0, 0.0, 0.0], dtype=float)
    claims: list[Claim] = []
    for i in range(8):
        v = (base + 0.12 * i * np.array([0.0, 1.0, 0.0])).tolist()
        claims.append(
            Claim(
                text=f"c{i}",
                speaker=Speaker(name="Alice"),
                episode_id="e1",
                episode_date=t0 + timedelta(days=i * 5),
                embedding=v,
            )
        )
    series = build_stance_embedding_series(
        claims,
        author_key="alice",
        topic_id="top1",
        topic_for_claim=_topic_resolver("top1"),
        window_days=6,
    )
    assert len(series) >= 1
    vel, acc = compute_drift_velocity_acceleration(series)
    assert isinstance(vel, list)
    detect_drift_events_zscore(series, z_threshold=10.0)  # likely empty at extreme threshold
    ev = surface_drift_events(
        series=series,
        raw_claims=claims,
        author_topic_key="alice|top1",
        topic_id="top1",
        z_threshold=0.0,
        llm_complete=None,
    )
    assert isinstance(ev, list)


def test_meta_domain_ceiling_fails() -> None:
    c = ClaimClusterMeta(
        claim_ids=["1", "2"],
        texts=["x is true beyond doubt", "y follows"],
        claimed_confidence=0.95,
        domain="normative_philosophy",
    )
    out = evaluate_five_meta_criteria(c)
    assert out.route_open_question or not out.passed_all


def test_synthesis_pipeline_empty_graph(tmp_path: Path) -> None:
    from noosphere.synthesis import run_synthesis_pipeline

    class O:
        graph = OntologyGraph()
        conclusions = ConclusionsRegistry(data_path=str(tmp_path / "c.json"))
        data_dir = tmp_path

    n = run_synthesis_pipeline(O(), store=Store.from_database_url("sqlite:///:memory:")).persisted_count
    assert n == 0


def test_founder_view_smoke() -> None:
    f = FounderProfile(name="Alice")
    claims = [
        Claim(
            text="p1",
            speaker=Speaker(name="Alice"),
            episode_id="e",
            episode_date=date(2024, 1, 1),
            embedding=[1.0, 0.0],
        ),
        Claim(
            text="p2 opposite",
            speaker=Speaker(name="Bob"),
            episode_id="e",
            episode_date=date(2024, 1, 2),
            embedding=[-0.99, 0.1],
        ),
    ]
    v = compute_founder_intellectual_view(
        founder=f,
        claims=claims,
        topic_for_claim=lambda c: "t1",
        drift_events=[
            DriftEvent(
                target_id="x",
                observed_at=date(2024, 1, 3),
                author_topic_key="alice",
            )
        ],
    )
    assert v.founder_id == f.id
    assert "t1" in v.positions_by_topic


def test_store_list_drift_events() -> None:
    st = Store.from_database_url("sqlite:///:memory:")
    e = DriftEvent(target_id="t", observed_at=date(2024, 2, 2), notes="n")
    st.put_drift_event(e)
    lst = st.list_drift_events(limit=10)
    assert len(lst) == 1
