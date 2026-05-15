"""Integration tests for the principle distillation run path.

Covers the pieces `run_principle_distillation.sh` wires together that the
unit tests in ``test_principle_distillation.py`` do not:

  * the LLM cost cap actually gating cluster drafting;
  * queue-level auto-merge of candidates that paraphrase an accepted
    principle;
  * ``sync_drafts_to_codex`` writing the founder triage queue (and only
    the queue — never an accepted / public-visible row);
  * the founder triage memo the prompted agent produces instead of
    accepting on the founder's behalf;
  * ``recompute_conviction_for_accepted`` propagating a conclusion
    retraction up into principle conviction;
  * the whole chain end to end against a SQLite Codex.

The Codex side runs through ``codex_bridge._open_codex_connection`` with
a ``sqlite://`` URL — the same shim the ingest pipeline tests use — so
the ``%s`` placeholders and dict rows behave exactly as they do against
the real Postgres.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from noosphere.codex_bridge import _open_codex_connection
from noosphere.distillation import (
    DraftPrinciple,
    PrincipleDistillationPipeline,
    PrincipleStatus,
    auto_merge_against_accepted,
    build_triage_memo,
    compute_conviction,
    recompute_conviction_for_accepted,
    sync_drafts_to_codex,
)
from noosphere.models import Conclusion, Discipline

ORG = "org_principles"


# ── Codex fixtures ───────────────────────────────────────────────────────────


_SCHEMA = """
CREATE TABLE "Organization" (
  id TEXT PRIMARY KEY,
  slug TEXT,
  name TEXT
);
CREATE TABLE "Conclusion" (
  id TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  text TEXT NOT NULL,
  "confidenceTier" TEXT NOT NULL DEFAULT 'moderate',
  "embeddingJson" TEXT,
  "createdAt" TEXT
);
CREATE TABLE "Principle" (
  id TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  text TEXT NOT NULL,
  "domainsJson" TEXT NOT NULL DEFAULT '[]',
  "clusterConclusionIds" TEXT NOT NULL DEFAULT '[]',
  "citedConclusionIds" TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'draft',
  "triageReason" TEXT NOT NULL DEFAULT '',
  "mergedIntoId" TEXT,
  "convictionScore" REAL NOT NULL DEFAULT 0.0,
  "domainBreadth" INTEGER NOT NULL DEFAULT 0,
  "clusterCentroidSimilarity" REAL NOT NULL DEFAULT 0.0,
  "publicVisible" INTEGER NOT NULL DEFAULT 0,
  "driftReason" TEXT,
  "reviewedByFounderId" TEXT,
  "createdAt" TEXT,
  "updatedAt" TEXT,
  "reviewedAt" TEXT,
  "publishedAt" TEXT
);
"""


@pytest.fixture
def codex_url(tmp_path: Path) -> str:
    """A throwaway SQLite Codex seeded with the principle-relevant tables."""
    path = tmp_path / "codex.db"
    setup = sqlite3.connect(str(path))
    setup.executescript(_SCHEMA)
    setup.execute(
        'INSERT INTO "Organization" (id, slug, name) VALUES (?, ?, ?)',
        (ORG, "principles-org", "Principles Org"),
    )
    setup.commit()
    setup.close()
    return f"sqlite://{path}"


def _insert_conclusion(
    url: str,
    cid: str,
    text: str,
    *,
    tier: str = "firm",
    embedding: list[float] | None = None,
) -> None:
    conn = _open_codex_connection(url)
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO "Conclusion" '
        '(id, "organizationId", text, "confidenceTier", "embeddingJson", '
        '"createdAt") VALUES (%s, %s, %s, %s, %s, %s)',
        (
            cid,
            ORG,
            text,
            tier,
            json.dumps(embedding) if embedding is not None else None,
            "2026-05-14T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()


def _insert_accepted_principle(
    url: str,
    pid: str,
    text: str,
    *,
    cluster_ids: list[str],
    domain_breadth: int,
    centroid: float,
    conviction: float,
) -> None:
    conn = _open_codex_connection(url)
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO "Principle" '
        '(id, "organizationId", text, "domainsJson", "clusterConclusionIds", '
        '"citedConclusionIds", status, "convictionScore", "domainBreadth", '
        '"clusterCentroidSimilarity", "publicVisible", "createdAt", '
        '"updatedAt") '
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            pid,
            ORG,
            text,
            json.dumps(["AI", "Philosophy"][:domain_breadth] or ["AI"]),
            json.dumps(cluster_ids),
            json.dumps(cluster_ids[:1]),
            PrincipleStatus.ACCEPTED,
            conviction,
            domain_breadth,
            centroid,
            1,
            "2026-05-01T00:00:00+00:00",
            "2026-05-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()


def _fetch_principles(url: str) -> list[dict[str, Any]]:
    conn = _open_codex_connection(url)
    cur = conn.cursor()
    cur.execute('SELECT * FROM "Principle" WHERE "organizationId" = %s', (ORG,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── Pipeline stubs ───────────────────────────────────────────────────────────


class _StubEmbedder:
    """Deterministic embedder: each text emits a hand-set vector."""

    def __init__(self, vectors_by_text: dict[str, list[float]]) -> None:
        self._vectors = vectors_by_text

    @property
    def model_name(self) -> str:
        return "stub"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [list(self._vectors[t]) for t in texts]


class _StubDistiller:
    """Stand-in for PrincipleDistiller; clusters by the vector's label dim."""

    def __init__(self, drafted: dict[tuple[str, ...], dict[str, Any]]) -> None:
        self._drafted = drafted
        self.draft_calls = 0

    def cluster_conclusions(
        self, *, conclusions, embeddings, clustering_threshold, min_cluster_size
    ):
        groups: dict[int, list[int]] = {}
        for i, v in enumerate(embeddings):
            groups.setdefault(int(v[0]), []).append(i)
        return [g for g in groups.values() if len(g) >= min_cluster_size]

    def draft_principle_for_conclusions(self, cluster):
        self.draft_calls += 1
        key = tuple(c.id for c in cluster)
        return self._drafted.get(key)


