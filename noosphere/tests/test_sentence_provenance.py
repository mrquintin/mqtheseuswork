"""Tests for the per-sentence provenance assembler.

What we care about:

1. Cascade walk picks up artifact-level supports edges and the
   aggregated provenance respects the credibility cap (weak sources
   pile-on cannot manufacture strong evidence).
2. Sentence anchoring: a sentence with ``[S1]`` reads its weight from
   that source's contribution; a sentence with no marker inherits the
   conclusion's overall provenance.
3. Privacy: ``report.public()`` strips identifying detail for private
   sources but preserves the aggregate number — the firm is honest
   about its evidence base.
4. Round-trip: the report serialises and reloads byte-for-byte (used
   by snapshot tests on the front end).
5. Performance: a synthetic 5,000-word article assembles inside the
   25KB-gzipped budget.
"""

from __future__ import annotations

import gzip
import json
import uuid as _uuid
from datetime import date, datetime, timezone

import pytest

from noosphere.cascade.graph import CascadeGraph
from noosphere.cascade.sentence_provenance import (
    ArticleCitationLink,
    SCHEMA,
    SentenceProvenanceReport,
    assemble_sentence_provenance,
    labels_in_sentence,
    split_sentences,
)
from noosphere.literature.source_credibility import (
    CredibilityEventKind,
    CredibilityOutcome,
    CredibilityUpdate,
    InMemoryCredibilityLedger,
)
from noosphere.literature.source_priors import SourceType
from noosphere.models import (
    Artifact,
    CascadeEdgeRelation,
    CascadeNodeKind,
    Claim,
    Conclusion,
    ConfidenceTier,
    MethodInvocation,
    Speaker,
)
from noosphere.store import Store


def _uid() -> str:
    return str(_uuid.uuid4())


def _now() -> datetime:
    return datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


@pytest.fixture
def fixture(store: Store):
    """Conclusion supported by two artifacts via two claims, plus a
    third cited artifact reachable directly. Two of the artifacts are
    public (high credibility); one is a private internal note (no
    ledger, falls back to neutral 0.5)."""
    inv = MethodInvocation(
        id=_uid(),
        method_id="method:test",
        input_hash="ih",
        output_hash="oh",
        started_at=_now(),
        ended_at=_now(),
        succeeded=True,
        error_kind=None,
        correlation_id=_uid(),
        tenant_id="t1",
    )
    store.insert_method_invocation(inv)

    artifacts = []
    for slug in ("alpha", "beta", "gamma"):
        a = Artifact(
            id=_uid(),
            uri=f"https://example.com/{slug}",
            mime_type="text/html",
            title=f"{slug.title()} report",
            author="A. Researcher",
            source_date=date(2026, 1, 4),
            created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
        )
        store.put_artifact(a)
        artifacts.append(a)

    conclusion = Conclusion(
        id=_uid(),
        text="Therefore X.",
        rationale="Combine alpha, beta, gamma.",
        confidence_tier=ConfidenceTier.MODERATE,
        evidence_chain_claim_ids=[],
        confidence=0.72,
        created_at=datetime(2026, 1, 7, tzinfo=timezone.utc),
    )
    store.put_conclusion(conclusion)

    graph = CascadeGraph(store)

    # Wire each artifact directly into the conclusion via a supports
    # edge whose src is the artifact's cascade node id and whose dst is
    # the conclusion id.
    artifact_node_ids = []
    for a, base_conf in zip(artifacts, (0.9, 0.8, 0.5)):
        nid = graph.add_node(kind=CascadeNodeKind.ARTIFACT, ref=a.id)
        artifact_node_ids.append(nid)
        graph.add_edge(
            src=nid,
            dst=conclusion.id,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=base_conf,
        )

    # Credibility ledger: two confirmations on alpha (high credibility)
    # and one failure on beta (medium-low credibility); gamma absent
    # (unknown source → neutral 0.5).
    ledger = InMemoryCredibilityLedger()
    for outcome in (CredibilityOutcome.CONFIRMATION, CredibilityOutcome.CONFIRMATION):
        ledger.append(
            CredibilityUpdate(
                source_id=artifacts[0].id,
                outcome=outcome,
                weight=1.0,
                kind=CredibilityEventKind.FORECAST_RESOLUTION,
                conclusion_id=conclusion.id,
                observed_at=_now(),
            )
        )
    ledger.append(
        CredibilityUpdate(
            source_id=artifacts[1].id,
            outcome=CredibilityOutcome.FAILURE,
            weight=1.0,
            kind=CredibilityEventKind.RETRACTION,
            conclusion_id=conclusion.id,
            observed_at=_now(),
        )
    )

    return {
        "conclusion": conclusion,
        "artifacts": artifacts,
        "ledger": ledger,
        "inv": inv,
    }


def test_split_and_marker_extraction():
    body = (
        "This is the first sentence [S1]. The second one cites "
        "[S2] and [S1] together! Third sentence has no markers."
    )
    sents = split_sentences(body)
    assert len(sents) == 3
    assert labels_in_sentence(sents[0]) == ["S1"]
    assert labels_in_sentence(sents[1]) == ["S2", "S1"]
    assert labels_in_sentence(sents[2]) == []


