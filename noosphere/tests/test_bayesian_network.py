"""
Tests for the Bayesian-belief layer over the cascade graph.

Coverage matches the F-test list in the Round-20 prompt:

* a synthetic 5-node BN with hand-computed CPTs, asserting inference is
  *exact* (variable elimination matches the analytic marginals to
  floating-point);
* that an evidence update propagates correctly through the DAG;
* that sensitivity analysis matches analytic ground truth.

Plus the surrounding contract: DAG derivation from a live cascade store,
deterministic cycle-breaking, the credible interval reflecting CPT
uncertainty, the importance-sampling fallback, CPT learning with Laplace
smoothing, and the evidence-delta → revision-engine handoff.
"""

from __future__ import annotations

import math
import uuid as _uuid
from datetime import datetime, timezone

import pytest

from noosphere.cascade.graph import CascadeGraph, build_bayesian_skeleton
from noosphere.cascade.revision import RevisionInput
from noosphere.inquiry.bayesian_network import (
    BayesianNetwork,
    BNNode,
    ConditionalProbabilityTable,
    build_bn_dag,
    seed_cpt,
)
from noosphere.inquiry.bn_inference import (
    EXACT_NODE_LIMIT,
    ConfidenceDelta,
    EvidenceUpdate,
    bayesian_view_payload,
    compare_to_stored,
    evidence_map,
    infer_marginals,
    marginal,
    most_influential_parents,
    sensitivity,
    to_revision_inputs,
)
from noosphere.inquiry.bn_learning import (
    ResolvedCase,
    fit_cpt,
    learn_network,
)
from noosphere.models import (
    CascadeEdgeRelation,
    CascadeNodeKind,
    MethodInvocation,
)
from noosphere.store import Store

TOL = 1e-9


# ── synthetic 5-node network ────────────────────────────────────────────
#
#     A (root, 0.7)        B (root, 0.4)
#       │                   │
#       ▼                   │
#     C  P(C|A)             │
#       │                   │
#       └────────┬──────────┘
#                ▼
#              D  P(D|B,C)
#                │
#                ▼
#              E  P(E|D)
#
# Every CPT below is hand-picked so the marginals can be worked out on
# paper — see ``_analytic_*`` helpers.

CPT_A = 0.7
CPT_B = 0.4
CPT_C = {False: 0.2, True: 0.9}                       # keyed by A
CPT_D = {                                             # keyed by (B, C)
    (False, False): 0.05,
    (False, True): 0.60,
    (True, False): 0.30,
    (True, True): 0.95,
}
CPT_E = {False: 0.1, True: 0.8}                       # keyed by D


def _five_node_bn() -> BayesianNetwork:
    node_a = BNNode(
        node_id="A",
        ref="claim:A",
        kind=CascadeNodeKind.CLAIM,
        parents=(),
        cpt=ConditionalProbabilityTable("A", (), {(): CPT_A}),
    )
    node_b = BNNode(
        node_id="B",
        ref="claim:B",
        kind=CascadeNodeKind.CLAIM,
        parents=(),
        cpt=ConditionalProbabilityTable("B", (), {(): CPT_B}),
    )
    node_c = BNNode(
        node_id="C",
        ref="claim:C",
        kind=CascadeNodeKind.CLAIM,
        parents=("A",),
        cpt=ConditionalProbabilityTable(
            "C", ("A",), {(False,): CPT_C[False], (True,): CPT_C[True]}
        ),
    )
    node_d = BNNode(
        node_id="D",
        ref="claim:D",
        kind=CascadeNodeKind.CLAIM,
        parents=("B", "C"),
        cpt=ConditionalProbabilityTable("D", ("B", "C"), dict(CPT_D)),
    )
    node_e = BNNode(
        node_id="E",
        ref="conclusion:E",
        kind=CascadeNodeKind.CONCLUSION,
        parents=("D",),
        cpt=ConditionalProbabilityTable(
            "E", ("D",), {(False,): CPT_E[False], (True,): CPT_E[True]}
        ),
    )
    return BayesianNetwork(
        nodes={n.node_id: n for n in (node_a, node_b, node_c, node_d, node_e)}
    )