def _concl(cid: str, text: str, disciplines: list[Discipline]) -> Conclusion:
    return Conclusion(id=cid, text=text, disciplines=disciplines)


def _three_cluster_corpus() -> tuple[list[Conclusion], _StubEmbedder, _StubDistiller]:
    """Three 4-conclusion clusters, each spanning two domains."""
    conclusions: list[Conclusion] = []
    vectors: dict[str, list[float]] = {}
    drafted: dict[tuple[str, ...], dict[str, Any]] = {}
    for label in range(3):
        ids = []
        for member in range(4):
            cid = f"c{label}_{member}"
            text = f"cluster {label} conclusion {member}"
            disc = Discipline.AI if member % 2 == 0 else Discipline.PHILOSOPHY
            conclusions.append(_concl(cid, text, [disc]))
            vectors[text] = [float(label), 0.9 + member * 0.01]
            ids.append(cid)
        drafted[tuple(ids)] = {
            "text": f"Principle distilled from cluster {label}.",
            "domains": ["AI", "Philosophy"],
            "cited_conclusion_ids": ids[:2],
        }
    return conclusions, _StubEmbedder(vectors), _StubDistiller(drafted)


# ── A. Cost cap ──────────────────────────────────────────────────────────────


def test_cost_cap_gates_cluster_drafting() -> None:
    conclusions, embedder, distiller = _three_cluster_corpus()
    # Uncapped: all three clusters drafted.
    uncapped = PrincipleDistillationPipeline(
        distiller=distiller,
        embedder=embedder,
        clustering_threshold=0.5,
        min_cluster_size=4,
        min_domain_breadth=2,
    )
    drafts = uncapped.run(conclusions)
    assert len(drafts) == 3
    assert uncapped.budget_exhausted is False
    assert uncapped.estimated_cost_usd > 0.0

    per_cluster = uncapped.estimated_cost_usd / 3.0

    # Cap that admits exactly one cluster's draft call.
    _, embedder2, distiller2 = _three_cluster_corpus()
    capped = PrincipleDistillationPipeline(
        distiller=distiller2,
        embedder=embedder2,
        clustering_threshold=0.5,
        min_cluster_size=4,
        min_domain_breadth=2,
        cost_cap_usd=per_cluster * 1.5,
    )
    capped_drafts = capped.run(conclusions)
    assert len(capped_drafts) == 1
    assert capped.budget_exhausted is True
    assert capped.clusters_skipped_for_budget == 2
    # The cap is honored: the LLM was only invoked for the drafted cluster.
    assert distiller2.draft_calls == 1
    assert capped.estimated_cost_usd <= capped.cost_cap_usd


# ── B. Auto-merge ────────────────────────────────────────────────────────────


