"""End-to-end integration tests for the quarterly self-critique pass.

The unit-level behaviour of the reviewer, scheduler and addendum
lifecycle is covered by ``test_self_critique.py``. This file exercises
the *integration* the operational harness depends on — Round 17 prompt
43 wired together with the prompt-30 signed-publication path:

1. **Library pipeline.** ``run_quarterly_self_critique`` over a real
   :class:`Store`: a stub judge produces findings, findings land in the
   founder attention queue as high-severity ``ReviewItem`` rows, and
   ``addend`` findings convert into pending :class:`Addendum` rows
   without touching the original article body.
2. **Signed addenda.** An addendum is itself a signed publication: it
   round-trips through ``sign_publication`` / ``verify_signature`` and a
   tampered addendum body is rejected.
3. **The harness.** ``noosphere/scripts/run_self_critique_pass.sh`` run
   as a subprocess against a seeded SQLite store — it inventories
   articles older than the threshold, never double-runs an article
   recorded in a prior run's manifest, writes the triage memo + addendum
   candidates, and gates cleanly when no judge is wired.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from noosphere.ledger.canonicalize import PublicationCanonicalInput
from noosphere.ledger.publication_signing import (
    PublicationKeyring,
    sign_publication,
    verify_signature,
)
from noosphere.models import PublishedConclusion
from noosphere.peer_review.scheduler_self_critique import (
    PublishedArticle,
    run_quarterly_self_critique,
)
from noosphere.peer_review.self_critique import (
    SelfCritiqueAction,
    SelfCritiqueReviewer,
    SelfCritiqueVerdict,
    addendum_from_finding,
    publish_addendum,
)
from noosphere.store import Store

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "noosphere" / "scripts" / "run_self_critique_pass.sh"


# ── Helpers ────────────────────────────────────────────────────────────


def _article(article_id: str, *, slug: str, published_days_ago: int) -> PublishedArticle:
    now = datetime.now(timezone.utc)
    return PublishedArticle(
        article_id=article_id,
        title=f"Article {article_id}",
        body=f"The thesis of {article_id} rests on a five-year horizon.",
        slug=slug,
        published_at=now - timedelta(days=published_days_ago),
    )


def _stub_judge(article_id, article_text, reviewer_config, then, now):
    """Deterministic judge: one ``addend`` finding per article.

    ``reviewer_config`` must be non-empty — the harness always rotates a
    config off the original review before constructing the reviewer.
    """
    assert reviewer_config, "self-critique must run with a non-empty config"
    return [
        {
            "claim": f"Load-bearing claim of {article_id}.",
            "was_supported_by": ["src:original"],
            "now_supported_by": ["src:post-publication"],
            "verdict": "weakened",
            "recommended_action": "addend",
            "rationale": "New evidence narrows the claim; a dated addendum is due.",
        }
    ]


def _seed_published_conclusion(
    store: Store,
    *,
    article_id: str,
    slug: str,
    published_days_ago: int,
    body: str = "",
) -> None:
    """Insert one PublishedConclusion row the harness can inventory."""
    published_at = datetime.now(timezone.utc) - timedelta(days=published_days_ago)
    payload = {
        "schema": "theseus.publicConclusion.v1",
        "conclusionText": body or f"The thesis of {slug} rests on a five-year horizon.",
        "topicHint": f"Topic for {slug}",
    }
    row = PublishedConclusion(
        id=article_id,
        organization_id="org-test",
        source_conclusion_id=f"src-{article_id}",
        slug=slug,
        version=1,
        kind="ARTICLE",
        discounted_confidence=0.6,
        stated_confidence=0.75,
        calibration_discount_reason="",
        payload_json=json.dumps(payload),
        doi="",
        zenodo_record_id="",
        published_at=published_at,
    )
    with store.session() as s:
        s.add(row)
        s.commit()


def _run_harness(tmp_path: Path, db_path: Path, *, stamp: str, judge: str,
                 runs_dir: Path) -> subprocess.CompletedProcess:
    key_dir = tmp_path / f"keyring-{stamp}"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
        # Defang the other URL fallbacks so a stray env var can't redirect
        # the harness off the seeded test database.
        "THESEUS_DATABASE_URL": "",
        "THESEUS_CODEX_DATABASE_URL": "",
        "CODEX_DATABASE_URL": "",
        "DIRECT_URL": "",
    }
    return subprocess.run(
        [
            "bash",
            str(HARNESS),
            "--judge",
            judge,
            "--stamp",
            stamp,
            "--runs-dir",
            str(runs_dir),
            "--key-dir",
            str(key_dir),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


# ── 1. Library pipeline ────────────────────────────────────────────────


def test_quarterly_pass_queues_findings_and_drafts_addenda(tmp_path: Path):
    """The pass runs the reviewer, lands findings in the attention queue,
    and ``addend`` findings convert to pending addenda — all without
    mutating the original article body."""
    store = Store.from_database_url("sqlite:///:memory:")
    old = _article("art-old", slug="old-thesis", published_days_ago=200)
    older = _article("art-older", slug="older-thesis", published_days_ago=400)
    young = _article("art-young", slug="young-thesis", published_days_ago=10)
    original_body = old.body

    reviewer = SelfCritiqueReviewer(
        judge_fn=_stub_judge, reviewer_config="self-critique:provmix-openai-lead"
    )
    results = run_quarterly_self_critique(
        [old, older, young], reviewer=reviewer, store=store
    )

    # The young article is below the 90-day threshold — never reviewed.
    reviewed_ids = {r.article.article_id for r in results}
    assert reviewed_ids == {"art-old", "art-older"}

    # Every finding landed in the unified attention queue.
    queued = store.list_open_review_items()
    assert len(queued) == 2
    assert all(item.status == "open" for item in queued)
    assert {item.claim_a_id for item in queued} == {"art-old", "art-older"}

    # ``addend`` findings convert to pending addenda; the original body
    # is never referenced by the addendum.
    report = results[0].report
    addend_findings = [
        f for f in report.findings
        if f.recommended_action is SelfCritiqueAction.ADDEND
    ]
    assert addend_findings
    addendum = addendum_from_finding(
        addend_findings[0],
        article_id=old.article_id,
        article_slug=old.slug,
        reviewer_config=report.reviewer_config,
    )
    assert addendum.status.value == "pending"
    assert original_body not in addendum.body
    assert old.body == original_body  # immutable through the pass

    published = publish_addendum(addendum)
    assert published.status.value == "published"
    assert published.published_at is not None


def test_pass_carries_rotated_config_through_to_the_report(tmp_path: Path):
    """The reviewer config — rotated off the original review — must be
    recorded on the report so the firm can prove, after the fact, that
    self-critique did not reuse the publication swarm's configuration."""
    store = Store.from_database_url("sqlite:///:memory:")
    article = _article("art-1", slug="thesis", published_days_ago=180)
    rotated = "self-critique:promptvar-B"
    reviewer = SelfCritiqueReviewer(judge_fn=_stub_judge, reviewer_config=rotated)

    results = run_quarterly_self_critique([article], reviewer=reviewer, store=store)
    assert len(results) == 1
    assert results[0].report.reviewer_config == rotated