# — analytic ground truth —


def _p_c(p_a: float) -> float:
    return CPT_C[True] * p_a + CPT_C[False] * (1.0 - p_a)


def _p_d(p_b: float, p_c: float) -> float:
    total = 0.0
    for b in (False, True):
        for c in (False, True):
            pb = p_b if b else 1.0 - p_b
            pc = p_c if c else 1.0 - p_c
            total += CPT_D[(b, c)] * pb * pc
    return total


def _p_e(p_d: float) -> float:
    return CPT_E[True] * p_d + CPT_E[False] * (1.0 - p_d)


# ── A. exact inference ──────────────────────────────────────────────────


class TestExactInference:
    def test_marginals_match_analytic_ground_truth(self):
        bn = _five_node_bn()
        result = infer_marginals(bn)

        p_a = CPT_A
        p_b = CPT_B
        p_c = _p_c(p_a)
        p_d = _p_d(p_b, p_c)
        p_e = _p_e(p_d)

        assert result["A"].p_true == pytest.approx(p_a, abs=TOL)
        assert result["B"].p_true == pytest.approx(p_b, abs=TOL)
        assert result["C"].p_true == pytest.approx(p_c, abs=TOL)
        assert result["D"].p_true == pytest.approx(p_d, abs=TOL)
        assert result["E"].p_true == pytest.approx(p_e, abs=TOL)

        # No CPT counts on this fixture ⇒ the network is treated as
        # certain, so every result is an exact point with a collapsed CI.
        for r in result.values():
            assert r.exact is True
            assert r.method == "exact"
            assert r.ci_low == pytest.approx(r.p_true, abs=TOL)
            assert r.ci_high == pytest.approx(r.p_true, abs=TOL)

    def test_marginal_helper_agrees_with_infer_marginals(self):
        bn = _five_node_bn()
        full = infer_marginals(bn)
        for nid in bn.nodes:
            assert marginal(bn, nid) == pytest.approx(full[nid].p_true, abs=TOL)

    def test_variable_elimination_is_order_independent(self):
        """Two structurally identical networks built in different node
        insertion orders must yield identical marginals."""
        bn1 = _five_node_bn()
        nodes = list(bn1.nodes.values())
        bn2 = BayesianNetwork(nodes={n.node_id: n for n in reversed(nodes)})
        m1 = infer_marginals(bn1)
        m2 = infer_marginals(bn2)
        for nid in bn1.nodes:
            assert m1[nid].p_true == pytest.approx(m2[nid].p_true, abs=TOL)


# ── B. evidence updates ─────────────────────────────────────────────────


class TestEvidenceUpdate:
    def test_evidence_on_root_propagates_to_all_descendants(self):
        bn = _five_node_bn()
        result = infer_marginals(bn, evidence={"A": True})

        # A pinned True; C/D/E recomputed with P(A)=1.
        p_c = _p_c(1.0)
        p_d = _p_d(CPT_B, p_c)
        p_e = _p_e(p_d)

        assert result["A"].p_true == pytest.approx(1.0, abs=TOL)
        assert result["A"].is_evidence is True
        assert result["C"].p_true == pytest.approx(p_c, abs=TOL)
        assert result["D"].p_true == pytest.approx(p_d, abs=TOL)
        assert result["E"].p_true == pytest.approx(p_e, abs=TOL)
        # B is not downstream of A and must be untouched.
        assert result["B"].p_true == pytest.approx(CPT_B, abs=TOL)

    def test_retraction_evidence_drops_descendant_marginal(self):
        bn = _five_node_bn()
        before = marginal(bn, "E")
        after = marginal(bn, "E", evidence={"C": False})
        # C=False is the unfavourable parent state for D, so E falls.
        assert after < before

    def test_evidence_map_last_write_wins(self):
        updates = [
            EvidenceUpdate("A", True, kind="forecast_resolution"),
            EvidenceUpdate("A", False, kind="retraction"),
        ]
        assert evidence_map(updates) == {"A": False}

    def test_downstream_evidence_updates_upstream_belief(self):
        """Conditioning on a child raises the posterior of its parent —
        the BN does diagnostic (bottom-up) inference, not just causal."""
        bn = _five_node_bn()
        prior_d = marginal(bn, "D")
        posterior_d = marginal(bn, "D", evidence={"E": True})
        assert posterior_d > prior_d