def test_uncited_sentence_inherits_conclusion_provenance(store, fixture):
    body = "An uncited framing sentence opens the article."
    citations = [
        ArticleCitationLink(label="S1", source_kind="upload", source_id=a.id)
        for a in fixture["artifacts"]
    ]
    report = assemble_sentence_provenance(
        store=store,
        conclusion_id=fixture["conclusion"].id,
        body_markdown=body,
        citations=citations,
        ledger=fixture["ledger"],
    )
    assert len(report.sentences) == 1
    assert report.sentences[0].source_labels == []
    # Sentence inherits the overall — they must match exactly.
    assert report.sentences[0].provenance == pytest.approx(report.overall_provenance)
    assert 0.0 <= report.overall_provenance <= 1.0


def test_per_sentence_anchoring_and_credibility_cap(store, fixture):
    artifacts = fixture["artifacts"]
    citations = [
        ArticleCitationLink(label=f"S{i+1}", source_kind="upload", source_id=a.id)
        for i, a in enumerate(artifacts)
    ]
    body = (
        "Strong claim [S1] should land near the alpha credibility. "
        "Mixed claim cites [S2] only and should sit lower. "
        "Three-source claim spans [S1] [S2] [S3] but cannot exceed alpha."
    )
    report = assemble_sentence_provenance(
        store=store,
        conclusion_id=fixture["conclusion"].id,
        body_markdown=body,
        citations=citations,
        ledger=fixture["ledger"],
    )

    sents = report.sentences
    assert [s.source_labels for s in sents] == [["S1"], ["S2"], ["S1", "S2", "S3"]]

    s1_strength = report.sources["S1"].effective
    s2_strength = report.sources["S2"].effective
    s3_strength = report.sources["S3"].effective
    assert s1_strength > s3_strength > s2_strength  # alpha > gamma (0.5) > beta (post-failure)

    # Sentence 0 reads alpha alone. Effective = base × credibility.
    assert sents[0].provenance == pytest.approx(s1_strength, rel=1e-6)

    # Sentence 1 reads beta alone.
    assert sents[1].provenance == pytest.approx(s2_strength, rel=1e-6)

    # Sentence 2 pools all three; must not exceed the max credibility
    # contributor (alpha). This is the "weak evidence pile-on" cap.
    max_credibility = max(c.credibility for c in report.sources.values())
    assert sents[2].provenance <= max_credibility + 1e-9


def test_public_projection_drops_private_identity_but_keeps_aggregate(store, fixture):
    artifacts = fixture["artifacts"]
    citations = [
        ArticleCitationLink(label="S1", source_kind="upload", source_id=artifacts[0].id),
        ArticleCitationLink(
            label="S2",
            source_kind="upload",
            source_id=artifacts[1].id,
            public=False,  # private
        ),
    ]
    body = "Sentence one cites public [S1]. Sentence two cites private [S2]."
    report = assemble_sentence_provenance(
        store=store,
        conclusion_id=fixture["conclusion"].id,
        body_markdown=body,
        citations=citations,
        ledger=fixture["ledger"],
    )
    pub = report.public()

    # The private source's identity is gone from sources.
    assert "S1" in pub.sources
    assert "S2" not in pub.sources

    # The aggregate per-sentence number is preserved (the firm is
    # honest about its evidence base).
    assert pub.sentences[1].provenance == pytest.approx(report.sentences[1].provenance)
    # The label list no longer mentions the private source.
    assert pub.sentences[1].source_labels == []
    # …but private_source_count rises so the reader can see the
    # sentence rests on something redacted, without identifying it.
    assert pub.sentences[1].private_source_count >= 1

    # The serialisation must not contain the private source id.
    blob = pub.model_dump_json()
    assert artifacts[1].id not in blob


def test_report_round_trips_through_json(store, fixture):
    citations = [
        ArticleCitationLink(label=f"S{i+1}", source_kind="upload", source_id=a.id)
        for i, a in enumerate(fixture["artifacts"])
    ]
    body = "Round-trip sentence [S1]. Another sentence [S2]."
    report = assemble_sentence_provenance(
        store=store,
        conclusion_id=fixture["conclusion"].id,
        body_markdown=body,
        citations=citations,
        ledger=fixture["ledger"],
    )
    blob = report.model_dump_json(by_alias=True)
    parsed = json.loads(blob)
    assert parsed["schema"] == SCHEMA
    reloaded = SentenceProvenanceReport.model_validate_json(blob)
    assert reloaded.model_dump(by_alias=True) == report.model_dump(by_alias=True)


def test_5000_word_article_fits_within_25kb_gzipped(store, fixture):
    """Perf budget: a 5,000-word synthetic article must serialise to
    no more than 25KB gzipped. The heatmap data ships with the article
    HTML, so we cannot afford to bloat first paint."""
    citations = [
        ArticleCitationLink(label=f"S{i+1}", source_kind="upload", source_id=a.id)
        for i, a in enumerate(fixture["artifacts"])
    ]
    # 5,000 words = ~250 sentences of ~20 words each, half cited.
    parts = []
    for i in range(250):
        sentence_words = " ".join(
            f"word{i}_{j}" for j in range(20)
        )
        marker = f" [S{(i % 3) + 1}]" if i % 2 == 0 else ""
        parts.append(f"{sentence_words}{marker}.")
    body = " ".join(parts)
    assert len(body.split()) >= 5000

    report = assemble_sentence_provenance(
        store=store,
        conclusion_id=fixture["conclusion"].id,
        body_markdown=body,
        citations=citations,
        ledger=fixture["ledger"],
    )
    blob = report.public().model_dump_json(by_alias=True)
    gz = gzip.compress(blob.encode("utf-8"))
    assert len(gz) <= 25 * 1024, f"provenance payload too large: {len(gz)} bytes"