# ── 2. Signed addenda (prompt 30 round-trip) ───────────────────────────


def test_addendum_signature_round_trip_on_synthetic_article(tmp_path: Path):
    """A published addendum is itself a signed publication: it must
    round-trip through the prompt-30 signing path, and a tampered
    addendum body must fail verification."""
    finding_addendum = addendum_from_finding(
        # Build a finding indirectly via a reviewer so the shape is real.
        SelfCritiqueReviewer(
            judge_fn=_stub_judge, reviewer_config="self-critique:provmix-google-lead"
        )
        .review(
            article_id="synthetic",
            article_text="Synthetic article body.",
            original_evidence_at_publish_time=[],
            evidence_now=[],
        )
        .findings[0],
        article_id="synthetic",
        article_slug="synthetic-article",
    )

    canonical = PublicationCanonicalInput(
        slug="synthetic-article-addendum-1",
        version=1,
        conclusion_text=finding_addendum.body,
        published_at=finding_addendum.created_at,
    )
    keyring = PublicationKeyring(tmp_path / "publication-keys")
    keyring.ensure()

    sig = sign_publication(canonical, keyring)
    ok = verify_signature(sig, keyring, live_input=canonical)
    assert ok.ok, ok.issues
    assert sig.canonical_hash == canonical.hash_hex()

    tampered = PublicationCanonicalInput(
        slug=canonical.slug,
        version=canonical.version,
        conclusion_text=canonical.conclusion_text + "\n\n[tampered after signing]",
        published_at=finding_addendum.created_at,
    )
    bad = verify_signature(sig, keyring, live_input=tampered)
    assert not bad.ok
    assert any("hash mismatch" in i for i in bad.issues)


# ── 3. The operational harness ─────────────────────────────────────────