# ── sensitivity analysis ────────────────────────────────────────────────


class TestSensitivity:
    def test_sensitivity_of_E_to_D_matches_analytic(self):
        bn = _five_node_bn()
        sens = sensitivity(bn, "E")
        assert [s.parent_id for s in sens] == ["D"]
        s = sens[0]
        assert s.p_if_retracted == pytest.approx(CPT_E[False], abs=TOL)
        assert s.p_if_held == pytest.approx(CPT_E[True], abs=TOL)
        assert s.baseline == pytest.approx(marginal(bn, "E"), abs=TOL)
        assert s.delta == pytest.approx(s.baseline - CPT_E[False], abs=TOL)
        assert s.influence == pytest.approx(CPT_E[True] - CPT_E[False], abs=TOL)

    def test_sensitivity_of_D_to_both_parents_matches_analytic(self):
        bn = _five_node_bn()
        sens = {s.parent_id: s for s in sensitivity(bn, "D")}
        assert set(sens) == {"B", "C"}

        # P(D | C=False) and P(D | C=True), marginalising B.
        p_d_c_false = _p_d(CPT_B, 0.0)
        p_d_c_true = _p_d(CPT_B, 1.0)
        assert sens["C"].p_if_retracted == pytest.approx(p_d_c_false, abs=TOL)
        assert sens["C"].p_if_held == pytest.approx(p_d_c_true, abs=TOL)

        # P(D | B=False) and P(D | B=True), marginalising C.
        p_c = _p_c(CPT_A)
        p_d_b_false = _p_d(0.0, p_c)
        p_d_b_true = _p_d(1.0, p_c)
        assert sens["B"].p_if_retracted == pytest.approx(p_d_b_false, abs=TOL)
        assert sens["B"].p_if_held == pytest.approx(p_d_b_true, abs=TOL)

    def test_sensitivity_ranked_by_influence(self):
        bn = _five_node_bn()
        sens = sensitivity(bn, "D")
        influences = [s.influence for s in sens]
        assert influences == sorted(influences, reverse=True)

    def test_most_influential_parents_respects_top_k(self):
        bn = _five_node_bn()
        top1 = most_influential_parents(bn, "D", top_k=1)
        assert len(top1) == 1
        assert top1[0].influence == max(s.influence for s in sensitivity(bn, "D"))

    def test_root_node_has_no_sensitivity(self):
        bn = _five_node_bn()
        assert sensitivity(bn, "A") == []


# ── importance-sampling fallback ────────────────────────────────────────


class TestApproximateInference:
    def test_importance_sampling_approximates_exact(self):
        """Forcing the approximate backend (exact_limit=0) on the tiny
        fixture must land close to the analytic marginals and label
        itself honestly."""
        bn = _five_node_bn()
        result = infer_marginals(
            bn, exact_limit=0, importance_samples=40_000, seed=7
        )
        exact = infer_marginals(bn)
        for nid in bn.nodes:
            assert result[nid].method == "importance_sampling"
            assert result[nid].exact is False
            assert result[nid].n_samples == 40_000
            assert result[nid].p_true == pytest.approx(
                exact[nid].p_true, abs=0.02
            )

    def test_importance_sampling_with_evidence(self):
        bn = _five_node_bn()
        result = infer_marginals(
            bn,
            evidence={"A": True},
            exact_limit=0,
            importance_samples=40_000,
            seed=11,
        )
        exact = infer_marginals(bn, evidence={"A": True})
        assert result["E"].p_true == pytest.approx(exact["E"].p_true, abs=0.03)
        # CI must bracket the point estimate.
        assert result["E"].ci_low <= result["E"].p_true <= result["E"].ci_high


# ── DAG construction from a live cascade ────────────────────────────────


