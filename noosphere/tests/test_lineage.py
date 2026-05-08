"""Lineage assembler tests on synthetic data.

Three properties we care about, captured one test apiece:

1. **Order stability** — the same store, queried twice, returns the
   exact same JSON bytes. Determinism here is what makes lineage
   citable in a research appendix.
2. **No private leakage** — `lineage.public()` drops private nodes
   without leaving redaction stubs. A reader of the public lineage
   must not be able to tell that private steps exist.
3. **Round-trip** — an exported lineage, re-loaded from JSON, equals
   the in-memory original.
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import date, datetime, timezone

import pytest

from noosphere.cascade.graph import CascadeGraph
from noosphere.models import (
    Artifact,
    CascadeEdgeRelation,
    Claim,
    Conclusion,
    ConfidenceTier,
    DriftEvent,
    Finding,
    MethodInvocation,
    ReviewReport,
    Speaker,
)
from noosphere.store import Store
from noosphere.temporal.lineage import (
    Lineage,
    LineageNodeKind,
    assemble_lineage,
    lineage_diff,
    lineage_to_markdown,
)


def _uid() -> str:
    return str(_uuid.uuid4())


def _now() -> datetime:
    return datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


@pytest.fixture
def synthetic(store: Store):
    """Conclusion with two source claims, a peer review, a private drift
    event, and cascade edges wiring them together."""
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

    artifact = Artifact(
        id=_uid(),
        uri="https://example.com/paper.pdf",
        mime_type="application/pdf",
        title="Paper on policy",
        author="A. Researcher",
        source_date=date(2026, 1, 4),
        created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    store.put_artifact(artifact)

    speaker = Speaker(name="Alice")
    claims: list[Claim] = []
    for i, text in enumerate(("Premise A.", "Premise B.")):
        c = Claim(
            id=_uid(),
            text=text,
            speaker=speaker,
            episode_id="ep_1",
            episode_date=date(2026, 1, 5 + i),
            source_id=artifact.id,
            effective_at=datetime(2026, 1, 5 + i, tzinfo=timezone.utc),
            confidence=0.9,
        )
        store.put_claim(c)
        claims.append(c)

    conclusion = Conclusion(
        id=_uid(),
        text="Therefore X.",
        rationale="Combine A and B.",
        confidence_tier=ConfidenceTier.MODERATE,
        evidence_chain_claim_ids=[c.id for c in claims],
        confidence=0.72,
        created_at=datetime(2026, 1, 7, tzinfo=timezone.utc),
    )
    store.put_conclusion(conclusion)

    graph = CascadeGraph(store)
    for claim in claims:
        claim_nid = graph.add_node(
            kind=__import__(
                "noosphere.models", fromlist=["CascadeNodeKind"]
            ).CascadeNodeKind.CLAIM,
            ref=claim.id,
        )
        graph.add_edge(
            src=claim_nid,
            dst=conclusion.id,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.85,
        )

    review = ReviewReport(
        report_id=_uid(),
        reviewer="methodological",
        conclusion_id=conclusion.id,
        findings=[
            Finding(
                category="argument",
                severity="info",
                detail="Looks sound.",
                evidence=["claim:" + claims[0].id],
                suggested_action="ship",
            )
        ],
        overall_verdict="accept",
        confidence=0.8,
        completed_at=datetime(2026, 1, 8, tzinfo=timezone.utc),
        method_invocation_ids=[inv.id],
    )
    store.insert_review_report(review)

    drift = DriftEvent(
        id=_uid(),
        target_id=conclusion.id,
        observed_at=date(2026, 2, 1),
        drift_score=0.42,
        notes="Calibration drifted.",
    )
    store.put_drift_event(drift)

    return {
        "conclusion": conclusion,
        "claims": claims,
        "artifact": artifact,
        "review": review,
        "drift": drift,
    }


def test_assembly_is_order_stable(store: Store, synthetic):
    """Same inputs → same JSON bytes. We check both node ordering and
    the serialised form so the lineage is citable in a research appendix."""
    cid = synthetic["conclusion"].id

    a = assemble_lineage(store, cid)
    b = assemble_lineage(store, cid)

    # `assembled_at` floats with wall-clock; everything else must match.
    a_dump = a.model_dump(mode="json", exclude={"assembled_at"})
    b_dump = b.model_dump(mode="json", exclude={"assembled_at"})
    assert a_dump == b_dump

    # Node ordering is deterministic by (timestamp, kind_priority, id).
    timestamps = [n.timestamp for n in a.nodes]
    assert timestamps == sorted(timestamps), "lineage nodes must be time-sorted"

    # And the conclusion's two source claims arrive before it.
    kinds = [n.kind for n in a.nodes]
    first_concl_idx = kinds.index(LineageNodeKind.CONCLUSION)
    assert all(
        kinds[i] in (LineageNodeKind.SOURCE, LineageNodeKind.CLAIM)
        for i in range(first_concl_idx)
    ), "every node before the conclusion must be a source/claim"


def test_public_filter_does_not_leak_private_nodes(store: Store, synthetic):
    """`lineage.public()` returns ONLY public-visible nodes. The drift
    and peer-review nodes (private) must be absent — not redacted."""
    cid = synthetic["conclusion"].id
    full = assemble_lineage(store, cid)
    public = full.public()

    private_ids = {n.id for n in full.nodes if not n.public_visible}
    assert private_ids, "fixture must produce at least one private node"

    public_ids = {n.id for n in public.nodes}
    assert public_ids.isdisjoint(private_ids)

    # No edge in the public lineage may reference a dropped node — that
    # would let a reader infer a private step exists.
    for e in public.edges:
        assert e.src in public_ids and e.dst in public_ids

    # And the JSON itself must not mention the private node ids.
    blob = public.model_dump_json()
    for nid in private_ids:
        assert nid not in blob

    # Drift + peer-review kinds should be entirely absent from the public
    # serialisation; the public lineage shows source → claim → conclusion.
    public_kinds = {n.kind for n in public.nodes}
    assert LineageNodeKind.DRIFT not in public_kinds
    assert LineageNodeKind.PEER_REVIEW not in public_kinds


def test_export_is_round_trippable(store: Store, synthetic, tmp_path):
    """JSON export → reload produces the exact same Lineage."""
    cid = synthetic["conclusion"].id
    lineage = assemble_lineage(store, cid)

    json_path = tmp_path / "lineage.json"
    json_path.write_text(lineage.model_dump_json(indent=2), encoding="utf-8")

    reloaded = Lineage.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert reloaded.model_dump(mode="json") == lineage.model_dump(mode="json")

    md = lineage_to_markdown(lineage)
    assert cid in md
    assert "## Timeline" in md


def test_lineage_diff_surfaces_added_and_removed_nodes(store: Store, synthetic):
    """`lineage_diff` is the engine behind revision-event "what changed"."""
    cid = synthetic["conclusion"].id
    before = assemble_lineage(store, cid)

    # Add a new drift event after the snapshot.
    new_drift = DriftEvent(
        id=_uid(),
        target_id=cid,
        observed_at=date(2026, 3, 1),
        drift_score=0.6,
        notes="Re-validated after Q1.",
    )
    store.put_drift_event(new_drift)
    after = assemble_lineage(store, cid)

    diff = lineage_diff(before, after)
    added_ids = {n.id for n in diff.added}
    assert f"drift:{new_drift.id}" in added_ids
    assert diff.removed == []