def test_harness_runs_end_to_end_with_stub_judge(tmp_path: Path):
    """The harness inventories, runs, triages, drafts addenda, and
    verifies the signing path — end to end against a seeded store."""
    db_path = tmp_path / "store.db"
    store = Store.from_database_url(f"sqlite:///{db_path}")
    # Article ids chosen so the stub judge's deterministic bucket lands
    # on each verdict: art-0007 -> dismiss, art-0000 -> addend,
    # art-0001 -> revise. A young article must be excluded entirely.
    _seed_published_conclusion(store, article_id="art-0007",
                               slug="still-holds-thesis", published_days_ago=200)
    _seed_published_conclusion(store, article_id="art-0000",
                               slug="weakened-thesis", published_days_ago=300)
    _seed_published_conclusion(store, article_id="art-0001",
                               slug="contradicted-thesis", published_days_ago=400)
    _seed_published_conclusion(store, article_id="art-young",
                               slug="young-thesis", published_days_ago=10)

    runs_dir = tmp_path / "runs"
    stamp = "20260514T000000Z"
    proc = _run_harness(tmp_path, db_path, stamp=stamp, judge="stub", runs_dir=runs_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    memo = runs_dir / f"self_critique_{stamp}.md"
    assert memo.exists()
    text = memo.read_text()
    for section in (
        "## A. Pre-flight",
        "## B. Inventory",
        "## C. Run",
        "## D. Triage",
        "## E. Addendum candidates",
        "## F. Signed-publication path",
        "## Cost report",
    ):
        assert section in text, f"missing section: {section}"

    # Inventory: three eligible, one young article excluded.
    assert "art-0007" in text
    assert "art-0000" in text
    assert "art-0001" in text
    assert "art-young" not in text

    # The signing round-trip is wired and passes.
    assert "synthetic addendum signature round-trip: yes" in text
    assert "tampered addendum correctly rejected: yes" in text

    # The manifest is the de-dup ledger for future runs.
    manifest = json.loads((runs_dir / f"self_critique_{stamp}" / "manifest.json").read_text())
    assert {a["article_id"] for a in manifest["articles"]} == {
        "art-0007", "art-0000", "art-0001",
    }

    # The ``weakened`` article produced an addendum candidate file.
    addenda_dir = runs_dir / f"self_critique_{stamp}" / "addenda"
    addendum_file = addenda_dir / "weakened-thesis.md"
    assert addendum_file.exists()
    addendum_text = addendum_file.read_text()
    assert "Addendum candidate" in addendum_text
    assert "signed-publication path" in addendum_text

    # Cost report carries a per-article breakdown and a non-zero total.
    assert "total LLM spend this pass:" in text
    assert "prompt tok" in text


def test_harness_does_not_double_run_articles_from_a_prior_manifest(tmp_path: Path):
    """An article recorded in a prior run's manifest is cross-referenced
    and skipped — the pass never double-runs an article."""
    db_path = tmp_path / "store.db"
    store = Store.from_database_url(f"sqlite:///{db_path}")
    _seed_published_conclusion(store, article_id="art-0000",
                               slug="weakened-thesis", published_days_ago=300)
    _seed_published_conclusion(store, article_id="art-0001",
                               slug="contradicted-thesis", published_days_ago=400)

    runs_dir = tmp_path / "runs"
    # A prior run already critiqued art-0000.
    prior_dir = runs_dir / "self_critique_20260101T000000Z"
    prior_dir.mkdir(parents=True)
    (prior_dir / "manifest.json").write_text(json.dumps({
        "stamp": "20260101T000000Z",
        "articles": [{"article_id": "art-0000", "slug": "weakened-thesis",
                      "status": "reviewed"}],
    }))

    stamp = "20260514T010000Z"
    proc = _run_harness(tmp_path, db_path, stamp=stamp, judge="stub", runs_dir=runs_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    manifest = json.loads((runs_dir / f"self_critique_{stamp}" / "manifest.json").read_text())
    critiqued = {a["article_id"] for a in manifest["articles"]}
    assert critiqued == {"art-0001"}  # art-0000 skipped as a prior-run duplicate

    text = (runs_dir / f"self_critique_{stamp}.md").read_text()
    assert "already critiqued by a prior run (skipped, not double-run): **1**" in text


def test_harness_gates_run_when_no_judge_is_wired(tmp_path: Path):
    """With articles pending and ``--judge gate``, the harness must not
    silently produce an empty pass — it exits 4 and the memo records
    every pending article as deferred."""
    db_path = tmp_path / "store.db"
    store = Store.from_database_url(f"sqlite:///{db_path}")
    _seed_published_conclusion(store, article_id="art-0000",
                               slug="weakened-thesis", published_days_ago=300)

    runs_dir = tmp_path / "runs"
    stamp = "20260514T020000Z"
    proc = _run_harness(tmp_path, db_path, stamp=stamp, judge="gate", runs_dir=runs_dir)
    assert proc.returncode == 4, proc.stdout + proc.stderr

    text = (runs_dir / f"self_critique_{stamp}.md").read_text()
    assert "Run incomplete" in text
    assert "deferred" in text
    # The signing path is still verified even when the run defers.
    assert "synthetic addendum signature round-trip: yes" in text


def test_harness_handles_an_empty_corpus(tmp_path: Path):
    """A store with no articles older than the threshold is a clean
    PASS — the machinery works, the corpus just is not old enough yet."""
    db_path = tmp_path / "store.db"
    store = Store.from_database_url(f"sqlite:///{db_path}")
    _seed_published_conclusion(store, article_id="art-young",
                               slug="young-thesis", published_days_ago=5)

    runs_dir = tmp_path / "runs"
    stamp = "20260514T030000Z"
    proc = _run_harness(tmp_path, db_path, stamp=stamp, judge="stub", runs_dir=runs_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    text = (runs_dir / f"self_critique_{stamp}.md").read_text()
    assert "older than 90 days (eligible): **0**" in text
    assert "synthetic addendum signature round-trip: yes" in text