def _uid() -> str:
    return str(_uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def store_graph_inv():
    store = Store.from_database_url("sqlite:///:memory:")
    inv = MethodInvocation(
        id=_uid(),
        method_id=_uid(),
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
    return store, CascadeGraph(store), inv


class TestDagConstruction:
    def test_build_bn_dag_projects_claims_and_conclusions(self, store_graph_inv):
        store, graph, inv = store_graph_inv
        claim = graph.add_node(kind=CascadeNodeKind.CLAIM, ref="c1")
        conclusion = graph.add_node(kind=CascadeNodeKind.CONCLUSION, ref="conc")
        artifact = graph.add_node(kind=CascadeNodeKind.ARTIFACT, ref="art")
        # claim → conclusion is a BN edge; artifact → claim is not (an
        # artifact is evidence, not a truth-valued proposition).
        graph.add_edge(
            src=claim, dst=conclusion,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )
        graph.add_edge(
            src=artifact, dst=claim,
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id=inv.id, confidence=0.8,
        )

        bn = build_bn_dag(store)
        assert set(bn.nodes) == {claim, conclusion}
        assert bn.parents_of(conclusion) == (claim,)
        assert bn.parents_of(claim) == ()

        # A supports edge should seed the conclusion well above the leak.
        m = infer_marginals(bn)
        assert m[conclusion].p_true > 0.5
        # Seeded CPT carries pseudo-counts ⇒ a real credible interval.
        with_ci = infer_marginals(bn, ci_samples=64, seed=3)
        assert with_ci[conclusion].ci_low < with_ci[conclusion].p_true
        assert with_ci[conclusion].ci_high > with_ci[conclusion].p_true

    def test_refutes_edge_pulls_marginal_below_leak(self, store_graph_inv):
        store, graph, inv = store_graph_inv
        claim = graph.add_node(kind=CascadeNodeKind.CLAIM, ref="bad")
        conclusion = graph.add_node(kind=CascadeNodeKind.CONCLUSION, ref="conc")
        graph.add_edge(
            src=claim, dst=conclusion,
            relation=CascadeEdgeRelation.REFUTES,
            method_invocation_id=inv.id, confidence=0.9,
        )
        bn = build_bn_dag(store)
        # With the refuting parent active the conclusion should sit low.
        assert marginal(bn, conclusion, evidence={claim: True}) < 0.5

    def test_cycle_is_broken_deterministically(self, store_graph_inv):
        store, graph, inv = store_graph_inv
        a = graph.add_node(kind=CascadeNodeKind.CLAIM, ref="a")
        b = graph.add_node(kind=CascadeNodeKind.CLAIM, ref="b")
        c = graph.add_node(kind=CascadeNodeKind.CLAIM, ref="c")
        # a → b → c → a is a cycle in the coheres_with subgraph.
        graph.add_edge(
            src=a, dst=b, relation=CascadeEdgeRelation.COHERES_WITH,
            method_invocation_id=inv.id, confidence=0.5,
        )
        graph.add_edge(
            src=b, dst=c, relation=CascadeEdgeRelation.COHERES_WITH,
            method_invocation_id=inv.id, confidence=0.5,
        )
        graph.add_edge(
            src=c, dst=a, relation=CascadeEdgeRelation.COHERES_WITH,
            method_invocation_id=inv.id, confidence=0.5,
        )
        skeleton = build_bayesian_skeleton(store)
        assert len(skeleton["dropped_edge_ids"]) == 1
        assert len(skeleton["edges"]) == 2

        # The BN must still be a valid DAG (construction would raise if not).
        bn = build_bn_dag(store)
        assert len(bn.dropped_edges) == 1
        assert len(bn.topological_order()) == 3

        # Deterministic: same snapshot → identical skeleton.
        again = build_bayesian_skeleton(store)
        assert again == skeleton

    def test_credibility_lookup_attenuates_low_credibility_source(
        self, store_graph_inv
    ):
        store, graph, inv = store_graph_inv
        claim = graph.add_node(kind=CascadeNodeKind.CLAIM, ref="src")
        conclusion = graph.add_node(kind=CascadeNodeKind.CONCLUSION, ref="conc")
        graph.add_edge(
            src=claim, dst=conclusion,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )
        trusted = build_bn_dag(store)
        distrusted = build_bn_dag(store, credibility={claim: 0.2})
        # A low-credibility source seeds a weaker CPT row.
        p_trusted = marginal(trusted, conclusion, evidence={claim: True})
        p_distrusted = marginal(distrusted, conclusion, evidence={claim: True})
        assert p_distrusted < p_trusted


# ── CPT learning ────────────────────────────────────────────────────────


class TestCptLearning:
    def test_fit_cpt_uses_laplace_smoothing_on_sparse_rows(self):
        bn = _five_node_bn()
        node_c = bn.nodes["C"]
        # One observation, A=True → C=True. Laplace add-one ⇒ 2/3, not 1.
        cases = [
            ResolvedCase("C", {"A": True}, outcome=True),
        ]
        cpt, report = fit_cpt(node_c, cases, laplace_alpha=1.0)
        assert cpt.p_true((True,)) == pytest.approx(2.0 / 3.0, abs=TOL)
        # The A=False row had no data ⇒ it keeps the seeded value.
        assert cpt.p_true((False,)) == pytest.approx(CPT_C[False], abs=TOL)
        assert (True,) in report.fitted_rows
        assert (False,) in report.seeded_rows
        assert report.fully_fit is False

    def test_fit_cpt_converges_to_empirical_with_enough_data(self):
        bn = _five_node_bn()
        node_c = bn.nodes["C"]
        # 70 True / 30 False under A=True ⇒ ~0.7 with α=1 smoothing.
        cases = (
            [ResolvedCase("C", {"A": True}, outcome=True) for _ in range(70)]
            + [ResolvedCase("C", {"A": True}, outcome=False) for _ in range(30)]
        )
        cpt, _ = fit_cpt(node_c, cases, laplace_alpha=1.0)
        assert cpt.p_true((True,)) == pytest.approx(71.0 / 102.0, abs=TOL)
        # Counts reflect data volume ⇒ a tight credible interval later.
        alpha, beta = cpt.row_counts((True,))
        assert alpha == pytest.approx(71.0, abs=TOL)
        assert beta == pytest.approx(31.0, abs=TOL)

    def test_learn_network_only_fits_nodes_above_threshold(self):
        bn = _five_node_bn()
        # Plenty of cases for C, none for anything else.
        cases = [
            ResolvedCase("C", {"A": True}, outcome=True) for _ in range(10)
        ]
        learned = learn_network(bn, cases, min_cases_for_fit=4)
        assert learned.fitted_node_ids == ("C",)
        assert learned.network.nodes["C"].seeded is False
        assert learned.network.nodes["A"].seeded is True
        assert learned.network.nodes["D"].seeded is True
        # Structure is preserved.
        assert learned.network.parents_of("D") == ("B", "C")

    def test_learning_tightens_credible_interval(self):
        """A CPT fit from many cases yields a tighter CI than the seeded
        guess it replaces."""
        bn = _five_node_bn()
        # Seed C's CPT with counts so it has a non-trivial interval.
        node_c = bn.nodes["C"]
        seeded_c = BNNode(
            node_id="C",
            ref=node_c.ref,
            kind=node_c.kind,
            parents=("A",),
            cpt=seed_cpt("C", {"A": 0.5}),
        )
        bn.nodes["C"] = seeded_c
        bn = BayesianNetwork(nodes=dict(bn.nodes))
        seeded_ci = infer_marginals(bn, ci_samples=80, seed=1)["C"]

        cases = (
            [ResolvedCase("C", {"A": True}, outcome=True) for _ in range(120)]
            + [ResolvedCase("C", {"A": False}, outcome=False) for _ in range(120)]
        )
        learned = learn_network(bn, cases, min_cases_for_fit=4).network
        learned_ci = infer_marginals(learned, ci_samples=80, seed=1)["C"]

        seeded_width = seeded_ci.ci_high - seeded_ci.ci_low
        learned_width = learned_ci.ci_high - learned_ci.ci_low
        assert learned_width < seeded_width


# ── evidence delta → revision engine (part C) ───────────────────────────


class TestRevisionHandoff:
    def test_compare_to_stored_flags_significant_deltas(self):
        bn = _five_node_bn()
        marginals = infer_marginals(bn, evidence={"A": True})
        # Stored confidence deliberately stale for E, accurate for B.
        stored = {"E": 0.30, "B": CPT_B}
        deltas = compare_to_stored(marginals, stored, threshold=0.05)
        by_id = {d.node_id: d for d in deltas}
        assert by_id["E"].significant is True
        assert by_id["B"].significant is False
        # Sorted by descending |delta|.
        assert abs(deltas[0].delta) >= abs(deltas[-1].delta)

    def test_to_revision_inputs_maps_marginal_to_signed_weight(self):
        deltas = [
            ConfidenceDelta("c1", 0.5, 1.0, 1.0, 1.0, significant=True),
            ConfidenceDelta("c2", 0.5, 0.0, 0.0, 0.0, significant=True),
            ConfidenceDelta("c3", 0.5, 0.5, 0.5, 0.5, significant=False),
        ]
        inputs = to_revision_inputs(deltas)
        assert all(isinstance(i, RevisionInput) for i in inputs)
        by_claim = {i.claim_id: i for i in inputs}
        # marginal 1.0 → weight +1 (corroborates); 0.0 → -1 (contradicts).
        assert by_claim["c1"].clamped_weight() == pytest.approx(1.0, abs=TOL)
        assert by_claim["c2"].clamped_weight() == pytest.approx(-1.0, abs=TOL)
        # c3 not significant ⇒ excluded.
        assert "c3" not in by_claim

    def test_to_revision_inputs_can_include_insignificant(self):
        deltas = [ConfidenceDelta("c3", 0.5, 0.55, 0.5, 0.6, significant=False)]
        assert to_revision_inputs(deltas, only_significant=False)


# ── founder UI payload (part E) ─────────────────────────────────────────


class TestViewPayload:
    def test_payload_shape_for_founder_tab(self):
        bn = _five_node_bn()
        payload = bayesian_view_payload(bn, "E", top_k=3)
        assert payload["node_id"] == "E"
        assert payload["kind"] == "conclusion"
        assert payload["exact"] is True
        assert payload["method"] == "exact"
        assert payload["node_count"] == 5
        assert payload["exact_limit"] == EXACT_NODE_LIMIT
        assert 0.0 <= payload["marginal"] <= 1.0
        assert payload["parents"] and payload["parents"][0]["parent_id"] == "D"
        assert "p_if_retracted" in payload["parents"][0]

    def test_payload_unknown_node_raises(self):
        bn = _five_node_bn()
        with pytest.raises(KeyError):
            bayesian_view_payload(bn, "does-not-exist")


# ── network invariants ──────────────────────────────────────────────────


class TestNetworkInvariants:
    def test_topological_order_is_parents_before_children(self):
        bn = _five_node_bn()
        order = bn.topological_order()
        position = {nid: i for i, nid in enumerate(order)}
        for node in bn:
            for parent in node.parents:
                assert position[parent] < position[node.node_id]

    def test_cyclic_construction_is_rejected(self):
        # X ↔ Y is not a DAG; construction must refuse it.
        cpt_x = ConditionalProbabilityTable(
            "X", ("Y",), {(False,): 0.5, (True,): 0.5}
        )
        cpt_y = ConditionalProbabilityTable(
            "Y", ("X",), {(False,): 0.5, (True,): 0.5}
        )
        node_x = BNNode("X", "x", CascadeNodeKind.CLAIM, ("Y",), cpt_x)
        node_y = BNNode("Y", "y", CascadeNodeKind.CLAIM, ("X",), cpt_y)
        with pytest.raises(ValueError, match="cyclic"):
            BayesianNetwork(nodes={"X": node_x, "Y": node_y})

    def test_dangling_parent_is_rejected(self):
        cpt = ConditionalProbabilityTable(
            "X", ("ghost",), {(False,): 0.5, (True,): 0.5}
        )
        node = BNNode("X", "x", CascadeNodeKind.CLAIM, ("ghost",), cpt)
        with pytest.raises(ValueError, match="not in the network"):
            BayesianNetwork(nodes={"X": node})

    def test_non_total_cpt_is_rejected(self):
        with pytest.raises(ValueError, match="total"):
            ConditionalProbabilityTable("X", ("A",), {(True,): 0.5})
