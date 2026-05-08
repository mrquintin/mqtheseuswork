"""Tests for the declarative ``DomainBound`` system on registered methods.

Covers:

  * the three verdict statuses (in_bounds, edge_case, out_of_bounds) for
    both anchor-centroid and tag-set bounds, and for combined bounds
    under both ``"any"`` and ``"all"`` combinators;
  * the deterministic loader (``load_domain_bound``) including auto-
    derivation of ``revision_id`` and ``edge_radius``;
  * cross-model embedding refusal — anchors built under model A cannot
    be checked against an embedding from model B;
  * the refusal helper writes a ledger entry when the orchestrator
    invokes a method on an out-of-bounds conclusion;
  * the MQS gate: an out-of-bounds verdict forces ``domain_sensitivity``
    to 0 and, by the multiplicative composite formula, gates the
    composite to 0 regardless of the other four sub-scores;
  * the registry side-table wiring on the decorator.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from noosphere.evaluation.mqs import (
    MqsInput,
    StubMqsJudge,
    score_conclusion,
    score_domain_sensitivity,
)
from noosphere.methods.anchor_curator import (
    CandidateConclusion,
    propose_anchors,
    to_anchor_bound_dict,
)
from noosphere.methods.domain_bounds import (
    AnchorBound,
    DomainBound,
    DomainVerdict,
    EmbeddingModelMismatch,
    TagBound,
    angular_cosine_distance,
    check_anchor,
    check_domain,
    check_tags,
    load_domain_bound,
    refuse_out_of_bounds,
)
from noosphere.methods._decorator import register_method
from noosphere.methods._registry import REGISTRY
from noosphere.models import MethodType


# ── Synthetic embeddings ───────────────────────────────────────────────────


def _ax(i: int, dim: int = 4) -> tuple[float, ...]:
    """Unit vector along axis ``i``. Distinct axes give distance 0.5
    (= 90 degrees / 180 degrees) under angular cosine; same axis = 0."""
    v = [0.0] * dim
    v[i % dim] = 1.0
    return tuple(v)


def _near(i: int, *, eps: float = 0.05, dim: int = 4) -> tuple[float, ...]:
    """A vector close-but-not-identical to axis ``i``. Same direction
    plus a small bump toward axis (i+1) so angular distance is small."""
    v = list(_ax(i, dim=dim))
    v[(i + 1) % dim] = eps
    return tuple(v)


# ── Distance ───────────────────────────────────────────────────────────────


def test_angular_cosine_distance_basics():
    a = (1.0, 0.0)
    b = (1.0, 0.0)
    assert angular_cosine_distance(a, b) == pytest.approx(0.0)

    c = (0.0, 1.0)
    assert angular_cosine_distance(a, c) == pytest.approx(0.5)

    d = (-1.0, 0.0)
    assert angular_cosine_distance(a, d) == pytest.approx(1.0)


def test_angular_cosine_distance_zero_vector_returns_max():
    # A zero vector cannot be in-domain under any tight radius.
    assert angular_cosine_distance((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)) == 1.0


def test_angular_cosine_distance_dim_mismatch():
    with pytest.raises(ValueError):
        angular_cosine_distance((1.0, 0.0), (1.0, 0.0, 0.0))


# ── Tag bound ──────────────────────────────────────────────────────────────


def test_tag_bound_in_bounds_and_out():
    bound = TagBound(tags=("forecasting", "policy"))
    v = check_tags(bound, ["Policy", "weather"])
    assert v.status == "in_bounds"
    assert v.matched_tags == ("policy",)
    assert v.margin == 1.0

    v2 = check_tags(bound, ["weather", "art"])
    assert v2.status == "out_of_bounds"
    assert v2.margin == -1.0


def test_tag_bound_normalization_is_case_insensitive():
    bound = TagBound(tags=("  Forecasting  ", "POLICY"))
    v = check_tags(bound, ["forecasting"])
    assert v.status == "in_bounds"


# ── Anchor bound ───────────────────────────────────────────────────────────


@pytest.fixture
def anchor_bound() -> AnchorBound:
    return AnchorBound(
        anchors=(_ax(0), _ax(1)),
        embedding_model="mock-embed",
        in_radius=0.10,
        edge_radius=0.20,
        revision_id="rev_test",
    )


def test_anchor_bound_in_bounds(anchor_bound):
    # _near(0) is very close to _ax(0); distance should be < 0.10.
    v = check_anchor(anchor_bound, embedding=_near(0, eps=0.001), embedding_model="mock-embed")
    assert v.status == "in_bounds"
    assert v.margin > 0
    assert v.matched_anchor_index == 0
    assert v.anchor_revision_id == "rev_test"


def test_anchor_bound_edge_case(anchor_bound):
    # Construct an embedding whose angular distance to the nearest anchor
    # is between in_radius (0.10) and edge_radius (0.20). 45 degrees /
    # 180 degrees = 0.25 is too far, so we use a smaller perturbation.
    # cos(theta) = 0.96 -> theta/pi ~ 0.0901 (in_bounds), so we tilt
    # harder to get into the edge band.
    target = math.cos(math.pi * 0.15)  # angular distance ~ 0.15 (between 0.10 and 0.20)
    sin = math.sqrt(max(0.0, 1.0 - target * target))
    emb = (target, sin, 0.0, 0.0)
    v = check_anchor(anchor_bound, embedding=emb, embedding_model="mock-embed")
    assert v.status == "edge_case"
    assert v.margin > 0  # positive but smaller


def test_anchor_bound_out_of_bounds(anchor_bound):
    # Far from both axes 0 and 1 — push along axis 2 (orthogonal to both).
    v = check_anchor(anchor_bound, embedding=_ax(2), embedding_model="mock-embed")
    assert v.status == "out_of_bounds"
    assert v.margin < 0


def test_anchor_bound_refuses_cross_model(anchor_bound):
    with pytest.raises(EmbeddingModelMismatch):
        check_anchor(anchor_bound, embedding=_ax(0), embedding_model="other-model")


def test_anchor_bound_refuses_dim_mismatch(anchor_bound):
    with pytest.raises(EmbeddingModelMismatch):
        check_anchor(
            anchor_bound,
            embedding=(1.0, 0.0, 0.0),
            embedding_model="mock-embed",
        )


# ── Combined bound ─────────────────────────────────────────────────────────


def test_domain_bound_combinator_any_passes_when_either_passes(anchor_bound):
    bound = DomainBound(
        tag_bound=TagBound(tags=("forecasting",)),
        anchor_bound=anchor_bound,
        combinator="any",
    )
    # Tag fails, anchor passes -> overall in_bounds via "any".
    v = check_domain(
        bound,
        embedding=_ax(0),
        embedding_model="mock-embed",
        tags=["weather"],
    )
    assert v.status == "in_bounds"


def test_domain_bound_combinator_all_requires_both(anchor_bound):
    bound = DomainBound(
        tag_bound=TagBound(tags=("forecasting",)),
        anchor_bound=anchor_bound,
        combinator="all",
    )
    # Tag fails, anchor passes -> overall out via "all".
    v = check_domain(
        bound,
        embedding=_ax(0),
        embedding_model="mock-embed",
        tags=["weather"],
    )
    assert v.status == "out_of_bounds"


def test_domain_bound_anchor_side_without_embedding_is_out_of_bounds(anchor_bound):
    bound = DomainBound(anchor_bound=anchor_bound)
    v = check_domain(bound, tags=["forecasting"])
    assert v.status == "out_of_bounds"


def test_empty_domain_bound_is_rejected():
    with pytest.raises(ValueError):
        DomainBound()


# ── Loader ─────────────────────────────────────────────────────────────────


def test_load_domain_bound_from_bare_tag_list():
    bound = load_domain_bound(["forecasting", "policy"])
    assert isinstance(bound, DomainBound)
    assert bound.tag_bound is not None
    assert bound.anchor_bound is None
    assert "forecasting" in bound.tag_bound.tags


def test_load_domain_bound_derives_revision_id_and_edge_radius():
    blob = {
        "anchors": [[1.0, 0.0], [0.0, 1.0]],
        "embedding_model": "mock-embed",
        "in_radius": 0.20,
    }
    a = load_domain_bound(blob)
    b = load_domain_bound(blob)
    assert a.anchor_bound.revision_id == b.anchor_bound.revision_id  # deterministic
    assert a.anchor_bound.revision_id.startswith("rev_")
    assert a.anchor_bound.edge_radius == pytest.approx(0.25)  # 0.20 * 1.25


def test_load_domain_bound_rejects_anchor_without_model():
    with pytest.raises(ValueError):
        load_domain_bound({"anchors": [[1.0, 0.0]], "in_radius": 0.2})


# ── Decorator integration ─────────────────────────────────────────────────


@pytest.fixture
def fresh_registry():
    saved_specs = dict(REGISTRY._specs)
    saved_fns = dict(REGISTRY._fns)
    saved_emits = dict(REGISTRY._emits_edges)
    saved_deps = dict(REGISTRY._depends_on)
    saved_bounds = dict(REGISTRY._domain_bounds)
    REGISTRY._specs.clear()
    REGISTRY._fns.clear()
    REGISTRY._emits_edges.clear()
    REGISTRY._depends_on.clear()
    REGISTRY._domain_bounds.clear()
    yield REGISTRY
    REGISTRY._specs.clear()
    REGISTRY._fns.clear()
    REGISTRY._emits_edges.clear()
    REGISTRY._depends_on.clear()
    REGISTRY._domain_bounds.clear()
    REGISTRY._specs.update(saved_specs)
    REGISTRY._fns.update(saved_fns)
    REGISTRY._emits_edges.update(saved_emits)
    REGISTRY._depends_on.update(saved_deps)
    REGISTRY._domain_bounds.update(saved_bounds)


def test_decorator_stashes_domain_bound_in_registry(fresh_registry):
    @register_method(
        name="forecast_method_test",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={},
        output_schema={},
        description="test",
        rationale="test",
        owner="test",
        domain=["forecasting", "policy"],
    )
    def _fn(x):  # pragma: no cover - body irrelevant
        return x

    bound = fresh_registry.get_domain_bound("forecast_method_test")
    assert bound is not None
    assert bound.tag_bound is not None
    assert "forecasting" in bound.tag_bound.tags


def test_decorator_method_without_domain_has_no_bound(fresh_registry):
    @register_method(
        name="unbounded_test",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={},
        output_schema={},
        description="test",
        rationale="test",
        owner="test",
    )
    def _fn(x):  # pragma: no cover
        return x

    assert fresh_registry.get_domain_bound("unbounded_test") is None


# ── Refusal helper + ledger ────────────────────────────────────────────────


class _FakeLedger:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(
        self,
        *,
        actor,
        method_id,
        inputs_hash,
        outputs_hash,
        inputs_ref,
        outputs_ref,
        context,
    ) -> str:
        entry_id = hashlib.sha256(
            f"{method_id}:{inputs_hash}:{outputs_hash}".encode()
        ).hexdigest()[:16]
        self.entries.append(
            {
                "entry_id": entry_id,
                "actor": actor,
                "method_id": method_id,
                "inputs_hash": inputs_hash,
                "outputs_hash": outputs_hash,
                "inputs_ref": inputs_ref,
                "outputs_ref": outputs_ref,
                "context": context,
            }
        )
        return entry_id


def test_refuse_out_of_bounds_writes_ledger_entry():
    ledger = _FakeLedger()
    verdict = DomainVerdict(
        status="out_of_bounds",
        margin=-0.42,
        reason="nearest anchor too far",
        embedding_model="mock-embed",
        anchor_revision_id="rev_x",
        distance=0.62,
    )
    refusal = refuse_out_of_bounds(
        method_name="contradiction_probe",
        method_version="1.0.0",
        method_id="m_abc",
        conclusion_id="c_xyz",
        verdict=verdict,
        ledger=ledger,
        actor=object(),
        context=object(),
    )
    assert refusal.method_name == "contradiction_probe"
    assert refusal.conclusion_id == "c_xyz"
    assert refusal.verdict.status == "out_of_bounds"
    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry["method_id"] == "m_abc"
    assert "contradiction_probe" in entry["inputs_ref"]
    assert "c_xyz" in entry["outputs_ref"]


def test_refuse_out_of_bounds_rejects_non_refusing_verdict():
    verdict = DomainVerdict(status="in_bounds", margin=0.05, reason="ok")
    with pytest.raises(ValueError):
        refuse_out_of_bounds(
            method_name="m",
            method_version="1.0.0",
            method_id=None,
            conclusion_id="c",
            verdict=verdict,
        )


# ── MQS gating ─────────────────────────────────────────────────────────────


def _high_score_judge() -> StubMqsJudge:
    """Pin every sub-score to a high value so the only way the composite
    can go to zero is through the domain-sensitivity gate."""
    return StubMqsJudge(
        responses={
            "severity": {"score": 1.0, "rationale": "stub"},
            "aim_method_fit": {"score": 1.0, "rationale": "stub"},
            "compressibility": {"score": 1.0, "rationale": "stub", "decorative_count": 0},
            "domain_sensitivity": {"score": 1.0, "rationale": "stub"},
        }
    )


def test_mqs_out_of_bounds_gates_composite_to_zero():
    judge = _high_score_judge()
    inp = MqsInput(
        conclusion_id="c1",
        conclusion_text="we will revisit by 2027",  # boost progressivity floor
        topic_hint="forecasting",
        forecast_count=2,
        has_check_back_date=True,
        domain_bound_verdict="out_of_bounds",
        domain_bound_margin=-0.32,
        domain_bound_revision_id="rev_x",
    )
    score = score_conclusion(inp, judge=judge)
    assert score.domain_sensitivity.score == 0.0
    assert score.domain_sensitivity.evidence["gated_to_zero"] is True
    assert score.composite == 0.0  # gate forces composite to 0


def test_mqs_in_bounds_does_not_gate():
    judge = _high_score_judge()
    inp = MqsInput(
        conclusion_id="c2",
        conclusion_text="we will revisit by 2027",
        topic_hint="forecasting",
        forecast_count=2,
        has_check_back_date=True,
        domain_bound_verdict="in_bounds",
        domain_bound_margin=0.08,
    )
    score = score_conclusion(inp, judge=judge)
    assert score.domain_sensitivity.score > 0
    assert score.composite > 0


def test_mqs_edge_case_caps_domain_sensitivity():
    judge = _high_score_judge()
    inp = MqsInput(
        conclusion_id="c3",
        conclusion_text="we will revisit by 2027",
        topic_hint="forecasting",
        forecast_count=2,
        has_check_back_date=True,
        domain_bound_verdict="edge_case",
        domain_bound_margin=0.02,
    )
    sub = score_domain_sensitivity(inp, judge)
    assert sub.score <= 0.4 + 1e-9
    assert sub.evidence["edge_case_capped"] is True


def test_mqs_no_verdict_preserves_legacy_behavior():
    judge = _high_score_judge()
    inp = MqsInput(
        conclusion_id="c4",
        conclusion_text="we will revisit by 2027",
        topic_hint="forecasting",
        forecast_count=2,
        has_check_back_date=True,
        # domain_bound_verdict left as None
    )
    sub = score_domain_sensitivity(inp, judge)
    assert sub.evidence["domain_bound_verdict"] is None
    assert sub.score > 0


# ── Anchor curator ────────────────────────────────────────────────────────


def test_propose_anchors_picks_real_corpus_points():
    # Two well-separated clusters of 4 points each in 4-D.
    cluster_a = [
        CandidateConclusion(conclusion_id=f"a{i}", embedding=_near(0, eps=0.001 * i, dim=4))
        for i in range(4)
    ]
    cluster_b = [
        CandidateConclusion(conclusion_id=f"b{i}", embedding=_near(2, eps=0.001 * i, dim=4))
        for i in range(4)
    ]
    proposal = propose_anchors(
        method_name="m",
        embedding_model="mock-embed",
        candidates=cluster_a + cluster_b,
        k=2,
        seed=0,
    )
    # Both medoid IDs should be drawn from the input corpus.
    cand_ids = {c.conclusion_id for c in cluster_a + cluster_b}
    assert set(proposal.medoid_ids).issubset(cand_ids)
    assert len(proposal.medoid_ids) == 2

    # Medoids should land in different clusters (one a*, one b*).
    has_a = any(mid.startswith("a") for mid in proposal.medoid_ids)
    has_b = any(mid.startswith("b") for mid in proposal.medoid_ids)
    assert has_a and has_b

    # The proposal can be turned into a valid AnchorBound dict.
    bound_dict = to_anchor_bound_dict(proposal)
    bound = load_domain_bound(bound_dict)
    assert bound.anchor_bound is not None
    assert bound.anchor_bound.embedding_model == "mock-embed"


def test_propose_anchors_revision_id_is_deterministic():
    cands = [
        CandidateConclusion(conclusion_id=f"x{i}", embedding=_near(0, eps=0.001 * i, dim=4))
        for i in range(4)
    ]
    p1 = propose_anchors(method_name="m", embedding_model="mock-embed", candidates=cands, k=2, seed=42)
    p2 = propose_anchors(method_name="m", embedding_model="mock-embed", candidates=cands, k=2, seed=42)
    assert p1.revision_id == p2.revision_id
    assert p1.medoid_ids == p2.medoid_ids