def test_auto_merge_folds_paraphrase_of_accepted_principle() -> None:
    accepted = [
        {"id": "prn_accepted", "text": "Calibration beats coverage."},
    ]
    paraphrase = DraftPrinciple(
        text="The firm prefers calibration over coverage.",
        domains=["AI", "Philosophy"],
        cited_conclusion_ids=["c1"],
        cluster_conclusion_ids=["c1", "c2", "c3", "c4"],
        conviction_score=0.5,
        domain_breadth=2,
        cluster_centroid_similarity=0.9,
    )
    distinct = DraftPrinciple(
        text="Adversarial review surfaces hidden assumptions.",
        domains=["AI", "Epistemology"],
        cited_conclusion_ids=["c5"],
        cluster_conclusion_ids=["c5", "c6", "c7", "c8"],
        conviction_score=0.6,
        domain_breadth=2,
        cluster_centroid_similarity=0.9,
    )
    # Embed the paraphrase identically to the accepted principle, the
    # distinct draft orthogonally.
    embedder = _StubEmbedder(
        {
            "Calibration beats coverage.": [1.0, 0.0],
            "The firm prefers calibration over coverage.": [1.0, 0.02],
            "Adversarial review surfaces hidden assumptions.": [0.0, 1.0],
        }
    )
    merged = auto_merge_against_accepted(
        [paraphrase, distinct],
        accepted_principles=accepted,
        embedder=embedder,
        paraphrase_threshold=0.92,
    )
    assert merged == 1
    assert paraphrase.status == PrincipleStatus.MERGED
    assert paraphrase.merged_into_id == "prn_accepted"
    assert distinct.status == PrincipleStatus.DRAFT
    assert distinct.merged_into_id is None


# ── C. Codex sync ────────────────────────────────────────────────────────────


def _queue_drafts() -> list[DraftPrinciple]:
    draft = DraftPrinciple(
        text="A queued draft principle.",
        domains=["AI", "Philosophy"],
        cited_conclusion_ids=["c1"],
        cluster_conclusion_ids=["c1", "c2", "c3", "c4"],
        conviction_score=0.62,
        domain_breadth=2,
        cluster_centroid_similarity=0.88,
    )
    rereview = DraftPrinciple(
        text="A re-review draft principle.",
        domains=["AI", "Economics"],
        cited_conclusion_ids=["c5"],
        cluster_conclusion_ids=["c5", "c6", "c7", "c8"],
        conviction_score=0.71,
        domain_breadth=2,
        cluster_centroid_similarity=0.9,
        status=PrincipleStatus.NEEDS_REREVIEW,
        existing_principle_id="prn_old",
        drift_reason="cluster_grew",
    )
    merged = DraftPrinciple(
        text="A paraphrase of an accepted principle.",
        domains=["AI"],
        cited_conclusion_ids=["c9"],
        cluster_conclusion_ids=["c9", "c10", "c11", "c12"],
        conviction_score=0.4,
        domain_breadth=1,
        cluster_centroid_similarity=0.8,
        status=PrincipleStatus.MERGED,
        merged_into_id="prn_accepted",
    )
    return [draft, rereview, merged]


def test_sync_writes_only_the_queue(codex_url: str) -> None:
    conn = _open_codex_connection(codex_url)
    counts = sync_drafts_to_codex(
        conn, organization_id=ORG, drafts=_queue_drafts()
    )
    conn.close()
    assert counts["inserted"] == 3
    assert counts["draft"] == 1
    assert counts["needs_rereview"] == 1
    assert counts["merged"] == 1

    rows = _fetch_principles(codex_url)
    assert len(rows) == 3
    # Nothing the sync writes is published — that is a founder action.
    for row in rows:
        assert row["status"] in (
            PrincipleStatus.DRAFT,
            PrincipleStatus.NEEDS_REREVIEW,
            PrincipleStatus.MERGED,
        )
        assert not row["publicVisible"]
        assert row["reviewedAt"] is None
        assert row["reviewedByFounderId"] is None
        assert row["publishedAt"] is None

    by_status = {r["status"]: r for r in rows}
    assert by_status[PrincipleStatus.MERGED]["mergedIntoId"] == "prn_accepted"
    assert by_status[PrincipleStatus.NEEDS_REREVIEW]["driftReason"] == "cluster_grew"
    assert "cluster_grew" in by_status[PrincipleStatus.NEEDS_REREVIEW]["triageReason"]

    # The triage-queue read (draft + needs_rereview) sees two rows.
    queued = [
        r
        for r in rows
        if r["status"]
        in (PrincipleStatus.DRAFT, PrincipleStatus.NEEDS_REREVIEW)
    ]
    assert len(queued) == 2


