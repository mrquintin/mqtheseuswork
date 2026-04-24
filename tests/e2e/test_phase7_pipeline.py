"""
End-to-end regression gate: clean SQLite, Dialectic-style ingest, synthesis assembly,
contradictions in graph, session-scoped research generation — wall clock < 10 minutes.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

import pytest

from noosphere.config import get_settings
from noosphere.ingest_artifacts import ingest_dialectic_session_jsonl
from noosphere.llm import MockLLMClient
from noosphere.models import Claim, ConvictionLevel, Principle, RelationType, Relationship, Speaker
from noosphere.observability import configure_logging
from noosphere.ontology import GraphPersistence, OntologyGraph
from noosphere.orchestrator import NoosphereOrchestrator
from noosphere.research_advisor import session_research
from noosphere.store import Store
from noosphere.synthesis import run_synthesis_pipeline


SESSION_ID = "e2e_dialectic_apr14"
DIM = 8


def _vec(axis: int, sign: float = 1.0) -> list[float]:
    v = [0.0] * DIM
    v[axis % DIM] = sign
    return v


def _write_graph(path: Path) -> None:
    spk = Speaker(name="founder_a")
    e1 = _vec(0, 1.0)
    e2 = _vec(0, 1.0)
    ed = _vec(0, -1.0)
    claims = [
        Claim(
            id="claim_e2e_s1",
            text="A.",
            speaker=spk,
            episode_id=SESSION_ID,
            episode_date=date(2026, 4, 14),
            embedding=e1,
        ),
        Claim(
            id="claim_e2e_s2",
            text=(
                "Organizational learning requires explicit falsification protocols in "
                "strategic planning cycles diverging substantially from intuition and "
                "repeated measurement cycles across temporal boundaries and cohorts."
            ),
            speaker=spk,
            episode_id=SESSION_ID,
            episode_date=date(2026, 4, 14),
            embedding=e2,
        ),
        Claim(
            id="claim_e2e_dissent",
            text="We should reject the prior framing entirely for unrelated reasons.",
            speaker=Speaker(name="founder_b"),
            episode_id=SESSION_ID,
            episode_date=date(2026, 4, 14),
            embedding=ed,
        ),
    ]
    centroid = e1
    pr_a = Principle(
        id="princ_e2e_a",
        text="Methods require empirical anchors before firm-level adoption.",
        conviction=ConvictionLevel.STRONG,
        conviction_score=0.75,
        embedding=centroid,
        supporting_claims=["claim_e2e_s1", "claim_e2e_s2"],
        mention_count=2,
    )
    pr_b = Principle(
        id="princ_e2e_b",
        text="Heuristic shortcuts dominate when time pressure exceeds measurement cost.",
        conviction=ConvictionLevel.MODERATE,
        conviction_score=0.55,
        embedding=_vec(1, 1.0),
        supporting_claims=[],
        mention_count=1,
    )
    rel = Relationship(
        id="rel_e2e_contra",
        source_id="princ_e2e_a",
        target_id="princ_e2e_b",
        relation=RelationType.CONTRADICTS,
        strength=0.9,
    )
    g = OntologyGraph()
    for c in claims:
        g.add_claim(c)
    g.add_principle(pr_a)
    g.add_principle(pr_b)
    g.add_relationship(rel)
    GraphPersistence(g).save_to_json(str(path / "graph.json"))


def _write_session_jsonl(path: Path) -> None:
    lines: list[str] = []
    for i in range(24):
        ts = (i * 1800) // 23
        lines.append(
            json.dumps(
                {
                    "text": f"Claim line {i} about methodological falsification and measurement.",
                    "speaker": "founder_a",
                    "timestamp": f"2026-04-14T{(ts // 3600):02d}:{((ts % 3600) // 60):02d}:00",
                    "timestamp_seconds": float(ts),
                    "episode_id": SESSION_ID,
                    "claim_id": f"claim_e2e_ts_{i}",
                }
            )
        )
    lines.append(
        json.dumps(
            {
                "text": "A.",
                "speaker": "founder_a",
                "episode_id": SESSION_ID,
                "claim_id": "claim_e2e_s1",
                "embedding": [float(x) for x in _vec(0, 1.0)],
            }
        )
    )
    lines.append(
        json.dumps(
            {
                "text": (
                    "Organizational learning requires explicit falsification protocols in "
                    "strategic planning cycles diverging substantially from intuition and "
                    "repeated measurement cycles across temporal boundaries and cohorts."
                ),
                "speaker": "founder_a",
                "episode_id": SESSION_ID,
                "claim_id": "claim_e2e_s2",
                "embedding": [float(x) for x in _vec(0, 1.0)],
            }
        )
    )
    lines.append(
        json.dumps(
            {
                "text": "We should reject the prior framing entirely for unrelated reasons.",
                "speaker": "founder_b",
                "episode_id": SESSION_ID,
                "claim_id": "claim_e2e_dissent",
                "embedding": [float(x) for x in _vec(0, -1.0)],
            }
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "e2e.db"
    monkeypatch.setenv("THESEUS_DATABASE_URL", f"sqlite:///{db_path.resolve()}")
    monkeypatch.setenv("THESEUS_DATA_DIR", str(tmp_path.resolve()))
    monkeypatch.setenv("THESEUS_LOG_FILE", "0")
    monkeypatch.setenv("THESEUS_SYNTHESIS_MAX_WORKERS", "1")
    get_settings.cache_clear()
    _write_graph(tmp_path)
    return tmp_path


def test_e2e_ingest_synthesis_contradiction_research_under_budget(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_logging(json_format=True, log_to_file=False)
    t0 = time.perf_counter()

    jsonl = isolated_env / "session.jsonl"
    _write_session_jsonl(jsonl)

    store = Store.from_database_url(get_settings().database_url)
    art, n = ingest_dialectic_session_jsonl(
        jsonl, store, episode_id=SESSION_ID, episode_date=date(2026, 4, 14)
    )
    assert n >= 3
    assert art.id

    orch = NoosphereOrchestrator(str(isolated_env.resolve()))
    assert len(orch.get_contradictions()) >= 1

    written = run_synthesis_pipeline(orch, store=store).persisted_count
    assert written >= 1
    conclusions = store.list_conclusions()
    assert len(conclusions) >= 1
    con_id = conclusions[0].id

    bundle = {
        "topics": [
            {
                "title": "Stress-test falsification norms",
                "rationale": "Ground next session in measurement cost.",
                "citing_claim_id": "claim_e2e_s1",
                "citing_open_question_or_conclusion_id": con_id,
            }
        ],
        "readings": [
            {
                "title": "How to Solve It",
                "author": "George Pólya",
                "rationale": "Heuristics vs measurement.",
                "citing_claim_id": "claim_e2e_s2",
                "citing_open_question_or_conclusion_id": con_id,
            }
        ],
    }

    monkeypatch.setattr(
        "noosphere.llm.llm_client_from_settings",
        lambda: MockLLMClient(responses=[json.dumps(bundle)]),
    )
    out = session_research(orch, session_id=SESSION_ID, generate=True)
    data = json.loads(out)
    assert len(data.get("topics", [])) >= 1
    assert len(data.get("readings", [])) >= 1

    elapsed = time.perf_counter() - t0
    assert elapsed < 600.0, f"pipeline took {elapsed:.1f}s (budget 600s)"

    get_settings.cache_clear()


def test_backup_roundtrip_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Backup/restore helpers produce a readable archive (subset of Phase 7)."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "graph.json").write_text('{"principles":[],"claims":[],"relationships":[]}', encoding="utf-8")
    dbfile = tmp_path / "store.db"
    dbfile.write_bytes(b"")

    monkeypatch.setenv("THESEUS_DATABASE_URL", f"sqlite:///{dbfile.resolve()}")
    monkeypatch.setenv("THESEUS_DATA_DIR", str(data.resolve()))
    get_settings.cache_clear()

    from noosphere.backup_restore import create_backup_archive, restore_backup_archive

    arch = create_backup_archive(output_dir=tmp_path / "out")
    assert arch.is_file()

    dest = tmp_path / "restore_here"
    dest.mkdir()
    monkeypatch.setenv("THESEUS_DATA_DIR", str(dest.resolve()))
    get_settings.cache_clear()
    restore_backup_archive(arch, force=True)
    assert (dest / "graph.json").is_file()

    get_settings.cache_clear()
