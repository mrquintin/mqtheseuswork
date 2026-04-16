"""Performance regression on a medium synthetic graph (subset of full archive)."""

from __future__ import annotations

import os
import time
from datetime import date

import pytest

from noosphere.config import get_settings
from noosphere.models import Claim, ConvictionLevel, Principle, Speaker
from noosphere.ontology import GraphPersistence, OntologyGraph
from noosphere.orchestrator import NoosphereOrchestrator
from noosphere.store import Store
from noosphere.synthesis import run_synthesis_pipeline


def _build_graph(n_principles: int) -> OntologyGraph:
    g = OntologyGraph()
    spk = Speaker(name="p")
    dim = 8
    for i in range(n_principles):
        cid_a, cid_b = f"c_{i}_a", f"c_{i}_b"
        emb = [0.0] * dim
        emb[i % dim] = 1.0
        t_short = "Hi."
        t_long = (
            f"Principle {i} methodological cluster text with distinct token salad "
            f"alpha_{i} beta_{i} gamma_{i} to satisfy meta compressibility heuristics."
        )
        g.add_claim(
            Claim(
                id=cid_a,
                text=t_short,
                speaker=spk,
                episode_id="perf",
                episode_date=date(2026, 4, 14),
                embedding=list(emb),
            )
        )
        g.add_claim(
            Claim(
                id=cid_b,
                text=t_long,
                speaker=spk,
                episode_id="perf",
                episode_date=date(2026, 4, 14),
                embedding=list(emb),
            )
        )
        g.add_principle(
            Principle(
                id=f"p_{i}",
                text=f"Distilled methodological rule number {i} for performance subset.",
                conviction=ConvictionLevel.MODERATE,
                conviction_score=0.72,
                embedding=list(emb),
                supporting_claims=[cid_a, cid_b],
                mention_count=2,
            )
        )
    return g


@pytest.mark.skipif(os.environ.get("THESEUS_SKIP_PERF") == "1", reason="THESEUS_SKIP_PERF=1")
def test_synthesis_subset_wall_clock(tmp_path, monkeypatch):
    monkeypatch.setenv("THESEUS_DATABASE_URL", f"sqlite:///{(tmp_path / 'p.db').resolve()}")
    monkeypatch.setenv("THESEUS_DATA_DIR", str(tmp_path.resolve()))
    monkeypatch.setenv("THESEUS_SYNTHESIS_MAX_WORKERS", os.environ.get("THESEUS_SYNTHESIS_MAX_WORKERS", "4"))
    get_settings.cache_clear()

    g = _build_graph(28)
    GraphPersistence(g).save_to_json(str(tmp_path / "graph.json"))

    store = Store.from_database_url(get_settings().database_url)
    orch = NoosphereOrchestrator(str(tmp_path.resolve()))

    t0 = time.perf_counter()
    n = run_synthesis_pipeline(orch, store=store).persisted_count
    elapsed = time.perf_counter() - t0

    assert n >= 1
    assert elapsed < 180.0, f"synthesis over subset took {elapsed:.1f}s (budget 180s)"

    get_settings.cache_clear()