def test_sync_refreshes_unreviewed_drafts_but_keeps_founder_actions(
    codex_url: str,
) -> None:
    conn = _open_codex_connection(codex_url)
    sync_drafts_to_codex(conn, organization_id=ORG, drafts=_queue_drafts())
    conn.close()

    # Founder accepts the plain draft (simulated): it must survive a re-sync.
    conn = _open_codex_connection(codex_url)
    cur = conn.cursor()
    cur.execute(
        'UPDATE "Principle" SET status = %s, "reviewedAt" = %s '
        'WHERE "organizationId" = %s AND status = %s',
        (
            PrincipleStatus.ACCEPTED,
            "2026-05-14T01:00:00+00:00",
            ORG,
            PrincipleStatus.DRAFT,
        ),
    )
    conn.commit()
    conn.close()

    # Re-run distillation → sync again.
    conn = _open_codex_connection(codex_url)
    counts = sync_drafts_to_codex(
        conn, organization_id=ORG, drafts=_queue_drafts()
    )
    conn.close()
    # No stale unreviewed drafts existed (the only draft was accepted).
    assert counts["deleted_stale"] == 0

    rows = _fetch_principles(codex_url)
    statuses = sorted(r["status"] for r in rows)
    # accepted (kept) + needs_rereview x2 + merged x2 + draft x1
    assert statuses.count(PrincipleStatus.ACCEPTED) == 1
    assert statuses.count(PrincipleStatus.DRAFT) == 1


# ── D. Triage memo ───────────────────────────────────────────────────────────


def test_build_triage_memo_is_advisory_and_complete() -> None:
    drafts = _queue_drafts()
    conclusions_by_id = {
        "c1": _concl("c1", "Underlying conclusion one.", [Discipline.AI]),
        "c2": _concl("c2", "Underlying conclusion two.", [Discipline.PHILOSOPHY]),
        "c5": _concl("c5", "Re-review underlying conclusion.", [Discipline.AI]),
    }
    accepted = [{"id": "prn_accepted", "text": "Calibration beats coverage."}]
    memo = build_triage_memo(
        run_stamp="20260514T120000Z",
        run_kind="provider-backed",
        corpus_label="firm-corpus",
        drafts=drafts,
        conclusions_by_id=conclusions_by_id,
        accepted_principles=accepted,
        pipeline_stats={
            "corpus_size": 12,
            "clusters": 3,
            "estimated_cost_usd": 0.027,
            "cost_cap_usd": 1.0,
            "budget_exhausted": False,
        },
    )
    # Header + the agent-does-not-accept guarantee.
    assert "# Principle Distillation — Founder Triage Memo" in memo
    assert "agent does not accept principles" in memo
    assert "run_kind: provider-backed" in memo
    # Every queued candidate's text appears.
    assert "A queued draft principle." in memo
    assert "A re-review draft principle." in memo
    # Underlying conclusions are reachable from the memo.
    assert "Underlying conclusion one." in memo
    assert "`c1`" in memo
    # A recommendation is attached to each candidate.
    assert "Recommendation — propose accept" in memo
    assert "Recommendation — propose re-accept" in memo
    # The merged candidate is recorded but not queued for triage.
    assert "Auto-merged candidates" in memo
    assert "A paraphrase of an accepted principle." in memo
    # The memo explains how to act — in the UI, not via the agent.
    assert "/principles/queue" in memo
    assert "/methodology/principles" in memo


def test_build_triage_memo_offline_preamble() -> None:
    memo = build_triage_memo(
        run_stamp="20260514T120000Z",
        run_kind="distill-offline-deterministic",
        corpus_label="verification-corpus",
        drafts=[],
        conclusions_by_id={},
    )
    assert "offline deterministic distiller" in memo
    assert "No candidates this pass" in memo


# ── E. Conviction recomputation ──────────────────────────────────────────────


def test_recompute_conviction_propagates_retraction(codex_url: str) -> None:
    cluster_ids = ["k1", "k2", "k3", "k4"]
    # Four conclusions, each with a real embedding so the centroid is
    # recomputed rather than read from the stored value.
    embeddings = {
        "k1": [1.0, 0.0, 0.0],
        "k2": [0.9, 0.1, 0.0],
        "k3": [0.0, 1.0, 0.0],
        "k4": [0.1, 0.9, 0.0],
    }
    for cid, vec in embeddings.items():
        _insert_conclusion(codex_url, cid, f"conclusion {cid}", embedding=vec)

    baseline = compute_conviction(
        cluster_size=4, domain_breadth=2, centrality_scores=[0.85] * 4
    )
    _insert_accepted_principle(
        codex_url,
        "prn_live",
        "A live accepted principle.",
        cluster_ids=cluster_ids,
        domain_breadth=2,
        centroid=0.85,
        conviction=baseline,
    )

    # Retract one underlying conclusion.
    conn = _open_codex_connection(codex_url)
    cur = conn.cursor()
    cur.execute('DELETE FROM "Conclusion" WHERE id = %s', ("k4",))
    conn.commit()
    conn.close()

    conn = _open_codex_connection(codex_url)
    changes = recompute_conviction_for_accepted(conn, organization_id=ORG)
    conn.close()

    assert len(changes) == 1
    change = changes[0]
    assert change["id"] == "prn_live"
    assert change["cluster_before"] == 4
    assert change["cluster_after"] == 3
    # A shrunken cluster cannot score higher than the full one.
    assert change["after"] < change["before"]

    rows = {r["id"]: r for r in _fetch_principles(codex_url)}
    assert rows["prn_live"]["convictionScore"] == pytest.approx(change["after"])


def test_recompute_conviction_noop_when_corpus_unchanged(codex_url: str) -> None:
    cluster_ids = ["s1", "s2", "s3", "s4"]
    for cid in cluster_ids:
        _insert_conclusion(
            codex_url, cid, f"conclusion {cid}", embedding=[1.0, 0.0]
        )
    # Conviction stored consistently with a 4-member, centroid≈1.0 cluster.
    conviction = compute_conviction(
        cluster_size=4, domain_breadth=2, centrality_scores=[1.0] * 4
    )
    _insert_accepted_principle(
        codex_url,
        "prn_stable",
        "A stable accepted principle.",
        cluster_ids=cluster_ids,
        domain_breadth=2,
        centroid=1.0,
        conviction=conviction,
    )
    conn = _open_codex_connection(codex_url)
    changes = recompute_conviction_for_accepted(conn, organization_id=ORG)
    conn.close()
    assert changes == []


# ── F. End to end ────────────────────────────────────────────────────────────


def test_distillation_run_to_queue_end_to_end(codex_url: str) -> None:
    conclusions, embedder, distiller = _three_cluster_corpus()
    pipeline = PrincipleDistillationPipeline(
        distiller=distiller,
        embedder=embedder,
        clustering_threshold=0.5,
        min_cluster_size=4,
        min_domain_breadth=2,
    )
    drafts = pipeline.run(conclusions)
    assert len(drafts) == 3

    # An accepted principle that one cluster's draft paraphrases.
    accepted = [
        {
            "id": "prn_accepted",
            "text": "Principle distilled from cluster 0.",
        }
    ]
    merge_embedder = _StubEmbedder(
        {
            "Principle distilled from cluster 0.": [1.0, 0.0],
            "Principle distilled from cluster 1.": [0.0, 1.0],
            "Principle distilled from cluster 2.": [0.0, -1.0],
        }
    )
    merged = auto_merge_against_accepted(
        drafts,
        accepted_principles=accepted,
        embedder=merge_embedder,
        paraphrase_threshold=0.92,
    )
    assert merged == 1

    # Sync the whole pass to the Codex queue.
    conn = _open_codex_connection(codex_url)
    counts = sync_drafts_to_codex(conn, organization_id=ORG, drafts=drafts)
    conn.close()
    assert counts["inserted"] == 3
    assert counts["merged"] == 1
    assert counts["draft"] == 2

    rows = _fetch_principles(codex_url)
    queued = [r for r in rows if r["status"] == PrincipleStatus.DRAFT]
    assert len(queued) == 2

    # The triage memo the agent produces — advisory, complete, no writes.
    conclusions_by_id = {c.id: c for c in conclusions}
    memo = build_triage_memo(
        run_stamp="20260514T120000Z",
        run_kind="distill-offline-deterministic",
        corpus_label="verification-corpus",
        drafts=drafts,
        conclusions_by_id=conclusions_by_id,
        accepted_principles=accepted,
        pipeline_stats={
            "corpus_size": len(conclusions),
            "clusters": 3,
            "estimated_cost_usd": pipeline.estimated_cost_usd,
            "cost_cap_usd": pipeline.cost_cap_usd,
            "budget_exhausted": pipeline.budget_exhausted,
        },
    )
    assert "Principle distilled from cluster 1." in memo
    assert "Auto-merged candidates" in memo

    # Conviction recompute is a no-op here (no accepted rows in the DB yet),
    # but it must run cleanly against the freshly-synced queue.
    conn = _open_codex_connection(codex_url)
    changes = recompute_conviction_for_accepted(conn, organization_id=ORG)
    conn.close()
    assert changes == []
